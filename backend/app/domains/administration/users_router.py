from __future__ import annotations

import logging
from datetime import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Membership,
    Role,
    Site,
    Specialty,
    TenantSpecialty,
    User,
)
from app.db.session import tenant_session
from app.domains.administration.schemas import (
    DoctorAvailabilityCreate,
    DoctorAvailabilityOut,
    DoctorAvailabilityUpdate,
    DoctorInvite,
    DoctorPage,
    DoctorOut,
    DoctorSpecialtiesUpdate,
    DoctorUpdate,
    ManagedRoleOut,
    ManagedUserOut,
    ManagedUserPage,
    MembershipStatusUpdate,
    SiteRoleUpdate,
    UserInvite,
)
from app.domains.identity.authorization import (
    AuthorizationContext,
    load_authorization_context,
)
from app.domains.identity.keycloak_admin import (
    KeycloakAdminError,
    create_identity,
    delete_identity,
)
from app.domains.identity.models import membership_roles, membership_site_roles
from app.domains.identity.router import get_verified_claims

router = APIRouter(prefix="/api/v1/admin", tags=["user and physician administration"])
ASSIGNABLE_SITE_ROLES = frozenset({"doctor", "service", "receptionist"})


def _management_context(
    claims: dict[str, Any],
    tenant_id: UUID,
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id)
    is_platform_admin = (
        "superadmin" in context.role_codes
        and "platform:manage" in context.permission_codes
    )
    is_tenant_admin = (
        "administrator" in context.role_codes
        and "tenant:manage" in context.permission_codes
    )
    if not (is_platform_admin or is_tenant_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator permission is required",
        )
    if "users:manage" not in context.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User management permission is required",
        )
    return context


def _audit(
    session: Session,
    context: AuthorizationContext,
    *,
    tenant_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    event_data: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=context.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            event_data=event_data or {},
        )
    )


def _require_site(session: Session, tenant_id: UUID, site_id: UUID) -> Site:
    site = session.scalar(
        select(Site).where(
            Site.tenant_id == tenant_id,
            Site.id == site_id,
            Site.is_active.is_(True),
        )
    )
    if site is None:
        raise HTTPException(status_code=404, detail="Active site not found")
    return site


def _require_membership(
    session: Session,
    tenant_id: UUID,
    membership_id: UUID,
) -> Membership:
    membership = session.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.id == membership_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    return membership


def _validate_site_role_codes(role_codes: list[str]) -> None:
    if not set(role_codes).issubset(ASSIGNABLE_SITE_ROLES):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only doctor, service, and receptionist roles can be assigned to a site",
        )


def _site_role_ids(session: Session, role_codes: list[str]) -> dict[str, UUID]:
    roles = session.scalars(
        select(Role).where(Role.code.in_(role_codes))
    ).all()
    role_ids = {role.code: role.id for role in roles}
    if set(role_ids) != set(role_codes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more requested roles are not configured",
        )
    return role_ids


@router.get(
    "/tenants/{tenant_id}/managed-roles",
    response_model=list[ManagedRoleOut],
)
def list_managed_roles(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[dict[str, str]]:
    _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        roles = session.scalars(
            select(Role)
            .where(Role.code.in_(ASSIGNABLE_SITE_ROLES))
            .order_by(Role.name)
        ).all()
        return [{"code": role.code, "name": role.name} for role in roles]


@router.get(
    "/tenants/{tenant_id}/users",
    response_model=ManagedUserPage,
)
def list_managed_users(
    tenant_id: UUID,
    site_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    role_code: str | None = None,
    membership_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|suspended)$",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ManagedUserPage:
    _management_context(claims, tenant_id)
    pattern = None
    if q is not None:
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_q}%"

    with tenant_session(tenant_id) as session:
        if site_id is not None:
            _require_site(session, tenant_id, site_id)
        base = select(Membership, User).join(User, User.id == Membership.user_id).where(
            Membership.tenant_id == tenant_id
        )
        if membership_status is not None:
            base = base.where(Membership.status == membership_status)
        if pattern is not None:
            base = base.where(
                or_(
                    User.display_name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                )
            )
        if role_code:
            tenant_role_match = exists(
                select(1)
                .select_from(membership_roles)
                .join(Role, Role.id == membership_roles.c.role_id)
                .where(
                    membership_roles.c.tenant_id == tenant_id,
                    membership_roles.c.membership_id == Membership.id,
                    Role.code == role_code,
                )
            )
            site_role_query = (
                select(1)
                .select_from(membership_site_roles)
                .join(Role, Role.id == membership_site_roles.c.role_id)
                .where(
                    membership_site_roles.c.tenant_id == tenant_id,
                    membership_site_roles.c.membership_id == Membership.id,
                    Role.code == role_code,
                )
            )
            if site_id is not None:
                site_role_query = site_role_query.where(
                    membership_site_roles.c.site_id == site_id
                )
            site_role_match = exists(site_role_query)
            base = base.where(or_(tenant_role_match, site_role_match))

        total = session.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0
        rows = session.execute(
            base.order_by(User.display_name, Membership.id)
            .limit(limit)
            .offset(offset)
        ).all()
        items = []
        for membership, user in rows:
            role_ids = set(
                session.scalars(
                    select(membership_roles.c.role_id).where(
                        membership_roles.c.tenant_id == tenant_id,
                        membership_roles.c.membership_id == membership.id,
                    )
                ).all()
            )
            if site_id is not None:
                role_ids.update(
                    session.scalars(
                        select(membership_site_roles.c.role_id).where(
                            membership_site_roles.c.tenant_id == tenant_id,
                            membership_site_roles.c.site_id == site_id,
                            membership_site_roles.c.membership_id == membership.id,
                        )
                    ).all()
                )
            role_codes = sorted(
                session.scalars(select(Role.code).where(Role.id.in_(role_ids))).all()
            ) if role_ids else []
            items.append(
                ManagedUserOut(
                    membership_id=membership.id,
                    user_id=user.id,
                    identity_provider_subject=user.identity_provider_subject,
                    email=user.email,
                    display_name=user.display_name,
                    is_active=user.is_active,
                    membership_status=membership.status,
                    role_codes=role_codes,
                )
            )
        return ManagedUserPage(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=ManagedUserOut,
    status_code=status.HTTP_201_CREATED,
)
def invite_managed_user(
    tenant_id: UUID,
    payload: UserInvite,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ManagedUserOut:
    context = _management_context(claims, tenant_id)
    _validate_site_role_codes(payload.role_codes)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, payload.site_id)
        _site_role_ids(session, payload.role_codes)
    try:
        subject = create_identity(
            payload.email,
            payload.display_name,
            require_mfa="doctor" in payload.role_codes,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    user_id = uuid4()
    membership_id = uuid4()
    try:
        with tenant_session(tenant_id) as session:
            _require_site(session, tenant_id, payload.site_id)
            role_ids = _site_role_ids(session, payload.role_codes)
            session.execute(
                insert(User).values(
                    id=user_id,
                    identity_provider_subject=str(subject),
                    email=payload.email,
                    display_name=payload.display_name,
                    is_active=True,
                )
            )
            membership = Membership(
                id=membership_id,
                tenant_id=tenant_id,
                user_id=user_id,
                status="active",
            )
            session.add(membership)
            session.flush()
            session.execute(
                membership_site_roles.insert(),
                [
                    {
                        "tenant_id": tenant_id,
                        "site_id": payload.site_id,
                        "membership_id": membership_id,
                        "role_id": role_id,
                    }
                    for role_id in role_ids.values()
                ],
            )
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="invite",
                entity_type="membership",
                entity_id=membership_id,
                event_data={
                    "site_id": str(payload.site_id),
                    "role_codes": payload.role_codes,
                },
            )
            return ManagedUserOut(
                membership_id=membership_id,
                user_id=user_id,
                identity_provider_subject=str(subject),
                email=payload.email,
                display_name=payload.display_name,
                is_active=True,
                membership_status="active",
                role_codes=sorted(role_ids),
            )
    except IntegrityError as exc:
        try:
            delete_identity(subject)
        except KeycloakAdminError as cleanup_error:
            raise HTTPException(
                status_code=503,
                detail="User persistence failed and the pending identity could not be removed",
            ) from cleanup_error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user conflicts with existing tenant data",
        ) from exc
    except HTTPException:
        try:
            delete_identity(subject)
        except KeycloakAdminError as cleanup_error:
            raise HTTPException(
                status_code=503,
                detail="User persistence failed and the pending identity could not be removed",
            ) from cleanup_error
        raise
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).error(
            "Managed user persistence transaction failed (%s)",
            type(exc).__name__,
        )
        try:
            delete_identity(subject)
        except KeycloakAdminError as cleanup_error:
            raise HTTPException(
                status_code=503,
                detail="User persistence failed and the pending identity could not be removed",
            ) from cleanup_error
        raise HTTPException(
            status_code=503,
            detail="User persistence failed",
        ) from exc


@router.put(
    "/tenants/{tenant_id}/users/{membership_id}/sites/{site_id}/roles",
    response_model=ManagedUserOut,
)
def update_site_roles(
    tenant_id: UUID,
    membership_id: UUID,
    site_id: UUID,
    payload: SiteRoleUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ManagedUserOut:
    context = _management_context(claims, tenant_id)
    _validate_site_role_codes(payload.role_codes)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, site_id)
        membership = _require_membership(session, tenant_id, membership_id)
        role_ids = _site_role_ids(session, payload.role_codes)
        session.execute(
            membership_site_roles.delete().where(
                membership_site_roles.c.tenant_id == tenant_id,
                membership_site_roles.c.site_id == site_id,
                membership_site_roles.c.membership_id == membership_id,
            )
        )
        if role_ids:
            session.execute(
                membership_site_roles.insert(),
                [
                    {
                        "tenant_id": tenant_id,
                        "site_id": site_id,
                        "membership_id": membership_id,
                        "role_id": role_id,
                    }
                    for role_id in role_ids.values()
                ],
            )
        user = session.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update_site_roles",
            entity_type="membership",
            entity_id=membership_id,
            event_data={"site_id": str(site_id), "role_codes": payload.role_codes},
        )
        tenant_role_codes = session.scalars(
            select(Role.code)
            .join(membership_roles, membership_roles.c.role_id == Role.id)
            .where(
                membership_roles.c.tenant_id == tenant_id,
                membership_roles.c.membership_id == membership_id,
            )
        ).all()
        return ManagedUserOut(
            membership_id=membership.id,
            user_id=user.id,
            identity_provider_subject=user.identity_provider_subject,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            membership_status=membership.status,
            role_codes=sorted(set(tenant_role_codes) | set(payload.role_codes)),
        )


@router.patch(
    "/tenants/{tenant_id}/users/{membership_id}/status",
    response_model=ManagedUserOut,
)
def update_membership_status(
    tenant_id: UUID,
    membership_id: UUID,
    payload: MembershipStatusUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ManagedUserOut:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        membership = _require_membership(session, tenant_id, membership_id)
        membership.status = payload.status
        user = session.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update_membership_status",
            entity_type="membership",
            entity_id=membership_id,
            event_data={"status": payload.status},
        )
        tenant_role_codes = session.scalars(
            select(Role.code)
            .join(membership_roles, membership_roles.c.role_id == Role.id)
            .where(
                membership_roles.c.tenant_id == tenant_id,
                membership_roles.c.membership_id == membership_id,
            )
        ).all()
        return ManagedUserOut(
            membership_id=membership.id,
            user_id=user.id,
            identity_provider_subject=user.identity_provider_subject,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            membership_status=membership.status,
            role_codes=sorted(tenant_role_codes),
        )


def _require_doctor(
    session: Session,
    tenant_id: UUID,
    doctor_id: UUID,
) -> Doctor:
    doctor = session.scalar(
        select(Doctor).where(Doctor.tenant_id == tenant_id, Doctor.id == doctor_id)
    )
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


def _validate_specialties(
    session: Session,
    tenant_id: UUID,
    specialty_ids: list[UUID],
) -> dict[UUID, Specialty]:
    specialties = session.scalars(
        select(Specialty)
        .join(TenantSpecialty, TenantSpecialty.specialty_id == Specialty.id)
        .where(
            TenantSpecialty.tenant_id == tenant_id,
            TenantSpecialty.is_active.is_(True),
            Specialty.is_active.is_(True),
            Specialty.id.in_(specialty_ids),
        )
    ).all()
    by_id = {specialty.id: specialty for specialty in specialties}
    if set(by_id) != set(specialty_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All specialties must be active for this tenant",
        )
    return by_id


def _membership_has_doctor_role(
    session: Session,
    tenant_id: UUID,
    membership_id: UUID,
    site_id: UUID,
) -> bool:
    tenant_role = session.scalar(
        select(membership_roles.c.role_id)
        .join(Role, Role.id == membership_roles.c.role_id)
        .where(
            membership_roles.c.tenant_id == tenant_id,
            membership_roles.c.membership_id == membership_id,
            Role.code == "doctor",
        )
        .limit(1)
    )
    if tenant_role is not None:
        return True
    return session.scalar(
        select(membership_site_roles.c.role_id)
        .join(Role, Role.id == membership_site_roles.c.role_id)
        .where(
            membership_site_roles.c.tenant_id == tenant_id,
            membership_site_roles.c.site_id == site_id,
            membership_site_roles.c.membership_id == membership_id,
            Role.code == "doctor",
        )
        .limit(1)
    ) is not None


@router.get("/tenants/{tenant_id}/doctors", response_model=DoctorPage)
def list_doctors(
    tenant_id: UUID,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    specialty_id: UUID | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorPage:
    _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        query = (
            select(Doctor, Membership, User)
            .join(
                Membership,
                and_(
                    Membership.tenant_id == Doctor.tenant_id,
                    Membership.id == Doctor.membership_id,
                ),
            )
            .join(User, User.id == Membership.user_id)
            .where(Doctor.tenant_id == tenant_id)
        )
        if q:
            escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped_q}%"
            query = query.where(
                or_(
                    User.display_name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                    Doctor.license_number.ilike(pattern, escape="\\"),
                )
            )
        if specialty_id is not None:
            query = query.join(
                DoctorSpecialty,
                and_(
                    DoctorSpecialty.tenant_id == Doctor.tenant_id,
                    DoctorSpecialty.doctor_id == Doctor.id,
                ),
            ).where(DoctorSpecialty.specialty_id == specialty_id)
        if is_active is not None:
            query = query.where(Doctor.is_active.is_(is_active))
        total = session.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        ) or 0
        rows = session.execute(
            query.order_by(User.display_name, Doctor.id).limit(limit).offset(offset)
        ).all()
        doctor_ids = [doctor.id for doctor, _, _ in rows]
        specialty_rows = session.execute(
            select(DoctorSpecialty.doctor_id, DoctorSpecialty.specialty_id)
            .where(
                DoctorSpecialty.tenant_id == tenant_id,
                DoctorSpecialty.doctor_id.in_(doctor_ids),
            )
            .order_by(DoctorSpecialty.is_primary.desc(), DoctorSpecialty.specialty_id)
        ).all() if doctor_ids else []
        specialties_by_doctor: dict[UUID, list[UUID]] = {}
        primary_by_doctor: dict[UUID, UUID] = {}
        for doctor_id, specialty_id_value in specialty_rows:
            specialties_by_doctor.setdefault(doctor_id, []).append(specialty_id_value)
            if doctor_id not in primary_by_doctor:
                primary_by_doctor[doctor_id] = specialty_id_value
        items = [
            DoctorOut(
                id=doctor.id,
                tenant_id=doctor.tenant_id,
                membership_id=doctor.membership_id,
                email=user.email,
                display_name=user.display_name,
                license_number=doctor.license_number,
                is_active=doctor.is_active,
                specialty_ids=specialties_by_doctor.get(doctor.id, []),
                primary_specialty_id=primary_by_doctor.get(
                    doctor.id, doctor.specialty_id
                ),
            )
            for doctor, _, user in rows
        ]
        return DoctorPage(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/tenants/{tenant_id}/doctors",
    response_model=DoctorOut,
    status_code=status.HTTP_201_CREATED,
)
def create_doctor(
    tenant_id: UUID,
    payload: DoctorInvite,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorOut:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, payload.site_id)
        membership = _require_membership(session, tenant_id, payload.membership_id)
        if membership.status != "active":
            raise HTTPException(status_code=409, detail="Membership is suspended")
        if not _membership_has_doctor_role(
            session,
            tenant_id,
            membership.id,
            payload.site_id,
        ):
            raise HTTPException(
                status_code=422,
                detail="The membership must have the doctor role at this site",
            )
        _validate_specialties(session, tenant_id, payload.specialty_ids)
        doctor_id = uuid4()
        primary_specialty_id = payload.specialty_ids[0]
        doctor = Doctor(
            id=doctor_id,
            tenant_id=tenant_id,
            membership_id=membership.id,
            specialty_id=primary_specialty_id,
            license_number=payload.license_number,
            is_active=True,
        )
        session.add(doctor)
        session.flush()
        session.add_all(
            DoctorSpecialty(
                id=uuid4(),
                tenant_id=tenant_id,
                doctor_id=doctor_id,
                specialty_id=specialty_id,
                is_primary=specialty_id == primary_specialty_id,
            )
            for specialty_id in payload.specialty_ids
        )
        user = session.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="create",
            entity_type="doctor",
            entity_id=doctor_id,
            event_data={
                "site_id": str(payload.site_id),
                "specialty_ids": [str(value) for value in payload.specialty_ids],
            },
        )
        return DoctorOut(
            id=doctor.id,
            tenant_id=tenant_id,
            membership_id=membership.id,
            email=user.email,
            display_name=user.display_name,
            license_number=doctor.license_number,
            is_active=doctor.is_active,
            specialty_ids=payload.specialty_ids,
            primary_specialty_id=primary_specialty_id,
        )


@router.patch(
    "/tenants/{tenant_id}/doctors/{doctor_id}",
    response_model=DoctorOut,
)
def update_doctor(
    tenant_id: UUID,
    doctor_id: UUID,
    payload: DoctorUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorOut:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        doctor = _require_doctor(session, tenant_id, doctor_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(doctor, key, value)
        associations = session.scalars(
            select(DoctorSpecialty).where(
                DoctorSpecialty.tenant_id == tenant_id,
                DoctorSpecialty.doctor_id == doctor_id,
            )
        ).all()
        primary = next(
            (association.specialty_id for association in associations if association.is_primary),
            doctor.specialty_id,
        )
        membership = _require_membership(session, tenant_id, doctor.membership_id)
        user = session.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update",
            entity_type="doctor",
            entity_id=doctor_id,
            event_data=payload.model_dump(exclude_unset=True),
        )
        return DoctorOut(
            id=doctor.id,
            tenant_id=tenant_id,
            membership_id=doctor.membership_id,
            email=user.email,
            display_name=user.display_name,
            license_number=doctor.license_number,
            is_active=doctor.is_active,
            specialty_ids=[association.specialty_id for association in associations],
            primary_specialty_id=primary,
        )


@router.put(
    "/tenants/{tenant_id}/doctors/{doctor_id}/specialties",
    response_model=DoctorOut,
)
def update_doctor_specialties(
    tenant_id: UUID,
    doctor_id: UUID,
    payload: DoctorSpecialtiesUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorOut:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        doctor = _require_doctor(session, tenant_id, doctor_id)
        _validate_specialties(session, tenant_id, payload.specialty_ids)
        session.execute(
            DoctorSpecialty.__table__.delete().where(
                DoctorSpecialty.tenant_id == tenant_id,
                DoctorSpecialty.doctor_id == doctor_id,
            )
        )
        session.add_all(
            DoctorSpecialty(
                id=uuid4(),
                tenant_id=tenant_id,
                doctor_id=doctor_id,
                specialty_id=specialty_id,
                is_primary=specialty_id == payload.primary_specialty_id,
            )
            for specialty_id in payload.specialty_ids
        )
        doctor.specialty_id = payload.primary_specialty_id
        membership = _require_membership(session, tenant_id, doctor.membership_id)
        user = session.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update_specialties",
            entity_type="doctor",
            entity_id=doctor_id,
            event_data={
                "specialty_ids": [str(value) for value in payload.specialty_ids],
                "primary_specialty_id": str(payload.primary_specialty_id),
            },
        )
        return DoctorOut(
            id=doctor.id,
            tenant_id=tenant_id,
            membership_id=doctor.membership_id,
            email=user.email,
            display_name=user.display_name,
            license_number=doctor.license_number,
            is_active=doctor.is_active,
            specialty_ids=payload.specialty_ids,
            primary_specialty_id=payload.primary_specialty_id,
        )


def _validate_availability_overlap(
    session: Session,
    *,
    tenant_id: UUID,
    doctor_id: UUID,
    site_id: UUID,
    weekday: int,
    starts_at: time,
    ends_at: time,
    exclude_id: UUID | None = None,
) -> None:
    overlap = select(DoctorAvailability.id).where(
        DoctorAvailability.tenant_id == tenant_id,
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.site_id == site_id,
        DoctorAvailability.weekday == weekday,
        DoctorAvailability.starts_at < ends_at,
        DoctorAvailability.ends_at > starts_at,
    )
    if exclude_id is not None:
        overlap = overlap.where(DoctorAvailability.id != exclude_id)
    if session.scalar(overlap.limit(1)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Availability intervals cannot overlap",
        )


@router.get(
    "/tenants/{tenant_id}/doctors/{doctor_id}/availability",
    response_model=list[DoctorAvailabilityOut],
)
def list_doctor_availability(
    tenant_id: UUID,
    doctor_id: UUID,
    site_id: UUID | None = None,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[DoctorAvailability]:
    _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_doctor(session, tenant_id, doctor_id)
        query = select(DoctorAvailability).where(
            DoctorAvailability.tenant_id == tenant_id,
            DoctorAvailability.doctor_id == doctor_id,
        )
        if site_id is not None:
            _require_site(session, tenant_id, site_id)
            query = query.where(DoctorAvailability.site_id == site_id)
        return list(
            session.scalars(
                query.order_by(
                    DoctorAvailability.site_id,
                    DoctorAvailability.weekday,
                    DoctorAvailability.starts_at,
                )
            ).all()
        )


@router.post(
    "/tenants/{tenant_id}/doctors/{doctor_id}/availability",
    response_model=DoctorAvailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def create_doctor_availability(
    tenant_id: UUID,
    doctor_id: UUID,
    payload: DoctorAvailabilityCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorAvailability:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        doctor = _require_doctor(session, tenant_id, doctor_id)
        if not doctor.is_active:
            raise HTTPException(status_code=409, detail="Doctor is inactive")
        _require_site(session, tenant_id, payload.site_id)
        _validate_availability_overlap(
            session,
            tenant_id=tenant_id,
            doctor_id=doctor_id,
            site_id=payload.site_id,
            weekday=payload.weekday,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        availability = DoctorAvailability(
            id=uuid4(),
            tenant_id=tenant_id,
            doctor_id=doctor_id,
            **payload.model_dump(),
        )
        session.add(availability)
        session.flush()
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="create",
            entity_type="doctor_availability",
            entity_id=availability.id,
            event_data={"site_id": str(payload.site_id), "weekday": payload.weekday},
        )
        return availability


@router.patch(
    "/tenants/{tenant_id}/doctors/{doctor_id}/availability/{availability_id}",
    response_model=DoctorAvailabilityOut,
)
def update_doctor_availability(
    tenant_id: UUID,
    doctor_id: UUID,
    availability_id: UUID,
    payload: DoctorAvailabilityUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorAvailability:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_doctor(session, tenant_id, doctor_id)
        availability = session.scalar(
            select(DoctorAvailability).where(
                DoctorAvailability.tenant_id == tenant_id,
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.id == availability_id,
            )
        )
        if availability is None:
            raise HTTPException(status_code=404, detail="Availability not found")
        changes = payload.model_dump(exclude_unset=True)
        weekday = changes.get("weekday", availability.weekday)
        starts_at = changes.get("starts_at", availability.starts_at)
        ends_at = changes.get("ends_at", availability.ends_at)
        _validate_availability_overlap(
            session,
            tenant_id=tenant_id,
            doctor_id=doctor_id,
            site_id=availability.site_id,
            weekday=weekday,
            starts_at=starts_at,
            ends_at=ends_at,
            exclude_id=availability.id,
        )
        for key, value in changes.items():
            setattr(availability, key, value)
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update",
            entity_type="doctor_availability",
            entity_id=availability.id,
            event_data=payload.model_dump(mode="json", exclude_unset=True),
        )
        return availability


@router.delete(
    "/tenants/{tenant_id}/doctors/{doctor_id}/availability/{availability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_doctor_availability(
    tenant_id: UUID,
    doctor_id: UUID,
    availability_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Response:
    context = _management_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_doctor(session, tenant_id, doctor_id)
        availability = session.scalar(
            select(DoctorAvailability).where(
                DoctorAvailability.tenant_id == tenant_id,
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.id == availability_id,
            )
        )
        if availability is None:
            raise HTTPException(status_code=404, detail="Availability not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="doctor_availability",
            entity_id=availability_id,
            event_data={"site_id": str(availability.site_id)},
        )
        session.delete(availability)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
