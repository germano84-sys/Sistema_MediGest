import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AdministrativeDocument,
    AdministrativeFile,
    ClinicRoom,
    Patient,
    PatientIdentifier,
    Site,
    SiteHours,
    Tenant,
    TenantSetting,
)
from app.db.session import engine as application_engine
from app.db.session import tenant_session


@dataclass(frozen=True)
class TenantFixture:
    tenant_a: UUID
    tenant_b: UUID
    patient_a: UUID
    patient_b: UUID
    identifier_a: UUID
    identifier_b: UUID


@pytest.fixture
def tenant_fixture() -> TenantFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL to run PostgreSQL RLS tests")

    if application_engine.url.username != "medigest_app":
        pytest.fail("RLS integration tests must connect as the medigest_app role")

    ids = TenantFixture(
        tenant_a=uuid4(),
        tenant_b=uuid4(),
        patient_a=uuid4(),
        patient_b=uuid4(),
        identifier_a=uuid4(),
        identifier_b=uuid4(),
    )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    with migration_engine.begin() as connection:
        for tenant_id, suffix in ((ids.tenant_a, "a"), (ids.tenant_b, "b")):
            connection.execute(
                Tenant.__table__.insert().values(
                    id=tenant_id,
                    name=f"Synthetic tenant {suffix.upper()}",
                    slug=f"synthetic-rls-{suffix}-{tenant_id.hex[:8]}",
                )
            )
        for tenant_id, patient_id, identifier_id, suffix in (
            (ids.tenant_a, ids.patient_a, ids.identifier_a, "a"),
            (ids.tenant_b, ids.patient_b, ids.identifier_b, "b"),
        ):
            connection.execute(
                Patient.__table__.insert().values(
                    id=patient_id,
                    tenant_id=tenant_id,
                    patient_number=f"TEST-{suffix}-{patient_id.hex[:8]}",
                    given_name="Synthetic",
                    family_name=f"Person {suffix.upper()}",
                )
            )
            connection.execute(
                PatientIdentifier.__table__.insert().values(
                    id=identifier_id,
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    identifier_type="test",
                    encrypted_value=b"synthetic-only",
                    lookup_digest=identifier_id.hex * 2,
                    value_last_four="0000",
                )
            )

    try:
        yield ids
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                PatientIdentifier.__table__.delete().where(
                    PatientIdentifier.tenant_id.in_([ids.tenant_a, ids.tenant_b])
                )
            )
            connection.execute(
                Patient.__table__.delete().where(
                    Patient.tenant_id.in_([ids.tenant_a, ids.tenant_b])
                )
            )
            connection.execute(
                Tenant.__table__.delete().where(
                    Tenant.id.in_([ids.tenant_a, ids.tenant_b])
                )
            )
        migration_engine.dispose()


def test_tenant_session_lists_only_own_patients_and_identifiers(
    tenant_fixture: TenantFixture,
) -> None:
    with tenant_session(tenant_fixture.tenant_a) as session:
        patients = session.scalars(select(Patient)).all()
        identifiers = session.scalars(select(PatientIdentifier)).all()

        assert [patient.id for patient in patients] == [tenant_fixture.patient_a]
        assert [identifier.id for identifier in identifiers] == [
            tenant_fixture.identifier_a
        ]
        assert session.get(Patient, tenant_fixture.patient_b) is None
        assert session.get(PatientIdentifier, tenant_fixture.identifier_b) is None


def test_update_of_another_tenant_patient_changes_no_rows(
    tenant_fixture: TenantFixture,
) -> None:
    with tenant_session(tenant_fixture.tenant_a) as session:
        result = session.execute(
            update(Patient)
            .where(Patient.id == tenant_fixture.patient_b)
            .values(family_name="Tampered")
        )
        assert result.rowcount == 0

    settings = get_settings()
    migration_engine = create_engine(settings.migration_database_url, pool_pre_ping=True)
    try:
        with migration_engine.connect() as connection:
            family_name = connection.scalar(
                select(Patient.family_name).where(
                    Patient.id == tenant_fixture.patient_b
                )
            )
        assert family_name == "Person B"
    finally:
        migration_engine.dispose()


def test_insert_for_another_tenant_is_rejected(
    tenant_fixture: TenantFixture,
) -> None:
    with pytest.raises(DBAPIError):
        with tenant_session(tenant_fixture.tenant_a) as session:
            session.add(
                Patient(
                    id=uuid4(),
                    tenant_id=tenant_fixture.tenant_b,
                    patient_number="TEST-CROSS-TENANT",
                    given_name="Synthetic",
                    family_name="Rejected",
                )
            )
            session.flush()


def test_unsigned_or_forged_tenant_context_exposes_no_rows(
    tenant_fixture: TenantFixture,
) -> None:
    with Session(application_engine) as session, session.begin():
        session.execute(
            text(
                "SELECT set_config('app.tenant_id', :tenant_id, true), "
                "set_config('app.tenant_signature', :signature, true)"
            ),
            {
                "tenant_id": str(tenant_fixture.tenant_b),
                "signature": "0" * 64,
            },
        )
        assert session.scalars(select(Patient)).all() == []

    with pytest.raises(DBAPIError):
        with Session(application_engine) as session, session.begin():
            session.execute(
                text(
                    "SELECT app_private.set_tenant_context("
                    "CAST(:tenant_id AS uuid), :signature)"
                ),
                {
                    "tenant_id": str(tenant_fixture.tenant_b),
                    "signature": "0" * 64,
                },
            )


def test_application_role_cannot_bypass_rls_or_read_context_secret() -> None:
    with Session(application_engine) as session, session.begin():
        role = session.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        assert role == (False, False, False, False)

        owner = session.scalar(
            text(
                "SELECT pg_get_userbyid(relowner) "
                "FROM pg_class WHERE oid = 'public.patients'::regclass"
            )
        )
        assert owner != "medigest_app"

    with pytest.raises(DBAPIError):
        with Session(application_engine) as session, session.begin():
            session.execute(
                text("SELECT secret FROM app_private.tenant_context_keys")
            )

    with pytest.raises(DBAPIError):
        with Session(application_engine) as session, session.begin():
            session.execute(text("SET LOCAL row_security = off"))
            session.scalars(select(Patient)).all()



def test_tenant_context_is_cleared_after_transaction(
    tenant_fixture: TenantFixture,
) -> None:
    with tenant_session(tenant_fixture.tenant_a) as session:
        assert session.scalar(text("SELECT app_private.current_tenant_id()")) == (
            tenant_fixture.tenant_a
        )

    with Session(application_engine) as session, session.begin():
        assert session.scalar(text("SELECT app_private.current_tenant_id()")) is None
        assert session.scalars(select(Patient)).all() == []


def test_administration_rows_are_forced_and_tenant_scoped(
    tenant_fixture: TenantFixture,
) -> None:
    ids = tenant_fixture
    site_a, site_b = uuid4(), uuid4()
    room_a, room_b = uuid4(), uuid4()
    hours_a, hours_b = uuid4(), uuid4()
    setting_a, setting_b = uuid4(), uuid4()
    file_a, file_b = uuid4(), uuid4()
    document_a, document_b = uuid4(), uuid4()
    migration_engine = create_engine(
        get_settings().migration_database_url,
        pool_pre_ping=True,
    )
    with migration_engine.begin() as connection:
        connection.execute(
            Site.__table__.insert(),
            [
                {
                    "id": site_a,
                    "tenant_id": ids.tenant_a,
                    "code": "SITE-A",
                    "name": "Synthetic site A",
                },
                {
                    "id": site_b,
                    "tenant_id": ids.tenant_b,
                    "code": "SITE-B",
                    "name": "Synthetic site B",
                },
            ],
        )
        connection.execute(
            ClinicRoom.__table__.insert(),
            [
                {
                    "id": room_a,
                    "tenant_id": ids.tenant_a,
                    "site_id": site_a,
                    "code": "ROOM-A",
                    "name": "Synthetic room A",
                },
                {
                    "id": room_b,
                    "tenant_id": ids.tenant_b,
                    "site_id": site_b,
                    "code": "ROOM-B",
                    "name": "Synthetic room B",
                },
            ],
        )
        connection.execute(
            SiteHours.__table__.insert(),
            [
                {
                    "id": hours_a,
                    "tenant_id": ids.tenant_a,
                    "site_id": site_a,
                    "weekday": 0,
                    "opens_at": "08:00",
                    "closes_at": "17:00",
                },
                {
                    "id": hours_b,
                    "tenant_id": ids.tenant_b,
                    "site_id": site_b,
                    "weekday": 0,
                    "opens_at": "08:00",
                    "closes_at": "17:00",
                },
            ],
        )
        connection.execute(
            TenantSetting.__table__.insert(),
            [
                {
                    "id": setting_a,
                    "tenant_id": ids.tenant_a,
                    "key": "display.name",
                    "value": {"name": "Synthetic A"},
                },
                {
                    "id": setting_b,
                    "tenant_id": ids.tenant_b,
                    "key": "display.name",
                    "value": {"name": "Synthetic B"},
                },
            ],
        )
        connection.execute(
            AdministrativeFile.__table__.insert(),
            [
                {
                    "id": file_a,
                    "tenant_id": ids.tenant_a,
                    "site_id": site_a,
                    "patient_id": ids.patient_a,
                    "record_code": "EXP-SITE-A-SYNTHETIC",
                },
                {
                    "id": file_b,
                    "tenant_id": ids.tenant_b,
                    "site_id": site_b,
                    "patient_id": ids.patient_b,
                    "record_code": "EXP-SITE-B-SYNTHETIC",
                },
            ],
        )
        connection.execute(
            AdministrativeDocument.__table__.insert(),
            [
                {
                    "id": document_a,
                    "tenant_id": ids.tenant_a,
                    "administrative_file_id": file_a,
                    "document_type": "administrative_form",
                    "file_name": "synthetic-a.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 1,
                    "sha256_digest": "a" * 64,
                    "encrypted_content": b"synthetic-encrypted-a",
                },
                {
                    "id": document_b,
                    "tenant_id": ids.tenant_b,
                    "administrative_file_id": file_b,
                    "document_type": "administrative_form",
                    "file_name": "synthetic-b.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 1,
                    "sha256_digest": "b" * 64,
                    "encrypted_content": b"synthetic-encrypted-b",
                },
            ],
        )

    try:
        with tenant_session(ids.tenant_a) as session:
            assert [row.id for row in session.scalars(select(ClinicRoom)).all()] == [
                room_a
            ]
            assert [row.id for row in session.scalars(select(SiteHours)).all()] == [
                hours_a
            ]
            assert [
                row.id for row in session.scalars(select(TenantSetting)).all()
            ] == [setting_a]
            assert [
                row.id for row in session.scalars(select(AdministrativeFile)).all()
            ] == [file_a]
            assert [
                row.id
                for row in session.scalars(select(AdministrativeDocument)).all()
            ] == [document_a]
            hidden_update = session.execute(
                update(AdministrativeFile)
                .where(AdministrativeFile.id == file_b)
                .values(record_code="TAMPERED")
            )
            assert hidden_update.rowcount == 0

        with migration_engine.connect() as connection:
            rls_state = connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = "
                    "'public.patient_administrative_files'::regclass"
                )
            ).one()
            document_rls_state = connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = "
                    "'public.patient_administrative_documents'::regclass"
                )
            ).one()
        assert rls_state == (True, True)
        assert document_rls_state == (True, True)

        with pytest.raises(DBAPIError):
            with tenant_session(ids.tenant_a) as session:
                session.add(
                    TenantSetting(
                        id=uuid4(),
                        tenant_id=ids.tenant_b,
                        key="unauthorized.write",
                        value={"value": "blocked"},
                    )
                )
                session.flush()

        with Session(application_engine) as session, session.begin():
            session.execute(
                text("SELECT set_config('app.platform_signature', :signature, true)"),
                {"signature": "0" * 64},
            )
            assert session.scalars(select(Tenant)).all() == []
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                AdministrativeDocument.__table__.delete().where(
                    AdministrativeDocument.id.in_([document_a, document_b])
                )
            )
            connection.execute(
                AdministrativeFile.__table__.delete().where(
                    AdministrativeFile.id.in_([file_a, file_b])
                )
            )
            connection.execute(
                TenantSetting.__table__.delete().where(
                    TenantSetting.id.in_([setting_a, setting_b])
                )
            )
            connection.execute(
                SiteHours.__table__.delete().where(
                    SiteHours.id.in_([hours_a, hours_b])
                )
            )
            connection.execute(
                ClinicRoom.__table__.delete().where(
                    ClinicRoom.id.in_([room_a, room_b])
                )
            )
            connection.execute(
                Site.__table__.delete().where(Site.id.in_([site_a, site_b]))
            )
        migration_engine.dispose()
