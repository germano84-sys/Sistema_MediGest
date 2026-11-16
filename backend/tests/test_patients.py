import os
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, update

from app.db.models import (
    AdministrativeDocument,
    AdministrativeFile,
    AuditEvent,
    Membership,
    Patient,
    PatientEmergencyContact,
    PatientIdentifier,
    Role,
    Site,
    Tenant,
    User,
)
from app.db.session import tenant_session
from app.domains.identity.models import membership_roles
from app.domains.identity.router import get_verified_claims
from app.domains.patients.protection import (
    encrypt_json,
    encrypt_value,
    identifier_digest,
    decrypt_administrative_document,
    encrypt_administrative_document,
)
from app.domains.patients.router import (
    _validate_administrative_document,
    _validate_document,
)
from app.domains.patients.schemas import DocumentRule
from app.main import app


@dataclass(frozen=True)
class PatientFixture:
    tenant_id: UUID
    other_tenant_id: UUID
    site_id: UUID
    subject: str
    other_patient_id: UUID


@pytest.fixture
def patient_fixture() -> PatientFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for PostgreSQL patient tests")

    fixture = PatientFixture(
        tenant_id=uuid4(),
        other_tenant_id=uuid4(),
        site_id=uuid4(),
        subject=f"patient-test-{uuid4().hex}",
        other_patient_id=uuid4(),
    )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    user_id = uuid4()
    membership_id = uuid4()
    other_identifier = "OTHER12345"

    with migration_engine.begin() as connection:
        receptionist_role_id = connection.scalar(
            select(Role.id).where(Role.code == "receptionist")
        )
        assert receptionist_role_id is not None, "RBAC roles must be seeded by Alembic"
        connection.execute(
            Tenant.__table__.insert(),
            [
                {
                    "id": fixture.tenant_id,
                    "name": "Synthetic patient tenant",
                    "slug": f"patient-{fixture.tenant_id.hex[:12]}",
                },
                {
                    "id": fixture.other_tenant_id,
                    "name": "Synthetic other patient tenant",
                    "slug": f"other-patient-{fixture.other_tenant_id.hex[:12]}",
                },
            ],
        )
        connection.execute(
            Site.__table__.insert().values(
                id=fixture.site_id,
                tenant_id=fixture.tenant_id,
                code="TEST-SITE",
                name="Synthetic test site",
            )
        )
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                identity_provider_subject=fixture.subject,
                email="patient-test@example.invalid",
                display_name="Synthetic Patient Clerk",
                is_active=True,
            )
        )
        connection.execute(
            Membership.__table__.insert().values(
                id=membership_id,
                tenant_id=fixture.tenant_id,
                user_id=user_id,
                status="active",
            )
        )
        connection.execute(
            membership_roles.insert().values(
                tenant_id=fixture.tenant_id,
                membership_id=membership_id,
                role_id=receptionist_role_id,
            )
        )
        connection.execute(
            Patient.__table__.insert().values(
                id=fixture.other_patient_id,
                tenant_id=fixture.other_tenant_id,
                patient_number="MG-SYNTHETIC-OTHER",
                given_name="Synthetic",
                family_name="Other",
                birth_date=date(1990, 1, 1),
                status="active",
            )
        )
        connection.execute(
            PatientIdentifier.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.other_tenant_id,
                patient_id=fixture.other_patient_id,
                identifier_type="passport",
                encrypted_value=encrypt_value(other_identifier),
                lookup_digest=identifier_digest("passport", other_identifier),
                value_last_four=other_identifier[-4:],
                is_primary=True,
            )
        )
        connection.execute(
            PatientEmergencyContact.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.other_tenant_id,
                patient_id=fixture.other_patient_id,
                encrypted_data=encrypt_json(
                    {
                        "name": "Synthetic Other Contact",
                        "relationship": "Friend",
                        "phone": "+593 96 000 0000",
                        "email": None,
                    }
                ),
            )
        )

    try:
        yield fixture
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                delete(AdministrativeDocument).where(
                    AdministrativeDocument.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                delete(AdministrativeFile).where(
                    AdministrativeFile.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                delete(AuditEvent).where(
                    AuditEvent.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                delete(PatientEmergencyContact).where(
                    PatientEmergencyContact.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                delete(PatientIdentifier).where(
                    PatientIdentifier.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                delete(Patient).where(
                    Patient.tenant_id.in_(
                        [fixture.tenant_id, fixture.other_tenant_id]
                    )
                )
            )
            connection.execute(
                membership_roles.delete().where(
                    membership_roles.c.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(Membership).where(Membership.tenant_id == fixture.tenant_id)
            )
            connection.execute(delete(Site).where(Site.id == fixture.site_id))
            connection.execute(
                delete(Tenant).where(
                    Tenant.id.in_([fixture.tenant_id, fixture.other_tenant_id])
                )
            )
            connection.execute(
                delete(User).where(
                    User.identity_provider_subject == fixture.subject
                )
            )
        migration_engine.dispose()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _client(subject: str) -> TestClient:
    claims = {
        "sub": subject,
        "email": "patient-test@example.invalid",
        "name": "Synthetic Patient Clerk",
    }
    app.dependency_overrides[get_verified_claims] = lambda: claims
    return TestClient(app)


def test_document_rules_validate_ecuadorian_identity_checksum() -> None:
    rule = DocumentRule(
        identifier_type="cedula_ec",
        min_length=10,
        max_length=10,
        character_set="digits",
        checksum_algorithm="ec_cedula",
    )

    assert _validate_document(rule, "0110000007") == "0110000007"
    with pytest.raises(HTTPException) as error:
        _validate_document(rule, "0110000008")
    assert error.value.status_code == 422


def test_administrative_document_validation_and_encryption() -> None:
    body = b"%PDF-1.7\nsynthetic administrative document"

    assert _validate_administrative_document(
        "proof.pdf",
        "application/pdf",
        body,
    ) == ("proof.pdf", "application/pdf")
    encrypted = encrypt_administrative_document(body)
    assert encrypted != body
    assert body not in encrypted
    assert decrypt_administrative_document(encrypted) == body

    with pytest.raises(HTTPException) as error:
        _validate_administrative_document(
            "proof.pdf",
            "application/pdf",
            b"not a PDF",
        )
    assert error.value.status_code == 415


def test_patient_registration_correction_and_tenant_isolation(
    patient_fixture: PatientFixture,
) -> None:
    fixture = patient_fixture
    with _client(fixture.subject) as client:
        headers = {"X-Tenant-ID": str(fixture.tenant_id)}
        rules = client.get("/api/v1/patients/document-rules", headers=headers)
        assert rules.status_code == 200, rules.text
        assert {rule["identifier_type"] for rule in rules.json()} == {
            "cedula_ec",
            "passport",
        }

        invalid_document = client.post(
            "/api/v1/patients/records",
            headers=headers,
            json={
                "identifier_type": "cedula_ec",
                "identifier_value": "0110000008",
                "given_name": "Synthetic",
                "family_name": "Invalid",
                "birth_date": "1990-01-01",
            },
        )
        assert invalid_document.status_code == 422

        created = client.post(
            "/api/v1/patients/records",
            headers=headers,
            json={
                "identifier_type": "passport",
                "identifier_value": "TEST12345",
                "given_name": "Synthetic",
                "family_name": "Patient",
                "birth_date": "1990-01-01",
                "phone": "+593 99 000 0000",
                "email": "synthetic@example.invalid",
                "address": "Synthetic test address",
                "emergency_contacts": [
                    {
                        "name": "Synthetic Contact",
                        "relationship": "Friend",
                        "phone": "+593 98 000 0000",
                        "email": None,
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        patient = created.json()
        patient_id = patient["id"]
        assert patient["identifier_last_four"] == "2345"
        assert patient["phone"] == "+593 99 000 0000"
        assert len(patient["emergency_contacts"]) == 1

        site_headers = {
            **headers,
            "X-Site-ID": str(fixture.site_id),
        }
        missing_site = client.post(
            f"/api/v1/patients/administrative-files/{patient_id}/open",
            headers=headers,
        )
        assert missing_site.status_code == 400
        opened_file = client.post(
            f"/api/v1/patients/administrative-files/{patient_id}/open",
            headers=site_headers,
        )
        assert opened_file.status_code == 201, opened_file.text
        administrative_file = opened_file.json()
        assert administrative_file["site_id"] == str(fixture.site_id)
        assert administrative_file["record_code"].startswith("EXP-TEST-SITE-")
        repeated_open = client.post(
            f"/api/v1/patients/administrative-files/{patient_id}/open",
            headers=site_headers,
        )
        assert repeated_open.status_code == 201
        assert repeated_open.json()["id"] == administrative_file["id"]

        document_content = b"%PDF-1.7\nsynthetic administrative document"
        uploaded = client.post(
            f"/api/v1/patients/administrative-files/{administrative_file['id']}/documents",
            headers=site_headers,
            data={"document_type": "administrative_form"},
            files={"document": ("form.pdf", document_content, "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        saved_document = uploaded.json()["documents"][0]
        assert saved_document["document_type"] == "administrative_form"
        assert saved_document["file_name"] == "form.pdf"
        assert saved_document["size_bytes"] == len(document_content)
        unauthorized_document_type = client.post(
            f"/api/v1/patients/administrative-files/{administrative_file['id']}/documents",
            headers=site_headers,
            data={"document_type": "clinical_document"},
            files={"document": ("form.pdf", document_content, "application/pdf")},
        )
        assert unauthorized_document_type.status_code == 422

        with tenant_session(fixture.tenant_id) as session:
            administrative_audit = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == fixture.tenant_id,
                    AuditEvent.entity_id == UUID(administrative_file["id"]),
                )
            ).all()
        assert {event.action for event in administrative_audit} == {
            "open",
            "attach_document",
        }
        assert all(
            set(event.event_data) == {"changed_fields"}
            for event in administrative_audit
        )

        downloaded = client.get(
            f"/api/v1/patients/administrative-files/documents/{saved_document['id']}/download",
            headers=site_headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == document_content
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert "attachment" in downloaded.headers["content-disposition"]

        assert client.post(
            "/api/v1/clinical/diagnoses",
            headers=site_headers,
            json={"code": "synthetic"},
        ).status_code == 404
        assert client.patch(
            f"/api/v1/clinical/encounters/{uuid4()}",
            headers=site_headers,
            json={"status": "completed"},
        ).status_code == 404

        duplicate = client.post(
            "/api/v1/patients/records",
            headers=headers,
            json={
                "identifier_type": "passport",
                "identifier_value": "TEST12345",
                "given_name": "Synthetic",
                "family_name": "Duplicate",
                "birth_date": "1991-01-01",
            },
        )
        assert duplicate.status_code == 409

        document_search = client.get(
            "/api/v1/patients/records",
            headers=headers,
            params={"q": "TEST12345", "document_type": "passport"},
        )
        assert document_search.status_code == 200, document_search.text
        assert document_search.json()["total"] == 1

        corrected = client.patch(
            f"/api/v1/patients/records/{patient_id}",
            headers=headers,
            json={
                "given_name": "Corrected",
                "phone": "+593 97 000 0000",
                "identifier_type": "passport",
                "identifier_value": "NEW12345",
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["given_name"] == "Corrected"
        assert corrected.json()["phone"] == "+593 97 000 0000"
        assert corrected.json()["identifier_last_four"] == "2345"
        old_document_search = client.get(
            "/api/v1/patients/records",
            headers=headers,
            params={"q": "TEST12345", "document_type": "passport"},
        )
        assert old_document_search.status_code == 200
        assert old_document_search.json()["total"] == 0
        new_document_search = client.get(
            "/api/v1/patients/records",
            headers=headers,
            params={"q": "NEW12345", "document_type": "passport"},
        )
        assert new_document_search.status_code == 200
        assert new_document_search.json()["total"] == 1

        other_patient = client.get(
            f"/api/v1/patients/records/{fixture.other_patient_id}",
            headers=headers,
        )
        assert other_patient.status_code == 404
        other_update = client.patch(
            f"/api/v1/patients/records/{fixture.other_patient_id}",
            headers=headers,
            json={"given_name": "Unauthorized"},
        )
        assert other_update.status_code == 404
        other_search = client.get(
            "/api/v1/patients/records",
            headers=headers,
            params={"q": "Other"},
        )
        assert other_search.status_code == 200
        assert other_search.json()["total"] == 0

        cross_tenant = client.get(
            "/api/v1/patients/records",
            headers={"X-Tenant-ID": str(fixture.other_tenant_id)},
            params={"q": "Other"},
        )
        assert cross_tenant.status_code == 403

        rule_update = client.put(
            "/api/v1/patients/document-rules",
            headers=headers,
            json={"rules": rules.json()},
        )
        assert rule_update.status_code == 403

    with tenant_session(fixture.tenant_id) as session:
        assert session.scalar(
            select(Patient.id).where(Patient.id == fixture.other_patient_id)
        ) is None
        assert session.scalar(
            select(PatientEmergencyContact.id).where(
                PatientEmergencyContact.patient_id == fixture.other_patient_id
            )
        ) is None
        result = session.execute(
            update(Patient)
            .where(Patient.id == fixture.other_patient_id)
            .values(given_name="Should Not Change")
        )
        assert result.rowcount == 0
        contact_update = session.execute(
            update(PatientEmergencyContact)
            .where(PatientEmergencyContact.patient_id == fixture.other_patient_id)
            .values(encrypted_data=encrypt_json({"changed": True}))
        )
        assert contact_update.rowcount == 0

    migration_url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    try:
        with migration_engine.connect() as connection:
            encrypted_document = connection.scalar(
                select(AdministrativeDocument.encrypted_content).where(
                    AdministrativeDocument.tenant_id == fixture.tenant_id,
                    AdministrativeDocument.administrative_file_id
                    == UUID(administrative_file["id"]),
                )
            )
            encrypted_identifier = connection.scalar(
                select(PatientIdentifier.encrypted_value).where(
                    PatientIdentifier.tenant_id == fixture.tenant_id,
                    PatientIdentifier.patient_id == UUID(patient_id),
                    PatientIdentifier.is_primary.is_(True),
                )
            )
            encrypted_contact = connection.scalar(
                select(Patient.contact_data_encrypted).where(
                    Patient.tenant_id == fixture.tenant_id,
                    Patient.id == UUID(patient_id),
                )
            )
            encrypted_emergency_contact = connection.scalar(
                select(PatientEmergencyContact.encrypted_data).where(
                    PatientEmergencyContact.tenant_id == fixture.tenant_id,
                    PatientEmergencyContact.patient_id == UUID(patient_id),
                )
            )
            audit_data = connection.scalars(
                select(AuditEvent.event_data).where(
                    AuditEvent.tenant_id == fixture.tenant_id,
                    AuditEvent.entity_id == UUID(patient_id),
                )
            ).all()
        assert encrypted_identifier is not None
        assert b"NEW12345" not in encrypted_identifier
        assert encrypted_contact is not None
        assert b"synthetic@example.invalid" not in encrypted_contact
        assert encrypted_emergency_contact is not None
        assert b"Synthetic Contact" not in encrypted_emergency_contact
        assert encrypted_document is not None
        assert document_content not in encrypted_document
        assert all(
            "synthetic@example.invalid" not in str(event)
            for event in audit_data
        )
        assert any(
            "given_name" in event.get("changed_fields", [])
            for event in audit_data
        )
    finally:
        migration_engine.dispose()
