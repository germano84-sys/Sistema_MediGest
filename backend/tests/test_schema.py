from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import UniqueConstraint, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.db.models import Appointment, Patient, Site, Tenant
from app.db.models import AdministrativeDocument, AdministrativeFile

EXPECTED_TABLES = {
    "appointments",
    "appointment_history",
    "patient_administrative_documents",
    "patient_administrative_files",
    "audit_events",
    "clinic_rooms",
    "clinical_records",
    "diagnoses",
    "doctors",
    "doctor_availability",
    "doctor_specialties",
    "encounters",
    "medical_orders",
    "membership_roles",
    "membership_site_roles",
    "memberships",
    "patient_emergency_contacts",
    "patient_identifiers",
    "patients",
    "permissions",
    "prescriptions",
    "role_permissions",
    "roles",
    "services",
    "site_holidays",
    "sites",
    "site_hours",
    "specialties",
    "tenants",
    "tenant_settings",
    "tenant_specialties",
    "users",
}


def test_model_registry_contains_initial_schema() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_orm_relationships_are_configured() -> None:
    configure_mappers()


def test_tenant_scoped_tables_include_tenant_constraints() -> None:
    for table_name in EXPECTED_TABLES - {
        "audit_events",
        "membership_roles",
        "membership_site_roles",
        "permissions",
        "role_permissions",
        "roles",
        "specialties",
        "tenants",
        "users",
    }:
        table = Base.metadata.tables[table_name]
        assert "tenant_id" in table.c
        assert any(
            fk.target_fullname == "tenants.id"
            for fk in table.c.tenant_id.foreign_keys
        )
        assert any(
            isinstance(constraint, UniqueConstraint)
            and constraint.columns.keys() == ["tenant_id", "id"]
            for constraint in table.constraints
        )


def test_patient_identifiers_are_not_stored_as_plaintext() -> None:
    columns = Base.metadata.tables["patient_identifiers"].c

    assert "encrypted_value" in columns
    assert "lookup_digest" in columns
    assert "identifier_value" not in columns


def test_appointments_store_ordered_administrative_reception_times() -> None:
    columns = Appointment.__table__.c
    assert {
        "arrival_confirmed_at",
        "checked_in_at",
        "queue_entered_at",
    } <= set(columns.keys())
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Appointment.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    assert "checked_in_at IS NULL OR arrival_confirmed_at IS NOT NULL" in constraints[
        "ck_appointments_checkin_requires_arrival"
    ]
    assert "queue_entered_at IS NULL OR checked_in_at IS NOT NULL" in constraints[
        "ck_appointments_queue_requires_checkin"
    ]


def test_appointments_store_service_workflow_without_clinical_fields() -> None:
    columns = Appointment.__table__.c
    assert {
        "service_status",
        "service_room_id",
        "preparation_started_at",
        "ready_at",
        "attention_started_at",
        "attention_completed_at",
    } <= set(columns.keys())
    assert not {
        "clinical_notes",
        "diagnosis",
        "prescription",
    }.intersection(columns.keys())
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Appointment.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    assert "service_status IN ('pending', 'preparing', 'ready', 'completed')" in (
        constraints["ck_appointments_service_status"]
    )


def test_administrative_files_are_site_scoped_and_documents_encrypted() -> None:
    file_table = AdministrativeFile.__table__
    document_columns = AdministrativeDocument.__table__.c

    assert {"tenant_id", "site_id", "patient_id", "record_code"} <= set(
        file_table.c.keys()
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.columns.keys() == ["tenant_id", "site_id", "record_code"]
        for constraint in file_table.constraints
    )
    assert "encrypted_content" in document_columns
    assert "content" not in document_columns
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in AdministrativeDocument.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    assert "document_type IN" in constraints["ck_patient_administrative_documents_authorized_type"]


def test_composite_foreign_key_rejects_cross_tenant_appointment() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()
    site_a_id = uuid4()
    patient_b_id = uuid4()
    starts_at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            Tenant.__table__.insert(),
            [
                {"id": tenant_a_id, "name": "Test tenant A", "slug": "test-tenant-a"},
                {"id": tenant_b_id, "name": "Test tenant B", "slug": "test-tenant-b"},
            ],
        )
        connection.execute(
            Site.__table__.insert(),
            {"id": site_a_id, "tenant_id": tenant_a_id, "code": "SITE-A", "name": "Test site A"},
        )
        connection.execute(
            Patient.__table__.insert(),
            {
                "id": patient_b_id,
                "tenant_id": tenant_b_id,
                "patient_number": "TEST-001",
                "given_name": "Test",
                "family_name": "Person",
            },
        )

        with pytest.raises(IntegrityError):
            connection.execute(
                Appointment.__table__.insert(),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_a_id,
                    "site_id": site_a_id,
                    "patient_id": patient_b_id,
                    "starts_at": starts_at,
                    "ends_at": starts_at + timedelta(minutes=30),
                },
            )
