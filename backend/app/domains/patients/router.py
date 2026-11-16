from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    AdministrativeDocument,
    AdministrativeFile,
    AuditEvent,
    Patient,
    PatientEmergencyContact,
    PatientIdentifier,
    Site,
    TenantSetting,
)
from app.db.session import tenant_session
from app.domains.identity.authorization import AuthorizationContext, load_authorization_context
from app.domains.identity.router import get_verified_claims
from app.domains.patients.protection import (
    decrypt_json,
    decrypt_administrative_document,
    encrypt_json,
    encrypt_administrative_document,
    encrypt_value,
    identifier_digest,
)
from app.domains.patients.schemas import (
    AdministrativeDocumentOut,
    AdministrativeDocumentType,
    AdministrativeFileOut,
    DocumentRule,
    EmergencyContactOut,
    PatientCreate,
    PatientDetail,
    PatientDocumentRulesUpdate,
    PatientPage,
    PatientSummary,
    PatientUpdate,
)

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])
DOCUMENT_RULES_SETTING = "patients.document_rules"
MAX_ADMINISTRATIVE_DOCUMENT_BYTES = 10 * 1024 * 1024
ADMINISTRATIVE_DOCUMENT_CONTENT_TYPES = {
    "application/pdf": (b"%PDF-", {".pdf"}),
    "image/jpeg": (b"\xff\xd8\xff", {".jpg", ".jpeg"}),
    "image/png": (b"\x89PNG\r\n\x1a\n", {".png"}),
}
DEFAULT_DOCUMENT_RULES = [
    {
        "identifier_type": "cedula_ec",
        "min_length": 10,
        "max_length": 10,
        "character_set": "digits",
        "checksum_algorithm": "ec_cedula",
        "is_active": True,
    },
    {
        "identifier_type": "passport",
        "min_length": 5,
        "max_length": 20,
        "character_set": "uppercase_alphanumeric",
        "checksum_algorithm": "none",
        "is_active": True,
    },
]


def _patient_context(
    claims: dict[str, Any],
    tenant_id: UUID | None,
) -> AuthorizationContext:
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID is required",
        )
    context = load_authorization_context(claims, tenant_id)
    if "patients:manage" not in context.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient management permission is required",
        )
    return context


def _administrative_file_context(
    claims: dict[str, Any],
    tenant_id: UUID | None,
    site_id: UUID | None,
) -> AuthorizationContext:
    if tenant_id is None or site_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID and X-Site-ID are required",
        )
    context = load_authorization_context(claims, tenant_id, site_id)
    if "patients:manage" not in context.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient management permission is required",
        )
    return context


def _tenant_id(context: AuthorizationContext) -> UUID:
    if context.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context is required",
        )
    return context.tenant_id


def _site_id(context: AuthorizationContext) -> UUID:
    if context.tenant_id is None or context.site_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site context is required",
        )
    return context.site_id


def _administrative_file_detail(
    session: Session,
    administrative_file: AdministrativeFile,
) -> AdministrativeFileOut:
    documents = session.scalars(
        select(AdministrativeDocument)
        .where(
            AdministrativeDocument.tenant_id == administrative_file.tenant_id,
            AdministrativeDocument.administrative_file_id == administrative_file.id,
        )
        .order_by(AdministrativeDocument.created_at, AdministrativeDocument.id)
    ).all()
    return AdministrativeFileOut(
        id=administrative_file.id,
        site_id=administrative_file.site_id,
        patient_id=administrative_file.patient_id,
        record_code=administrative_file.record_code,
        created_at=administrative_file.created_at,
        documents=[
            AdministrativeDocumentOut.model_validate(document)
            for document in documents
        ],
    )


def _validate_administrative_document(
    file_name: str,
    content_type: str | None,
    content: bytes,
) -> tuple[str, str]:
    safe_name = file_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if (
        not safe_name
        or len(safe_name) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in safe_name)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document filename is invalid",
        )
    normalized_type = (content_type or "").casefold()
    allowed = ADMINISTRATIVE_DOCUMENT_CONTENT_TYPES.get(normalized_type)
    extension = "." + safe_name.rsplit(".", 1)[-1].casefold() if "." in safe_name else ""
    if (
        allowed is None
        or extension not in allowed[1]
        or not content.startswith(allowed[0])
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only valid PDF, JPEG, and PNG documents are accepted",
        )
    return safe_name, normalized_type


def _document_rules(
    session: Session,
    tenant_id: UUID,
) -> list[DocumentRule]:
    setting = session.scalar(
        select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == DOCUMENT_RULES_SETTING,
        )
    )
    raw_rules = (
        setting.value.get("rules")
        if setting is not None
        else DEFAULT_DOCUMENT_RULES
    )
    if not isinstance(raw_rules, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Patient document rules are misconfigured",
        )
    try:
        return [DocumentRule.model_validate(rule) for rule in raw_rules]
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Patient document rules are misconfigured",
        ) from exc


def _active_document_rule(
    session: Session,
    tenant_id: UUID,
    identifier_type: str,
) -> DocumentRule:
    rule = next(
        (
            rule
            for rule in _document_rules(session, tenant_id)
            if rule.identifier_type == identifier_type and rule.is_active
        ),
        None,
    )
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This identification type is not enabled for the establishment",
        )
    return rule


def _validate_document(rule: DocumentRule, value: str) -> str:
    normalized = re.sub(r"[\s-]", "", value).upper()
    if not rule.min_length <= len(normalized) <= rule.max_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identification length does not match the configured rule",
        )
    patterns = {
        "digits": r"[0-9]+",
        "alphanumeric": r"[A-Z0-9]+",
        "uppercase_alphanumeric": r"[A-Z0-9]+",
    }
    if not re.fullmatch(patterns[rule.character_set], normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identification characters do not match the configured rule",
        )
    if rule.checksum_algorithm == "ec_cedula":
        if normalized[0:2] not in {f"{province:02d}" for province in range(1, 25)} | {"30"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ecuadorian identity document is invalid",
            )
        if int(normalized[2]) > 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ecuadorian identity document is invalid",
            )
        total = 0
        for index, character in enumerate(normalized[:9]):
            digit = int(character)
            if index % 2 == 0:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        check_digit = (10 - total % 10) % 10
        if check_digit != int(normalized[9]):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ecuadorian identity document is invalid",
            )
    return normalized


def _audit(
    session: Session,
    context: AuthorizationContext,
    *,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    changed_fields: list[str],
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=context.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            event_data={"changed_fields": sorted(set(changed_fields))},
        )
    )


def _insert_identifier(
    session: Session,
    *,
    tenant_id: UUID,
    patient_id: UUID,
    identifier_type: str,
    normalized_value: str,
    digest: str,
) -> None:
    try:
        with session.begin_nested():
            session.add(
                PatientIdentifier(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    identifier_type=identifier_type,
                    encrypted_value=encrypt_value(normalized_value),
                    lookup_digest=digest,
                    value_last_four=normalized_value[-4:],
                    is_primary=True,
                )
            )
            session.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint != (
            "uq_patient_identifiers_tenant_id_identifier_type_lookup_digest"
        ):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this identification already exists",
        ) from exc


def _require_patient(
    session: Session,
    tenant_id: UUID,
    patient_id: UUID,
) -> Patient:
    patient = session.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant_id,
            Patient.id == patient_id,
        )
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _patient_detail(session: Session, patient: Patient) -> PatientDetail:
    contact = (
        decrypt_json(patient.contact_data_encrypted)
        if patient.contact_data_encrypted is not None
        else {}
    )
    identifier = session.scalar(
        select(PatientIdentifier)
        .where(
            PatientIdentifier.tenant_id == patient.tenant_id,
            PatientIdentifier.patient_id == patient.id,
            PatientIdentifier.is_primary.is_(True),
        )
        .order_by(PatientIdentifier.created_at)
        .limit(1)
    )
    if identifier is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Patient identification record is missing",
        )
    emergency_rows = session.scalars(
        select(PatientEmergencyContact)
        .where(
            PatientEmergencyContact.tenant_id == patient.tenant_id,
            PatientEmergencyContact.patient_id == patient.id,
        )
        .order_by(PatientEmergencyContact.created_at, PatientEmergencyContact.id)
    ).all()
    emergency_contacts = []
    for row in emergency_rows:
        data = decrypt_json(row.encrypted_data)
        emergency_contacts.append(
            EmergencyContactOut(
                id=row.id,
                name=data["name"],
                relationship=data["relationship"],
                phone=data["phone"],
                email=data.get("email"),
            )
        )
    return PatientDetail(
        id=patient.id,
        tenant_id=patient.tenant_id,
        patient_number=patient.patient_number,
        given_name=patient.given_name,
        family_name=patient.family_name,
        birth_date=patient.birth_date,
        status=patient.status,
        identifier_type=identifier.identifier_type,
        identifier_last_four=identifier.value_last_four,
        phone=contact.get("phone"),
        email=contact.get("email"),
        address=contact.get("address"),
        emergency_contacts=emergency_contacts,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


def _masked_identifier(identifier: PatientIdentifier | None) -> tuple[str, str | None]:
    if identifier is None:
        return "", None
    return identifier.identifier_type, identifier.value_last_four


@router.get("/document-rules", response_model=list[DocumentRule])
def get_document_rules(
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> list[DocumentRule]:
    context = _patient_context(claims, tenant_id)
    active_tenant_id = _tenant_id(context)
    with tenant_session(active_tenant_id) as session:
        return _document_rules(session, active_tenant_id)


@router.put("/document-rules", response_model=list[DocumentRule])
def update_document_rules(
    payload: PatientDocumentRulesUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> list[DocumentRule]:
    context = _patient_context(claims, tenant_id)
    if (
        "administrator" not in context.role_codes
        or "tenant:manage" not in context.permission_codes
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator permission is required to change document rules",
        )
    active_tenant_id = _tenant_id(context)
    rules = [rule.model_dump(mode="json") for rule in payload.rules]
    with tenant_session(active_tenant_id) as session:
        setting = session.scalar(
            select(TenantSetting).where(
                TenantSetting.tenant_id == active_tenant_id,
                TenantSetting.key == DOCUMENT_RULES_SETTING,
            )
        )
        if setting is None:
            setting = TenantSetting(
                id=uuid4(),
                tenant_id=active_tenant_id,
                key=DOCUMENT_RULES_SETTING,
                value={"rules": rules},
            )
            session.add(setting)
        else:
            setting.value = {"rules": rules}
        session.flush()
        _audit(
            session,
            context,
            tenant_id=active_tenant_id,
            entity_type="tenant_setting",
            entity_id=setting.id,
            action="configure_document_rules",
            changed_fields=["document_rules"],
        )
    return payload.rules


@router.get("/records", response_model=PatientPage)
def search_patients(
    q: str = Query(min_length=1, max_length=120),
    document_type: str | None = Query(default=None, min_length=2, max_length=32),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> PatientPage:
    context = _patient_context(claims, tenant_id)
    active_tenant_id = _tenant_id(context)
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    name_pattern = f"%{escaped}%"
    with tenant_session(active_tenant_id) as session:
        document_match = None
        if document_type is not None:
            rule = _active_document_rule(
                session,
                active_tenant_id,
                document_type.casefold(),
            )
            normalized = _validate_document(rule, q)
            digest = identifier_digest(rule.identifier_type, normalized)
            document_match = (
                select(PatientIdentifier.id)
                .where(
                    PatientIdentifier.tenant_id == active_tenant_id,
                    PatientIdentifier.patient_id == Patient.id,
                    PatientIdentifier.identifier_type == rule.identifier_type,
                    PatientIdentifier.lookup_digest == digest,
                )
                .exists()
            )
        filters = [
            Patient.given_name.ilike(name_pattern, escape="\\"),
            Patient.family_name.ilike(name_pattern, escape="\\"),
        ]
        if document_match is not None:
            filters.append(document_match)
        base = select(Patient).where(
            Patient.tenant_id == active_tenant_id,
            or_(*filters),
        )
        total = session.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0
        patients = session.scalars(
            base.order_by(Patient.family_name, Patient.given_name, Patient.id)
            .limit(limit)
            .offset(offset)
        ).all()
        patient_ids = [patient.id for patient in patients]
        identifiers = session.scalars(
            select(PatientIdentifier)
            .where(
                PatientIdentifier.tenant_id == active_tenant_id,
                PatientIdentifier.patient_id.in_(patient_ids),
            )
            .order_by(
                PatientIdentifier.is_primary.desc(),
                PatientIdentifier.created_at,
            )
        ).all() if patient_ids else []
        identifier_by_patient: dict[UUID, PatientIdentifier] = {}
        for identifier in identifiers:
            identifier_by_patient.setdefault(identifier.patient_id, identifier)
        items = []
        for patient in patients:
            identifier = identifier_by_patient.get(patient.id)
            identifier_type, last_four = _masked_identifier(identifier)
            items.append(
                PatientSummary(
                    id=patient.id,
                    tenant_id=patient.tenant_id,
                    patient_number=patient.patient_number,
                    given_name=patient.given_name,
                    family_name=patient.family_name,
                    birth_date=patient.birth_date,
                    status=patient.status,
                    identifier_type=identifier_type,
                    identifier_last_four=last_four,
                )
            )
        return PatientPage(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/records",
    response_model=PatientDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_patient(
    payload: PatientCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> PatientDetail:
    context = _patient_context(claims, tenant_id)
    active_tenant_id = _tenant_id(context)
    with tenant_session(active_tenant_id) as session:
        rule = _active_document_rule(
            session,
            active_tenant_id,
            payload.identifier_type,
        )
        normalized_identifier = _validate_document(rule, payload.identifier_value)
        digest = identifier_digest(rule.identifier_type, normalized_identifier)
        existing = session.scalar(
            select(PatientIdentifier.id).where(
                PatientIdentifier.tenant_id == active_tenant_id,
                PatientIdentifier.identifier_type == rule.identifier_type,
                PatientIdentifier.lookup_digest == digest,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A patient with this identification already exists",
            )

        patient = Patient(
            id=uuid4(),
            tenant_id=active_tenant_id,
            patient_number=f"MG-{uuid4().hex[:16].upper()}",
            given_name=payload.given_name,
            family_name=payload.family_name,
            birth_date=payload.birth_date,
            contact_data_encrypted=encrypt_json(
                {
                    "phone": payload.phone,
                    "email": payload.email,
                    "address": payload.address,
                }
            ),
        )
        session.add(patient)
        session.flush()
        _insert_identifier(
            session,
            tenant_id=active_tenant_id,
            patient_id=patient.id,
            identifier_type=rule.identifier_type,
            normalized_value=normalized_identifier,
            digest=digest,
        )
        for emergency_contact in payload.emergency_contacts:
            session.add(
                PatientEmergencyContact(
                    id=uuid4(),
                    tenant_id=active_tenant_id,
                    patient_id=patient.id,
                    encrypted_data=encrypt_json(
                        emergency_contact.model_dump(mode="json")
                    ),
                )
            )
        _audit(
            session,
            context,
            tenant_id=active_tenant_id,
            entity_type="patient",
            entity_id=patient.id,
            action="create",
            changed_fields=[
                "identification",
                "given_name",
                "family_name",
                "birth_date",
                "contact",
                "emergency_contacts",
            ],
        )
        session.flush()
        return _patient_detail(session, patient)


@router.get("/records/{patient_id}", response_model=PatientDetail)
def get_patient(
    patient_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> PatientDetail:
    context = _patient_context(claims, tenant_id)
    active_tenant_id = _tenant_id(context)
    with tenant_session(active_tenant_id) as session:
        patient = _require_patient(session, active_tenant_id, patient_id)
        return _patient_detail(session, patient)


@router.patch("/records/{patient_id}", response_model=PatientDetail)
def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
) -> PatientDetail:
    context = _patient_context(claims, tenant_id)
    active_tenant_id = _tenant_id(context)
    changes = payload.model_dump(exclude_unset=True)
    with tenant_session(active_tenant_id) as session:
        patient = _require_patient(session, active_tenant_id, patient_id)
        changed_fields = list(changes)
        identifier_type = changes.get("identifier_type")
        identifier_value = changes.get("identifier_value")
        if identifier_type is not None and identifier_value is not None:
            rule = _active_document_rule(
                session,
                active_tenant_id,
                identifier_type,
            )
            normalized_identifier = _validate_document(rule, identifier_value)
            digest = identifier_digest(rule.identifier_type, normalized_identifier)
            existing = session.scalar(
                select(PatientIdentifier.id).where(
                    PatientIdentifier.tenant_id == active_tenant_id,
                    PatientIdentifier.identifier_type == rule.identifier_type,
                    PatientIdentifier.lookup_digest == digest,
                    PatientIdentifier.patient_id != patient.id,
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A patient with this identification already exists",
                )
            identifiers = session.scalars(
                select(PatientIdentifier).where(
                    PatientIdentifier.tenant_id == active_tenant_id,
                    PatientIdentifier.patient_id == patient.id,
                    PatientIdentifier.is_primary.is_(True),
                )
            ).all()
            unchanged_identifier = any(
                identifier.identifier_type == rule.identifier_type
                and identifier.lookup_digest == digest
                for identifier in identifiers
            )
            if not unchanged_identifier:
                if identifiers:
                    primary_identifier = identifiers[0]
                    primary_identifier.identifier_type = rule.identifier_type
                    primary_identifier.encrypted_value = encrypt_value(
                        normalized_identifier
                    )
                    primary_identifier.lookup_digest = digest
                    primary_identifier.value_last_four = normalized_identifier[-4:]
                else:
                    _insert_identifier(
                        session,
                        tenant_id=active_tenant_id,
                        patient_id=patient.id,
                        identifier_type=rule.identifier_type,
                        normalized_value=normalized_identifier,
                        digest=digest,
                    )

        contact_keys = {"phone", "email", "address"} & set(changes)
        if contact_keys:
            contact = (
                decrypt_json(patient.contact_data_encrypted)
                if patient.contact_data_encrypted is not None
                else {"phone": None, "email": None, "address": None}
            )
            for key in contact_keys:
                contact[key] = changes[key]
            patient.contact_data_encrypted = encrypt_json(contact)
        for field in ("given_name", "family_name", "birth_date"):
            if field in changes:
                setattr(patient, field, changes[field])

        if "emergency_contacts" in payload.model_fields_set:
            for emergency_contact in session.scalars(
                select(PatientEmergencyContact).where(
                    PatientEmergencyContact.tenant_id == active_tenant_id,
                    PatientEmergencyContact.patient_id == patient.id,
                )
            ).all():
                session.delete(emergency_contact)
            for emergency_contact in payload.emergency_contacts or []:
                session.add(
                    PatientEmergencyContact(
                        id=uuid4(),
                        tenant_id=active_tenant_id,
                        patient_id=patient.id,
                        encrypted_data=encrypt_json(
                            emergency_contact.model_dump(mode="json")
                        ),
                    )
                )

        _audit(
            session,
            context,
            tenant_id=active_tenant_id,
            entity_type="patient",
            entity_id=patient.id,
            action="correct",
            changed_fields=changed_fields,
        )
        session.flush()
        return _patient_detail(session, patient)


@router.post(
    "/administrative-files/{patient_id}/open",
    response_model=AdministrativeFileOut,
    status_code=status.HTTP_201_CREATED,
)
def open_administrative_file(
    patient_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
    site_id: UUID | None = Header(default=None, alias="X-Site-ID"),
) -> AdministrativeFileOut:
    context = _administrative_file_context(claims, tenant_id, site_id)
    active_tenant_id = _tenant_id(context)
    active_site_id = _site_id(context)
    with tenant_session(active_tenant_id) as session:
        _require_patient(session, active_tenant_id, patient_id)
        site = session.scalar(
            select(Site).where(
                Site.tenant_id == active_tenant_id,
                Site.id == active_site_id,
                Site.is_active.is_(True),
            )
        )
        if site is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )
        insert_result = session.execute(
            pg_insert(AdministrativeFile)
            .values(
                id=uuid4(),
                tenant_id=active_tenant_id,
                site_id=active_site_id,
                patient_id=patient_id,
                record_code=f"EXP-{site.code.upper()}-{uuid4().hex[:12].upper()}",
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "site_id", "patient_id"]
            )
        )
        administrative_file = session.scalar(
            select(AdministrativeFile).where(
                AdministrativeFile.tenant_id == active_tenant_id,
                AdministrativeFile.site_id == active_site_id,
                AdministrativeFile.patient_id == patient_id,
            )
        )
        if administrative_file is None:
            raise RuntimeError("Administrative file could not be opened")
        if insert_result.rowcount:
            _audit(
                session,
                context,
                tenant_id=active_tenant_id,
                entity_type="patient_administrative_file",
                entity_id=administrative_file.id,
                action="open",
                changed_fields=["record_code"],
            )
        session.flush()
        return _administrative_file_detail(session, administrative_file)


@router.get(
    "/administrative-files/{patient_id}",
    response_model=AdministrativeFileOut,
)
def get_administrative_file(
    patient_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
    site_id: UUID | None = Header(default=None, alias="X-Site-ID"),
) -> AdministrativeFileOut:
    context = _administrative_file_context(claims, tenant_id, site_id)
    active_tenant_id = _tenant_id(context)
    with tenant_session(active_tenant_id) as session:
        administrative_file = session.scalar(
            select(AdministrativeFile).where(
                AdministrativeFile.tenant_id == active_tenant_id,
                AdministrativeFile.site_id == _site_id(context),
                AdministrativeFile.patient_id == patient_id,
            )
        )
        if administrative_file is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Administrative file not found",
            )
        return _administrative_file_detail(session, administrative_file)


@router.post(
    "/administrative-files/{file_id}/documents",
    response_model=AdministrativeFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_administrative_document(
    file_id: UUID,
    document_type: AdministrativeDocumentType = Form(),
    document: UploadFile = File(),
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
    site_id: UUID | None = Header(default=None, alias="X-Site-ID"),
) -> AdministrativeFileOut:
    context = _administrative_file_context(claims, tenant_id, site_id)
    active_tenant_id = _tenant_id(context)
    content = await document.read(MAX_ADMINISTRATIVE_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAX_ADMINISTRATIVE_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Documents must be between 1 byte and 10 MiB",
        )
    file_name, content_type = _validate_administrative_document(
        document.filename or "",
        document.content_type,
        content,
    )
    with tenant_session(active_tenant_id) as session:
        administrative_file = session.scalar(
            select(AdministrativeFile).where(
                AdministrativeFile.tenant_id == active_tenant_id,
                AdministrativeFile.site_id == _site_id(context),
                AdministrativeFile.id == file_id,
            )
        )
        if administrative_file is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Administrative file not found",
            )
        session.add(
            AdministrativeDocument(
                id=uuid4(),
                tenant_id=active_tenant_id,
                administrative_file_id=administrative_file.id,
                document_type=document_type,
                file_name=file_name,
                content_type=content_type,
                size_bytes=len(content),
                sha256_digest=hashlib.sha256(content).hexdigest(),
                encrypted_content=encrypt_administrative_document(content),
            )
        )
        _audit(
            session,
            context,
            tenant_id=active_tenant_id,
            entity_type="patient_administrative_file",
            entity_id=administrative_file.id,
            action="attach_document",
            changed_fields=["documents"],
        )
        session.flush()
        return _administrative_file_detail(session, administrative_file)


@router.get("/administrative-files/documents/{document_id}/download")
def download_administrative_document(
    document_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
    site_id: UUID | None = Header(default=None, alias="X-Site-ID"),
) -> Response:
    context = _administrative_file_context(claims, tenant_id, site_id)
    active_tenant_id = _tenant_id(context)
    with tenant_session(active_tenant_id) as session:
        row = session.execute(
            select(AdministrativeDocument)
            .join(
                AdministrativeFile,
                (AdministrativeFile.tenant_id == AdministrativeDocument.tenant_id)
                & (
                    AdministrativeFile.id
                    == AdministrativeDocument.administrative_file_id
                ),
            )
            .where(
                AdministrativeDocument.tenant_id == active_tenant_id,
                AdministrativeDocument.id == document_id,
                AdministrativeFile.site_id == _site_id(context),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Administrative document not found",
            )
        content = decrypt_administrative_document(row.encrypted_content)
        filename = quote(row.file_name, safe="")
        return Response(
            content=content,
            media_type=row.content_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )


__all__ = ["router"]
