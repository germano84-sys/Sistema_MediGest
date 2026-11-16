import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select

from app.db.models import (
    Appointment,
    ClinicalRecord,
    Diagnosis,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Encounter,
    Membership,
    MedicalOrder,
    Patient,
    Prescription,
    Role,
    Site,
    Specialty,
    Tenant,
    TenantSpecialty,
    User,
)
from app.domains.identity.models import membership_roles
from app.domains.identity.router import get_verified_claims
from app.main import app


@dataclass(frozen=True)
class DashboardFixture:
    tenant_id: UUID
    site_id: UUID
    other_site_id: UUID
    specialty_id: UUID
    other_specialty_id: UUID
    admin_subject: str
    doctor_subject: str
    other_doctor_subject: str
    clinical_record_id: UUID
    other_clinical_record_id: UUID
    start_date: date


@pytest.fixture
def dashboard_fixture() -> DashboardFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for dashboard API tests")

    fixture = DashboardFixture(
        tenant_id=uuid4(),
        site_id=uuid4(),
        other_site_id=uuid4(),
        specialty_id=uuid4(),
        other_specialty_id=uuid4(),
        admin_subject=f"dashboard-admin-{uuid4().hex}",
        doctor_subject=f"dashboard-doctor-{uuid4().hex}",
        other_doctor_subject=f"dashboard-doctor-{uuid4().hex}",
        clinical_record_id=uuid4(),
        other_clinical_record_id=uuid4(),
        start_date=date.today() - timedelta(days=2),
    )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    tenant_admin_role_id = None
    doctor_role_id = None
    admin_user_id, doctor_user_id, other_doctor_user_id = uuid4(), uuid4(), uuid4()
    admin_membership_id = uuid4()
    doctor_membership_id, other_doctor_membership_id = uuid4(), uuid4()
    doctor_id, other_doctor_id = uuid4(), uuid4()
    patient_id, other_patient_id = uuid4(), uuid4()
    clinical_record_id = fixture.clinical_record_id
    other_clinical_record_id = fixture.other_clinical_record_id
    appointment_ids = [uuid4() for _ in range(7)]
    encounter_ids = [uuid4() for _ in range(3)]
    diagnosis_id, prescription_id, order_id = uuid4(), uuid4(), uuid4()
    created_at = datetime.combine(
        fixture.start_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    with migration_engine.begin() as connection:
        tenant_admin_role_id = connection.scalar(
            select(Role.id).where(Role.code == "administrator")
        )
        doctor_role_id = connection.scalar(
            select(Role.id).where(Role.code == "doctor")
        )
        assert tenant_admin_role_id is not None
        assert doctor_role_id is not None
        connection.execute(
            Tenant.__table__.insert().values(
                id=fixture.tenant_id,
                name="Synthetic dashboard tenant",
                slug=f"dashboard-{fixture.tenant_id.hex[:12]}",
            )
        )
        connection.execute(
            Site.__table__.insert(),
            [
                {
                    "id": fixture.site_id,
                    "tenant_id": fixture.tenant_id,
                    "code": "DASH-SITE",
                    "name": "Synthetic dashboard site",
                    "is_active": True,
                },
                {
                    "id": fixture.other_site_id,
                    "tenant_id": fixture.tenant_id,
                    "code": "DASH-OTHER",
                    "name": "Synthetic other site",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            Specialty.__table__.insert(),
            [
                {
                    "id": fixture.specialty_id,
                    "code": f"DASH{fixture.specialty_id.hex[:8].upper()}",
                    "name": "Synthetic specialty A",
                    "is_active": True,
                },
                {
                    "id": fixture.other_specialty_id,
                    "code": f"DASH{fixture.other_specialty_id.hex[:8].upper()}",
                    "name": "Synthetic specialty B",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            TenantSpecialty.__table__.insert(),
            [
                {
                    "id": uuid4(),
                    "tenant_id": fixture.tenant_id,
                    "specialty_id": fixture.specialty_id,
                    "is_active": True,
                },
                {
                    "id": uuid4(),
                    "tenant_id": fixture.tenant_id,
                    "specialty_id": fixture.other_specialty_id,
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            User.__table__.insert(),
            [
                {
                    "id": admin_user_id,
                    "identity_provider_subject": fixture.admin_subject,
                    "email": "dashboard-admin@example.invalid",
                    "display_name": "Synthetic Dashboard Admin",
                    "is_active": True,
                },
                {
                    "id": doctor_user_id,
                    "identity_provider_subject": fixture.doctor_subject,
                    "email": "dashboard-doctor@example.invalid",
                    "display_name": "Synthetic Dashboard Doctor A",
                    "is_active": True,
                },
                {
                    "id": other_doctor_user_id,
                    "identity_provider_subject": fixture.other_doctor_subject,
                    "email": "dashboard-doctor-b@example.invalid",
                    "display_name": "Synthetic Dashboard Doctor B",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            Membership.__table__.insert(),
            [
                {
                    "id": admin_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": admin_user_id,
                    "status": "active",
                },
                {
                    "id": doctor_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": doctor_user_id,
                    "status": "active",
                },
                {
                    "id": other_doctor_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": other_doctor_user_id,
                    "status": "active",
                },
            ],
        )
        connection.execute(
            membership_roles.insert(),
            [
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": admin_membership_id,
                    "role_id": tenant_admin_role_id,
                },
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": doctor_membership_id,
                    "role_id": doctor_role_id,
                },
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": other_doctor_membership_id,
                    "role_id": doctor_role_id,
                },
            ],
        )
        connection.execute(
            Doctor.__table__.insert(),
            [
                {
                    "id": doctor_id,
                    "tenant_id": fixture.tenant_id,
                    "membership_id": doctor_membership_id,
                    "specialty_id": fixture.specialty_id,
                    "license_number": f"DASH-LIC-{doctor_id.hex[:12]}",
                    "is_active": True,
                },
                {
                    "id": other_doctor_id,
                    "tenant_id": fixture.tenant_id,
                    "membership_id": other_doctor_membership_id,
                    "specialty_id": fixture.other_specialty_id,
                    "license_number": f"DASH-LIC-{other_doctor_id.hex[:12]}",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            DoctorSpecialty.__table__.insert(),
            [
                {
                    "id": uuid4(),
                    "tenant_id": fixture.tenant_id,
                    "doctor_id": doctor_id,
                    "specialty_id": fixture.specialty_id,
                    "is_primary": True,
                },
                {
                    "id": uuid4(),
                    "tenant_id": fixture.tenant_id,
                    "doctor_id": other_doctor_id,
                    "specialty_id": fixture.other_specialty_id,
                    "is_primary": True,
                },
            ],
        )
        connection.execute(
            Patient.__table__.insert(),
            [
                {
                    "id": patient_id,
                    "tenant_id": fixture.tenant_id,
                    "patient_number": f"DASH-{patient_id.hex[:10]}",
                    "given_name": "Synthetic",
                    "family_name": "Patient A",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                {
                    "id": other_patient_id,
                    "tenant_id": fixture.tenant_id,
                    "patient_number": f"DASH-{other_patient_id.hex[:10]}",
                    "given_name": "Synthetic",
                    "family_name": "Patient B",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
            ],
        )
        connection.execute(
            ClinicalRecord.__table__.insert(),
            [
                {
                    "id": clinical_record_id,
                    "tenant_id": fixture.tenant_id,
                    "patient_id": patient_id,
                    "record_number": f"DASH-REC-{patient_id.hex[:10]}",
                    "status": "open",
                },
                {
                    "id": other_clinical_record_id,
                    "tenant_id": fixture.tenant_id,
                    "patient_id": other_patient_id,
                    "record_number": f"DASH-REC-{other_patient_id.hex[:10]}",
                    "status": "open",
                },
            ],
        )
        for doctor, site in (
            (doctor_id, fixture.site_id),
            (other_doctor_id, fixture.site_id),
        ):
            connection.execute(
                DoctorAvailability.__table__.insert().values(
                    id=uuid4(),
                    tenant_id=fixture.tenant_id,
                    doctor_id=doctor,
                    site_id=site,
                    weekday=fixture.start_date.weekday(),
                    starts_at="09:00",
                    ends_at="12:00",
                    is_available=True,
                )
            )
        appointment_rows = [
            (appointment_ids[0], doctor_id, patient_id, fixture.site_id, "completed"),
            (appointment_ids[1], doctor_id, patient_id, fixture.site_id, "scheduled"),
            (appointment_ids[2], doctor_id, patient_id, fixture.site_id, "cancelled"),
            (appointment_ids[3], doctor_id, patient_id, fixture.other_site_id, "completed"),
            (appointment_ids[4], other_doctor_id, other_patient_id, fixture.site_id, "completed"),
            (appointment_ids[5], other_doctor_id, other_patient_id, fixture.site_id, "scheduled"),
            (appointment_ids[6], doctor_id, patient_id, fixture.site_id, "checked_in"),
        ]
        appointment_start = created_at + timedelta(hours=9)
        connection.execute(
            Appointment.__table__.insert(),
            [
                {
                    "id": appointment_id,
                    "tenant_id": fixture.tenant_id,
                    "site_id": site_id,
                    "patient_id": current_patient_id,
                    "doctor_id": current_doctor_id,
                    "starts_at": appointment_start,
                    "ends_at": appointment_start + timedelta(minutes=30),
                    "status": appointment_status,
                    "arrival_confirmed_at": (
                        appointment_start - timedelta(minutes=5)
                        if appointment_status == "checked_in"
                        else None
                    ),
                    "checked_in_at": (
                        appointment_start - timedelta(minutes=3)
                        if appointment_status == "checked_in"
                        else None
                    ),
                    "queue_entered_at": (
                        appointment_start - timedelta(minutes=2)
                        if appointment_status == "checked_in"
                        else None
                    ),
                    "created_at": created_at,
                    "updated_at": created_at,
                }
                for appointment_id, current_doctor_id, current_patient_id, site_id, appointment_status
                in appointment_rows
            ],
        )
        connection.execute(
            Encounter.__table__.insert(),
            [
                {
                    "id": encounter_ids[0],
                    "tenant_id": fixture.tenant_id,
                    "patient_id": patient_id,
                    "clinical_record_id": clinical_record_id,
                    "appointment_id": appointment_ids[0],
                    "site_id": fixture.site_id,
                    "doctor_id": doctor_id,
                    "started_at": appointment_start,
                    "ended_at": appointment_start + timedelta(minutes=20),
                    "status": "completed",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                {
                    "id": encounter_ids[1],
                    "tenant_id": fixture.tenant_id,
                    "patient_id": patient_id,
                    "clinical_record_id": clinical_record_id,
                    "appointment_id": appointment_ids[3],
                    "site_id": fixture.other_site_id,
                    "doctor_id": doctor_id,
                    "started_at": appointment_start,
                    "ended_at": appointment_start + timedelta(minutes=20),
                    "status": "completed",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                {
                    "id": encounter_ids[2],
                    "tenant_id": fixture.tenant_id,
                    "patient_id": other_patient_id,
                    "clinical_record_id": other_clinical_record_id,
                    "appointment_id": appointment_ids[4],
                    "site_id": fixture.site_id,
                    "doctor_id": other_doctor_id,
                    "started_at": appointment_start,
                    "ended_at": appointment_start + timedelta(minutes=20),
                    "status": "completed",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
            ],
        )
        connection.execute(
            Diagnosis.__table__.insert().values(
                id=diagnosis_id,
                tenant_id=fixture.tenant_id,
                encounter_id=encounter_ids[0],
                code_system="synthetic",
                code="SYN-001",
                description="Synthetic condition",
                diagnosed_on=fixture.start_date,
                status="active",
                is_primary=True,
            )
        )
        connection.execute(
            Prescription.__table__.insert().values(
                id=prescription_id,
                tenant_id=fixture.tenant_id,
                encounter_id=encounter_ids[0],
                medication_name="Synthetic medication",
                dosage="1 synthetic unit",
                route="oral",
                frequency="once daily",
                instructions="Synthetic instruction",
                issued_at=appointment_start,
                status="active",
            )
        )
        connection.execute(
            MedicalOrder.__table__.insert().values(
                id=order_id,
                tenant_id=fixture.tenant_id,
                encounter_id=encounter_ids[0],
                order_type="synthetic",
                description="Synthetic order",
                status="requested",
                requested_at=appointment_start,
            )
        )

    try:
        yield fixture
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                delete(Diagnosis).where(Diagnosis.id == diagnosis_id)
            )
            connection.execute(
                delete(Prescription).where(Prescription.id == prescription_id)
            )
            connection.execute(
                delete(MedicalOrder).where(MedicalOrder.id == order_id)
            )
            connection.execute(
                delete(Encounter).where(Encounter.id.in_(encounter_ids))
            )
            connection.execute(
                delete(Appointment).where(Appointment.id.in_(appointment_ids))
            )
            connection.execute(
                delete(ClinicalRecord).where(
                    ClinicalRecord.id.in_(
                        [clinical_record_id, other_clinical_record_id]
                    )
                )
            )
            connection.execute(
                delete(Patient).where(
                    Patient.id.in_([patient_id, other_patient_id])
                )
            )
            connection.execute(
                delete(DoctorAvailability).where(
                    DoctorAvailability.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(DoctorSpecialty).where(
                    DoctorSpecialty.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(Doctor).where(Doctor.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                membership_roles.delete().where(
                    membership_roles.c.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(Membership).where(Membership.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(TenantSpecialty).where(
                    TenantSpecialty.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(Site).where(Site.tenant_id == fixture.tenant_id)
            )
            connection.execute(delete(Tenant).where(Tenant.id == fixture.tenant_id))
            connection.execute(
                delete(Specialty).where(
                    Specialty.id.in_(
                        [fixture.specialty_id, fixture.other_specialty_id]
                    )
                )
            )
            connection.execute(
                delete(User).where(
                    User.identity_provider_subject.in_(
                        [
                            fixture.admin_subject,
                            fixture.doctor_subject,
                            fixture.other_doctor_subject,
                        ]
                    )
                    | User.email.in_(
                        [
                            "dashboard-doctor-b@example.invalid",
                        ]
                    )
                )
            )
        migration_engine.dispose()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _client(subject: str, email: str, name: str) -> TestClient:
    app.dependency_overrides[get_verified_claims] = lambda: {
        "sub": subject,
        "email": email,
        "name": name,
        "amr": ["pwd", "otp"],
    }
    return TestClient(app)


def test_admin_dashboard_aggregates_real_metrics_and_filters(
    dashboard_fixture: DashboardFixture,
) -> None:
    fixture = dashboard_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}/dashboard"
    with _client(
        fixture.admin_subject,
        "dashboard-admin@example.invalid",
        "Synthetic Dashboard Admin",
    ) as client:
        filtered = client.get(
            base,
            params={
                "start_date": fixture.start_date.isoformat(),
                "end_date": (fixture.start_date + timedelta(days=1)).isoformat(),
                "site_id": str(fixture.site_id),
                "specialty_id": str(fixture.specialty_id),
            },
        )
        assert filtered.status_code == 200, filtered.text
        result = filtered.json()
        assert result["patients_registered"] == 1
        assert result["available_doctors"] == 1
        assert result["completed_encounters"] == 1
        assert result["filters"]["site_id"] == str(fixture.site_id)
        assert result["filters"]["specialty_id"] == str(fixture.specialty_id)
        assert {
            row["status"]: row["count"]
            for row in result["appointments_by_status"]
        } == {
            "scheduled": 1,
            "confirmed": 0,
            "checked_in": 1,
            "completed": 1,
            "cancelled": 1,
            "no_show": 0,
        }
        assert result["productivity"] == [
            {
                "doctor_id": result["productivity"][0]["doctor_id"],
                "doctor_name": "Synthetic Dashboard Doctor A",
                "completed_encounters": 1,
                "appointments_total": 3,
                "completed_appointments": 1,
                "completion_rate_percent": 33.3,
            }
        ]
        assert len(result["sites"]) == 2
        assert len(result["specialties"]) == 2

        across_sites = client.get(
            base,
            params={
                "start_date": fixture.start_date.isoformat(),
                "end_date": fixture.start_date.isoformat(),
                "specialty_id": str(fixture.specialty_id),
            },
        )
        assert across_sites.status_code == 200
        assert across_sites.json()["appointments_by_status"][3]["count"] == 2
        assert across_sites.json()["completed_encounters"] == 2

        all_specialties = client.get(
            base,
            params={
                "start_date": fixture.start_date.isoformat(),
                "end_date": fixture.start_date.isoformat(),
                "site_id": str(fixture.site_id),
            },
        )
        assert all_specialties.status_code == 200
        assert all_specialties.json()["patients_registered"] == 2
        assert all_specialties.json()["available_doctors"] == 2
        assert all_specialties.json()["completed_encounters"] == 2
        assert len(all_specialties.json()["productivity"]) == 2

        invalid_range = client.get(
            base,
            params={
                "start_date": fixture.start_date.isoformat(),
                "end_date": (fixture.start_date - timedelta(days=1)).isoformat(),
            },
        )
        assert invalid_range.status_code == 422
        too_long_range = client.get(
            base,
            params={
                "start_date": (fixture.start_date - timedelta(days=366)).isoformat(),
                "end_date": fixture.start_date.isoformat(),
            },
        )
        assert too_long_range.status_code == 422
        invalid_specialty = client.get(
            base,
            params={"specialty_id": str(uuid4())},
        )
        assert invalid_specialty.status_code == 404
        unrelated_tenant = client.get(
            f"/api/v1/admin/tenants/{uuid4()}/dashboard",
        )
        assert unrelated_tenant.status_code == 403


def test_dashboard_requires_tenant_administrator(
    dashboard_fixture: DashboardFixture,
) -> None:
    fixture = dashboard_fixture
    with _client(
        fixture.doctor_subject,
        "dashboard-doctor@example.invalid",
        "Synthetic Dashboard Doctor A",
    ) as client:
        response = client.get(
            f"/api/v1/admin/tenants/{fixture.tenant_id}/dashboard",
            params={
                "site_id": str(fixture.site_id),
                "start_date": fixture.start_date.isoformat(),
                "end_date": fixture.start_date.isoformat(),
            },
        )
    assert response.status_code == 403


def test_doctor_dashboard_and_clinical_records_are_scoped_to_care_team(
    dashboard_fixture: DashboardFixture,
) -> None:
    fixture = dashboard_fixture
    dashboard_path = f"/api/v1/clinical/tenants/{fixture.tenant_id}/dashboard"
    records_path = f"/api/v1/clinical/tenants/{fixture.tenant_id}/records"
    appointments_path = f"/api/v1/admin/tenants/{fixture.tenant_id}/appointments"
    params = {
        "site_id": str(fixture.site_id),
        "date": fixture.start_date.isoformat(),
    }

    with _client(
        fixture.doctor_subject,
        "dashboard-doctor@example.invalid",
        "Synthetic Dashboard Doctor A",
    ) as doctor:
        dashboard = doctor.get(dashboard_path, params=params)
        assert dashboard.status_code == 200, dashboard.text
        data = dashboard.json()
        assert len(data["appointments"]) == 4
        assert all(
            item["patient_name"] == "Synthetic Patient A"
            for item in data["appointments"]
        )
        assert {
            item["appointment_status"] for item in data["appointments"]
        } == {"completed", "scheduled", "cancelled", "checked_in"}
        assert len(data["pending_attentions"]) == 1
        pending = data["pending_attentions"][0]
        assert pending["arrival_status"] == "checked_in"
        assert pending["attention_status"] == "pending"
        assert pending["arrival_confirmed_at"] is not None
        assert pending["checked_in_at"] is not None
        assert not {
            "patient_id",
            "patient_number",
            "reason",
            "operational_notes",
            "diagnoses",
            "prescriptions",
        }.intersection(pending)

        record = doctor.get(
            f"{records_path}/{fixture.clinical_record_id}",
            params={"site_id": str(fixture.site_id)},
        )
        assert record.status_code == 200, record.text
        assert record.json()["patient_name"] == "Synthetic Patient A"
        assert len(record.json()["encounters"]) == 1
        assert record.json()["encounters"][0]["diagnoses"][0]["code"] == "SYN-001"
        assert (
            record.json()["encounters"][0]["prescriptions"][0]["medication_name"]
            == "Synthetic medication"
        )
        assert (
            record.json()["encounters"][0]["orders"][0]["description"]
            == "Synthetic order"
        )

        other_patient_record = doctor.get(
            f"{records_path}/{fixture.other_clinical_record_id}",
            params={"site_id": str(fixture.site_id)},
        )
        assert other_patient_record.status_code == 404

        appointments = doctor.get(
            appointments_path,
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.start_date.isoformat(),
                "date_to": fixture.start_date.isoformat(),
            },
        )
        assert appointments.status_code == 200, appointments.text
        assert appointments.json()["total"] == 4
        assert all(
            item["patient_name"] == "Synthetic Patient A"
            for item in appointments.json()["items"]
        )

        unauthorized_filter = doctor.get(
            appointments_path,
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.start_date.isoformat(),
                "date_to": fixture.start_date.isoformat(),
                "doctor_id": str(uuid4()),
            },
        )
        assert unauthorized_filter.status_code == 403

    with _client(
        fixture.other_doctor_subject,
        "dashboard-doctor-b@example.invalid",
        "Synthetic Dashboard Doctor B",
    ) as other_doctor:
        other_dashboard = other_doctor.get(dashboard_path, params=params)
        assert other_dashboard.status_code == 200, other_dashboard.text
        assert len(other_dashboard.json()["appointments"]) == 2
        assert all(
            item["patient_name"] == "Synthetic Patient B"
            for item in other_dashboard.json()["appointments"]
        )

        other_record = other_doctor.get(
            f"{records_path}/{fixture.clinical_record_id}",
            params={"site_id": str(fixture.site_id)},
        )
        assert other_record.status_code == 404

        other_appointments = other_doctor.get(
            appointments_path,
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.start_date.isoformat(),
                "date_to": fixture.start_date.isoformat(),
            },
        )
        assert other_appointments.status_code == 200
        other_appointment_id = other_appointments.json()["items"][0]["id"]

        own_history = other_doctor.get(
            f"{appointments_path}/{other_appointment_id}/history",
            params={"site_id": str(fixture.site_id)},
        )
        assert own_history.status_code == 200

        denied_other_history = other_doctor.get(
            f"{appointments_path}/{appointments.json()['items'][0]['id']}/history",
            params={"site_id": str(fixture.site_id)},
        )
        assert denied_other_history.status_code == 404

    with _client(
        fixture.admin_subject,
        "dashboard-admin@example.invalid",
        "Synthetic Dashboard Admin",
    ) as admin:
        forbidden = admin.get(dashboard_path, params=params)
    assert forbidden.status_code == 403
