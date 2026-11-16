import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete

from app.db.models import (
    Appointment,
    AppointmentHistory,
    AuditEvent,
    ClinicRoom,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Membership,
    Patient,
    Role,
    Service,
    Site,
    SiteHoliday,
    SiteHours,
    Specialty,
    Tenant,
    TenantSpecialty,
    User,
)
from app.domains.identity.models import membership_roles
from app.domains.identity.router import get_verified_claims
from app.main import app


@dataclass(frozen=True)
class SchedulingFixture:
    tenant_id: UUID
    site_id: UUID
    patient_id: UUID
    doctor_id: UUID
    specialty_id: UUID
    service_id: UUID
    room_id: UUID
    receptionist_subject: str
    service_subject: str
    doctor_subject: str
    admin_subject: str
    work_date: date


@pytest.fixture
def scheduling_fixture() -> SchedulingFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for PostgreSQL scheduling tests")

    work_date = date.today() + timedelta(days=14)
    while work_date.weekday() > 4:
        work_date += timedelta(days=1)
    fixture = SchedulingFixture(
        tenant_id=uuid4(),
        site_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        specialty_id=uuid4(),
        service_id=uuid4(),
        room_id=uuid4(),
        receptionist_subject=f"scheduling-receptionist-{uuid4().hex}",
        service_subject=f"scheduling-service-{uuid4().hex}",
        doctor_subject=f"scheduling-doctor-{uuid4().hex}",
        admin_subject=f"scheduling-admin-{uuid4().hex}",
        work_date=work_date,
    )
    engine = create_engine(migration_url, pool_pre_ping=True)
    receptionist_user_id, service_user_id, doctor_user_id, admin_user_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    receptionist_membership_id, service_membership_id, doctor_membership_id, admin_membership_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    start_time = time(9, 0)
    end_time = time(12, 0)

    with engine.begin() as connection:
        receptionist_role_id = connection.scalar(
            Role.__table__.select()
            .with_only_columns(Role.id)
            .where(Role.code == "receptionist")
        )
        service_role_id = connection.scalar(
            Role.__table__.select()
            .with_only_columns(Role.id)
            .where(Role.code == "service")
        )
        administrator_role_id = connection.scalar(
            Role.__table__.select()
            .with_only_columns(Role.id)
            .where(Role.code == "administrator")
        )
        assert receptionist_role_id is not None
        assert service_role_id is not None
        assert administrator_role_id is not None
        connection.execute(
            Tenant.__table__.insert().values(
                id=fixture.tenant_id,
                name="Synthetic scheduling tenant",
                slug=f"scheduling-{fixture.tenant_id.hex[:12]}",
            )
        )
        connection.execute(
            Site.__table__.insert().values(
                id=fixture.site_id,
                tenant_id=fixture.tenant_id,
                code="SCHEDULING",
                name="Synthetic scheduling site",
                timezone="America/Guayaquil",
                is_active=True,
            )
        )
        connection.execute(
            ClinicRoom.__table__.insert().values(
                id=fixture.room_id,
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                code="SERVICE-ROOM",
                name="Synthetic service room",
                room_type="consultation",
                is_active=True,
            )
        )
        connection.execute(
            Specialty.__table__.insert().values(
                id=fixture.specialty_id,
                code=f"SCHED{fixture.specialty_id.hex[:8].upper()}",
                name="Synthetic scheduling specialty",
                is_active=True,
            )
        )
        connection.execute(
            TenantSpecialty.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.tenant_id,
                specialty_id=fixture.specialty_id,
                is_active=True,
            )
        )
        connection.execute(
            User.__table__.insert(),
            [
                {
                    "id": receptionist_user_id,
                    "identity_provider_subject": fixture.receptionist_subject,
                    "email": f"{fixture.receptionist_subject}@example.invalid",
                    "display_name": "Synthetic Scheduling Receptionist",
                    "is_active": True,
                },
                {
                    "id": service_user_id,
                    "identity_provider_subject": fixture.service_subject,
                    "email": f"{fixture.service_subject}@example.invalid",
                    "display_name": "Synthetic Scheduling Service",
                    "is_active": True,
                },
                {
                    "id": doctor_user_id,
                    "identity_provider_subject": fixture.doctor_subject,
                    "email": f"{fixture.doctor_subject}@example.invalid",
                    "display_name": "Synthetic Scheduling Doctor",
                    "is_active": True,
                },
                {
                    "id": admin_user_id,
                    "identity_provider_subject": fixture.admin_subject,
                    "email": f"{fixture.admin_subject}@example.invalid",
                    "display_name": "Synthetic Scheduling Admin",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            Membership.__table__.insert(),
            [
                {
                    "id": receptionist_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": receptionist_user_id,
                    "status": "active",
                },
                {
                    "id": service_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": service_user_id,
                    "status": "active",
                },
                {
                    "id": doctor_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": doctor_user_id,
                    "status": "active",
                },
                {
                    "id": admin_membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": admin_user_id,
                    "status": "active",
                },
            ],
        )
        connection.execute(
            membership_roles.insert(),
            [
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": receptionist_membership_id,
                    "role_id": receptionist_role_id,
                },
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": service_membership_id,
                    "role_id": service_role_id,
                },
                {
                    "tenant_id": fixture.tenant_id,
                    "membership_id": admin_membership_id,
                    "role_id": administrator_role_id,
                },
            ],
        )
        connection.execute(
            Doctor.__table__.insert().values(
                id=fixture.doctor_id,
                tenant_id=fixture.tenant_id,
                membership_id=doctor_membership_id,
                specialty_id=fixture.specialty_id,
                license_number=f"SYN-{fixture.doctor_id.hex[:10]}",
                is_active=True,
            )
        )
        connection.execute(
            DoctorSpecialty.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.tenant_id,
                doctor_id=fixture.doctor_id,
                specialty_id=fixture.specialty_id,
                is_primary=True,
            )
        )
        connection.execute(
            DoctorAvailability.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.tenant_id,
                doctor_id=fixture.doctor_id,
                site_id=fixture.site_id,
                weekday=fixture.work_date.weekday(),
                starts_at=start_time,
                ends_at=end_time,
                is_available=True,
            )
        )
        connection.execute(
            SiteHours.__table__.insert().values(
                id=uuid4(),
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                weekday=fixture.work_date.weekday(),
                opens_at=time(8, 0),
                closes_at=time(17, 0),
                is_closed=False,
            )
        )
        connection.execute(
            Patient.__table__.insert().values(
                id=fixture.patient_id,
                tenant_id=fixture.tenant_id,
                patient_number=f"SYN-{fixture.patient_id.hex[:10]}",
                given_name="Synthetic",
                family_name="Scheduling Patient",
                status="active",
            )
        )
        connection.execute(
            Service.__table__.insert().values(
                id=fixture.service_id,
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                code="CONSULT",
                name="Synthetic consultation",
                duration_minutes=30,
                price=0,
                currency="USD",
                is_active=True,
            )
        )

    try:
        yield fixture
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(AppointmentHistory).where(
                    AppointmentHistory.tenant_id == fixture.tenant_id
                )
            )
            connection.execute(
                delete(AuditEvent).where(AuditEvent.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(Appointment).where(Appointment.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(ClinicRoom).where(ClinicRoom.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(SiteHoliday).where(SiteHoliday.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(SiteHours).where(SiteHours.tenant_id == fixture.tenant_id)
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
                delete(Service).where(Service.tenant_id == fixture.tenant_id)
            )
            connection.execute(
                delete(Patient).where(Patient.tenant_id == fixture.tenant_id)
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
            connection.execute(delete(Site).where(Site.tenant_id == fixture.tenant_id))
            connection.execute(delete(Tenant).where(Tenant.id == fixture.tenant_id))
            connection.execute(
                delete(Specialty).where(Specialty.id == fixture.specialty_id)
            )
            connection.execute(
                delete(User).where(
                    User.identity_provider_subject.in_(
                        [
                            fixture.receptionist_subject,
                            fixture.service_subject,
                            fixture.doctor_subject,
                            fixture.admin_subject,
                        ]
                    )
                )
            )
        engine.dispose()


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


def test_scheduling_catalog_availability_calendar_and_overlap(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as client:
        catalog = client.get(
            f"{base}/scheduling/catalog",
            params={"site_id": str(fixture.site_id)},
        )
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()["timezone"] == "America/Guayaquil"
        assert catalog.json()["doctors"][0]["id"] == str(fixture.doctor_id)
        assert catalog.json()["services"][0]["duration_minutes"] == 30

        params = {
            "site_id": str(fixture.site_id),
            "date_from": fixture.work_date.isoformat(),
            "date_to": fixture.work_date.isoformat(),
            "doctor_id": str(fixture.doctor_id),
            "specialty_id": str(fixture.specialty_id),
            "service_id": str(fixture.service_id),
        }
        availability = client.get(f"{base}/scheduling/availability", params=params)
        assert availability.status_code == 200, availability.text
        slots = availability.json()["items"]
        assert slots
        assert availability.json()["duration_minutes"] == 30
        assert all(slot["doctor_id"] == str(fixture.doctor_id) for slot in slots)
        first_slot = slots[0]
        booking = {
            "site_id": str(fixture.site_id),
            "patient_id": str(fixture.patient_id),
            "doctor_id": str(fixture.doctor_id),
            "service_id": str(fixture.service_id),
            "starts_at": first_slot["starts_at"],
            "reason": "Control administrativo",
            "operational_notes": "Confirmar llegada",
            "status": "scheduled",
        }
        duration_mismatch = dict(booking, duration_minutes=45)
        rejected_duration = client.post(
            f"{base}/appointments",
            json=duration_mismatch,
        )
        assert rejected_duration.status_code == 422
        created = client.post(f"{base}/appointments", json=booking)
        assert created.status_code == 201, created.text
        created_data = created.json()
        assert created_data["duration_minutes"] == 30
        assert created_data["reason"] == "Control administrativo"
        assert created_data["operational_notes"] == "Confirmar llegada"
        assert created_data["patient_name"] == "Synthetic Scheduling Patient"

        calendar = client.get(
            f"{base}/appointments",
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
                "specialty_id": str(fixture.specialty_id),
            },
        )
        assert calendar.status_code == 200, calendar.text
        assert calendar.json()["total"] == 1
        assert calendar.json()["items"][0]["id"] == created_data["id"]

        overlapping = dict(booking)
        overlapping["starts_at"] = (
            datetime.fromisoformat(first_slot["starts_at"]) + timedelta(minutes=15)
        ).isoformat()
        conflict = client.post(f"{base}/appointments", json=overlapping)
        assert conflict.status_code == 409

        confirmed = client.patch(
            f"{base}/appointments/{created_data['id']}",
            params={"site_id": str(fixture.site_id)},
            json={
                "action": "confirm",
                "reason": "Confirmación administrativa",
                "expected_version": created_data["version"],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["version"] == created_data["version"] + 1

        stale = client.patch(
            f"{base}/appointments/{created_data['id']}",
            params={"site_id": str(fixture.site_id)},
            json={
                "action": "cancel",
                "reason": "Cancelación administrativa",
                "expected_version": created_data["version"],
            },
        )
        assert stale.status_code == 409
        assert "changed by another request" in stale.json()["detail"]

        next_slots = client.get(
            f"{base}/scheduling/availability",
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
                "doctor_id": str(fixture.doctor_id),
                "service_id": str(fixture.service_id),
            },
        ).json()["items"]
        reschedule_slot = next(
            slot for slot in next_slots
            if slot["starts_at"] != created_data["starts_at"]
        )
        moved = client.patch(
            f"{base}/appointments/{created_data['id']}",
            params={"site_id": str(fixture.site_id)},
            json={
                "action": "reschedule",
                "reason": "Cambio de horario solicitado",
                "expected_version": confirmed.json()["version"],
                "starts_at": reschedule_slot["starts_at"],
            },
        )
        assert moved.status_code == 200, moved.text
        assert datetime.fromisoformat(moved.json()["starts_at"]) == datetime.fromisoformat(
            reschedule_slot["starts_at"]
        )
        assert moved.json()["status"] == "confirmed"
        assert moved.json()["version"] == confirmed.json()["version"] + 1

        history = client.get(
            f"{base}/appointments/{created_data['id']}/history",
            params={"site_id": str(fixture.site_id)},
        )
        assert history.status_code == 200, history.text
        assert [event["action"] for event in history.json()] == [
            "created",
            "confirmed",
            "rescheduled",
        ]
        assert history.json()[2]["reason"] == "Cambio de horario solicitado"
        assert datetime.fromisoformat(
            history.json()[2]["changes"]["before"]["starts_at"]
        ) == datetime.fromisoformat(created_data["starts_at"])
        assert datetime.fromisoformat(
            history.json()[2]["changes"]["after"]["starts_at"]
        ) == datetime.fromisoformat(reschedule_slot["starts_at"])

        cancelled = client.patch(
            f"{base}/appointments/{created_data['id']}",
            params={"site_id": str(fixture.site_id)},
            json={
                "action": "cancel",
                "reason": "Paciente solicitó cancelar",
                "expected_version": moved.json()["version"],
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["version"] == moved.json()["version"] + 1

        invalid_transition = client.patch(
            f"{base}/appointments/{created_data['id']}",
            params={"site_id": str(fixture.site_id)},
            json={
                "action": "confirm",
                "reason": "No se puede confirmar",
                "expected_version": cancelled.json()["version"],
            },
        )
        assert invalid_transition.status_code == 409


def test_site_holidays_block_availability_and_booking(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.admin_subject,
        f"{fixture.admin_subject}@example.invalid",
        "Synthetic Scheduling Admin",
    ) as client:
        holiday_path = f"{base}/sites/{fixture.site_id}/holidays"
        holiday = client.post(
            holiday_path,
            json={"holiday_date": fixture.work_date.isoformat(), "name": "Feriado sintético"},
        )
        assert holiday.status_code == 201, holiday.text
        duplicate = client.post(
            holiday_path,
            json={"holiday_date": fixture.work_date.isoformat(), "name": "Duplicado sintético"},
        )
        assert duplicate.status_code == 409
        listed = client.get(
            holiday_path,
            params={
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
            },
        )
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "Feriado sintético"

    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as client:
        availability = client.get(
            f"{base}/scheduling/availability",
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
                "doctor_id": str(fixture.doctor_id),
            },
        )
        assert availability.status_code == 200
        assert availability.json()["items"] == []

        local_start = datetime.combine(
            fixture.work_date,
            time(9, 0),
            tzinfo=timezone(timedelta(hours=-5)),
        )
        booking = client.post(
            f"{base}/appointments",
            json={
                "site_id": str(fixture.site_id),
                "patient_id": str(fixture.patient_id),
                "doctor_id": str(fixture.doctor_id),
                "starts_at": local_start.isoformat(),
                "duration_minutes": 30,
                "reason": "Motivo sintético",
            },
        )
        assert booking.status_code == 409


def test_concurrent_bookings_for_same_doctor_slot_return_one_conflict(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as client:
        availability = client.get(
            f"{base}/scheduling/availability",
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
                "doctor_id": str(fixture.doctor_id),
                "duration_minutes": 30,
            },
        )
        assert availability.status_code == 200
        starts_at = availability.json()["items"][0]["starts_at"]
        payload = {
            "site_id": str(fixture.site_id),
            "patient_id": str(fixture.patient_id),
            "doctor_id": str(fixture.doctor_id),
            "starts_at": starts_at,
            "duration_minutes": 30,
            "reason": "Reserva concurrente sintética",
        }
        barrier = Barrier(2)

        def book():
            barrier.wait(timeout=5)
            return client.post(f"{base}/appointments", json=payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: book(), range(2)))

        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert "overlapping appointment" in conflict.json()["detail"]


def test_scheduling_permissions_and_working_hours(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.service_subject,
        f"{fixture.service_subject}@example.invalid",
        "Synthetic Scheduling Service",
    ) as client:
        denied = client.post(
            f"{base}/appointments",
            json={
                "site_id": str(fixture.site_id),
                "patient_id": str(fixture.patient_id),
                "doctor_id": str(fixture.doctor_id),
                "starts_at": datetime.combine(
                    fixture.work_date,
                    time(9, 0),
                    tzinfo=timezone(timedelta(hours=-5)),
                ).isoformat(),
                "duration_minutes": 30,
                "reason": "Motivo sintético",
            },
        )
        assert denied.status_code == 403
        unrelated_tenant = client.get(
            f"/api/v1/admin/tenants/{uuid4()}/appointments",
            params={
                "site_id": str(fixture.site_id),
                "date_from": fixture.work_date.isoformat(),
                "date_to": fixture.work_date.isoformat(),
            },
        )
        assert unrelated_tenant.status_code == 403

    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as client:
        forbidden_holiday = client.post(
            f"{base}/sites/{fixture.site_id}/holidays",
            json={
                "holiday_date": (fixture.work_date + timedelta(days=1)).isoformat(),
                "name": "Feriado no autorizado",
            },
        )
        assert forbidden_holiday.status_code == 403
        outside = client.post(
            f"{base}/appointments",
            json={
                "site_id": str(fixture.site_id),
                "patient_id": str(fixture.patient_id),
                "doctor_id": str(fixture.doctor_id),
                "starts_at": datetime.combine(
                    fixture.work_date,
                    time(12, 0),
                    tzinfo=timezone(timedelta(hours=-5)),
                ).isoformat(),
                "duration_minutes": 30,
                "reason": "Motivo sintético",
            },
        )
        assert outside.status_code == 409


def test_reception_search_and_checkin_lifecycle(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    starts_at = datetime.combine(
        fixture.work_date,
        time(9, 0),
        tzinfo=timezone(timedelta(hours=-5)),
    )
    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as client:
        created = client.post(
            f"{base}/appointments",
            json={
                "site_id": str(fixture.site_id),
                "patient_id": str(fixture.patient_id),
                "doctor_id": str(fixture.doctor_id),
                "service_id": str(fixture.service_id),
                "starts_at": starts_at.isoformat(),
                "reason": "Synthetic reason",
            },
        )
        assert created.status_code == 201
        appointment = created.json()

        params = {
            "site_id": str(fixture.site_id),
            "date": fixture.work_date.isoformat(),
            "q": f"SYN-{fixture.patient_id.hex[:10]}",
        }
        searched = client.get(
            f"{base}/operations/reception/appointments",
            params=params,
        )
        assert searched.status_code == 200
        result = searched.json()
        assert result["total"] == 1
        assert result["items"][0]["id"] == appointment["id"]
        assert result["items"][0]["patient_number"] == params["q"]
        assert "reason" not in result["items"][0]

        reception_path = (
            f"{base}/operations/reception/appointments/{appointment['id']}"
        )
        early_checkin = client.post(
            f"{reception_path}/check-in?site_id={fixture.site_id}",
            json={"expected_version": appointment["version"]},
        )
        assert early_checkin.status_code == 409

        arrival = client.post(
            f"{reception_path}/confirm-arrival?site_id={fixture.site_id}",
            json={"expected_version": appointment["version"]},
        )
        assert arrival.status_code == 200
        assert arrival.json()["action"] == "confirm-arrival"
        assert arrival.json()["version"] == appointment["version"] + 1

        checkin = client.post(
            f"{reception_path}/check-in?site_id={fixture.site_id}",
            json={"expected_version": arrival.json()["version"]},
        )
        assert checkin.status_code == 200
        assert checkin.json()["status"] == "checked_in"

        queued = client.post(
            f"{reception_path}/send-to-queue?site_id={fixture.site_id}",
            json={"expected_version": checkin.json()["version"]},
        )
        assert queued.status_code == 200
        duplicate_queue_entry = client.post(
            f"{reception_path}/send-to-queue?site_id={fixture.site_id}",
            json={"expected_version": queued.json()["version"]},
        )
        assert duplicate_queue_entry.status_code == 409

        sent = client.get(
            f"{base}/operations/reception/appointments",
            params={**params, "queue": "sent", "status": "checked_in"},
        )
        assert sent.status_code == 200
        assert sent.json()["items"][0]["queue_entered_at"] is not None

        with _client(
            fixture.service_subject,
            f"{fixture.service_subject}@example.invalid",
            "Synthetic Scheduling Service",
        ) as read_only_client:
            denied = read_only_client.post(
                f"{reception_path}/send-to-queue?site_id={fixture.site_id}",
                json={"expected_version": queued.json()["version"]},
            )
        assert denied.status_code == 403


def test_service_queue_room_assignment_and_attention_lifecycle(
    scheduling_fixture: SchedulingFixture,
) -> None:
    fixture = scheduling_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    starts_at = datetime.combine(
        fixture.work_date,
        time(9, 0),
        tzinfo=timezone(timedelta(hours=-5)),
    )
    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as receptionist:
        def create_queued_appointment(start: datetime) -> dict:
            created = receptionist.post(
                f"{base}/appointments",
                json={
                    "site_id": str(fixture.site_id),
                    "patient_id": str(fixture.patient_id),
                    "doctor_id": str(fixture.doctor_id),
                    "service_id": str(fixture.service_id),
                    "starts_at": start.isoformat(),
                    "reason": "Synthetic reason",
                },
            )
            assert created.status_code == 201, created.text
            appointment = created.json()
            reception_path = (
                f"{base}/operations/reception/appointments/{appointment['id']}"
            )
            arrival = receptionist.post(
                f"{reception_path}/confirm-arrival?site_id={fixture.site_id}",
                json={"expected_version": appointment["version"]},
            )
            assert arrival.status_code == 200, arrival.text
            checkin = receptionist.post(
                f"{reception_path}/check-in?site_id={fixture.site_id}",
                json={"expected_version": arrival.json()["version"]},
            )
            assert checkin.status_code == 200, checkin.text
            queued = receptionist.post(
                f"{reception_path}/send-to-queue?site_id={fixture.site_id}",
                json={"expected_version": checkin.json()["version"]},
            )
            assert queued.status_code == 200, queued.text
            return appointment

        first_appointment = create_queued_appointment(starts_at)
        second_appointment = create_queued_appointment(
            starts_at + timedelta(hours=1)
        )

    queue_path = f"{base}/operations/service/queue"
    item_path = f"{queue_path}/{{}}?site_id={fixture.site_id}"
    with _client(
        fixture.service_subject,
        f"{fixture.service_subject}@example.invalid",
        "Synthetic Scheduling Service",
    ) as service:
        queue = service.get(queue_path, params={"site_id": str(fixture.site_id)})
        assert queue.status_code == 200
        data = queue.json()
        assert data["total"] == 2
        items = {
            item["appointment_id"]: item for item in data["items"]
        }
        first_item = items[str(first_appointment["id"])]
        second_item = items[str(second_appointment["id"])]
        assert first_item["service_status"] == "pending"
        assert first_item["room_id"] is None
        assert data["rooms"][0]["id"] == str(fixture.room_id)
        assert not {
            "patient_id",
            "patient_number",
            "reason",
            "operational_notes",
            "diagnoses",
            "prescriptions",
        }.intersection(first_item)

        prepare_without_room = service.patch(
            item_path.format(first_appointment["id"]),
            json={
                "action": "start-preparation",
                "expected_version": first_item["version"],
            },
        )
        assert prepare_without_room.status_code == 409

        ready_items = []
        for item in (first_item, second_item):
            appointment_path = item_path.format(item["appointment_id"])
            assigned = service.patch(
                appointment_path,
                json={
                    "action": "assign-room",
                    "expected_version": item["version"],
                    "room_id": str(fixture.room_id),
                },
            )
            assert assigned.status_code == 200, assigned.text
            version = assigned.json()["version"]

            preparation = service.patch(
                appointment_path,
                json={"action": "start-preparation", "expected_version": version},
            )
            assert preparation.status_code == 200, preparation.text
            assert preparation.json()["service_status"] == "preparing"
            version = preparation.json()["version"]

            ready = service.patch(
                appointment_path,
                json={"action": "mark-ready", "expected_version": version},
            )
            assert ready.status_code == 200, ready.text
            assert ready.json()["service_status"] == "ready"
            ready_items.append((item["appointment_id"], ready.json()["version"]))

        first_id, first_version = ready_items[0]
        second_id, second_version = ready_items[1]
        attention = service.patch(
            item_path.format(first_id),
            json={"action": "start-attention", "expected_version": first_version},
        )
        assert attention.status_code == 200, attention.text

        room_conflict = service.patch(
            item_path.format(second_id),
            json={"action": "start-attention", "expected_version": second_version},
        )
        assert room_conflict.status_code == 409
        assert room_conflict.json()["detail"] == "Room is currently in use"

        completed_first = service.patch(
            item_path.format(first_id),
            json={"action": "finish", "expected_version": attention.json()["version"]},
        )
        assert completed_first.status_code == 200, completed_first.text
        assert completed_first.json()["service_status"] == "completed"

        attention_second = service.patch(
            item_path.format(second_id),
            json={"action": "start-attention", "expected_version": second_version},
        )
        assert attention_second.status_code == 200, attention_second.text
        completed_second = service.patch(
            item_path.format(second_id),
            json={
                "action": "finish",
                "expected_version": attention_second.json()["version"],
            },
        )
        assert completed_second.status_code == 200, completed_second.text

        finished_queue = service.get(
            queue_path,
            params={
                "site_id": str(fixture.site_id),
                "status": "completed",
                "room_id": str(fixture.room_id),
            },
        )
        assert finished_queue.status_code == 200
        assert finished_queue.json()["total"] == 2
        for finished_item in finished_queue.json()["items"]:
            assert finished_item["preparation_started_at"] is not None
            assert finished_item["ready_at"] is not None
            assert finished_item["attention_started_at"] is not None
            assert finished_item["attention_completed_at"] is not None

    with _client(
        fixture.receptionist_subject,
        f"{fixture.receptionist_subject}@example.invalid",
        "Synthetic Scheduling Receptionist",
    ) as receptionist:
        denied = receptionist.get(queue_path, params={"site_id": str(fixture.site_id)})
    assert denied.status_code == 403
