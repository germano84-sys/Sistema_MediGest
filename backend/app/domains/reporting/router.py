from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select

from app.db.models import (
    Appointment,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Encounter,
    Membership,
    Patient,
    Site,
    Specialty,
    TenantSpecialty,
    User,
)
from app.db.session import tenant_session
from app.domains.identity.authorization import (
    AuthorizationContext,
    load_authorization_context,
)
from app.domains.identity.router import get_verified_claims
from app.domains.reporting.schemas import (
    AdminDashboard,
    AppointmentStatusCount,
    DashboardFilters,
    DashboardSiteOption,
    DashboardSpecialtyOption,
    DoctorProductivity,
)

router = APIRouter(prefix="/api/v1/admin/tenants", tags=["reporting"])
APPOINTMENT_STATUSES = (
    "scheduled",
    "confirmed",
    "checked_in",
    "completed",
    "cancelled",
    "no_show",
)
MAX_DASHBOARD_RANGE_DAYS = 366


def _dashboard_context(
    claims: dict[str, Any],
    tenant_id: UUID,
    site_id: UUID | None,
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id, site_id)
    is_tenant_admin = (
        "administrator" in context.role_codes
        and "tenant:manage" in context.permission_codes
    )
    is_platform_admin = (
        "superadmin" in context.role_codes
        and "platform:manage" in context.permission_codes
    )
    if not (is_tenant_admin or is_platform_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator permission is required",
        )
    return context


def _date_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must not be earlier than start_date",
        )
    if (end_date - start_date).days + 1 > MAX_DASHBOARD_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dashboard date range must not exceed 366 days",
        )
    return (
        datetime.combine(start_date, time.min, tzinfo=timezone.utc),
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def _doctor_specialty_exists(specialty_id: UUID):
    return (
        select(DoctorSpecialty.id)
        .where(
            DoctorSpecialty.tenant_id == Doctor.tenant_id,
            DoctorSpecialty.doctor_id == Doctor.id,
            DoctorSpecialty.specialty_id == specialty_id,
        )
        .exists()
    )


def _patient_filter(
    tenant_id: UUID,
    start_at: datetime,
    end_at: datetime,
    site_id: UUID | None,
    specialty_id: UUID | None,
):
    matching_appointments = select(Appointment.id).where(
        Appointment.tenant_id == tenant_id,
        Appointment.patient_id == Patient.id,
        Appointment.starts_at >= start_at,
        Appointment.starts_at < end_at,
        Appointment.status.not_in(("cancelled", "no_show")),
    )
    if site_id is not None:
        matching_appointments = matching_appointments.where(
            Appointment.site_id == site_id
        )
    if specialty_id is not None:
        matching_appointments = matching_appointments.where(
            Appointment.doctor_id.is_not(None),
            select(DoctorSpecialty.id)
            .where(
                DoctorSpecialty.tenant_id == Appointment.tenant_id,
                DoctorSpecialty.doctor_id == Appointment.doctor_id,
                DoctorSpecialty.specialty_id == specialty_id,
            )
            .exists(),
        )
    return matching_appointments.exists()


@router.get("/{tenant_id}/dashboard", response_model=AdminDashboard)
def get_admin_dashboard(
    tenant_id: UUID,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=29)),
    end_date: date = Query(default_factory=date.today),
    site_id: UUID | None = Query(default=None),
    specialty_id: UUID | None = Query(default=None),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> AdminDashboard:
    _dashboard_context(claims, tenant_id, site_id)
    start_at, end_at = _date_range(start_date, end_date)
    with tenant_session(tenant_id) as session:
        if specialty_id is not None:
            configured_specialty = session.scalar(
                select(Specialty.id)
                .join(
                    TenantSpecialty,
                    TenantSpecialty.specialty_id == Specialty.id,
                )
                .where(
                    TenantSpecialty.tenant_id == tenant_id,
                    TenantSpecialty.is_active.is_(True),
                    Specialty.id == specialty_id,
                    Specialty.is_active.is_(True),
                )
            )
            if configured_specialty is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specialty not found",
                )

        sites = session.scalars(
            select(Site)
            .where(Site.tenant_id == tenant_id, Site.is_active.is_(True))
            .order_by(Site.name, Site.id)
        ).all()
        specialties = session.execute(
            select(Specialty.id, Specialty.code, Specialty.name)
            .join(
                TenantSpecialty,
                TenantSpecialty.specialty_id == Specialty.id,
            )
            .where(
                TenantSpecialty.tenant_id == tenant_id,
                TenantSpecialty.is_active.is_(True),
                Specialty.is_active.is_(True),
            )
            .order_by(Specialty.name, Specialty.id)
        ).all()

        patient_statement = select(func.count(Patient.id)).where(
            Patient.tenant_id == tenant_id,
            Patient.created_at >= start_at,
            Patient.created_at < end_at,
        )
        if site_id is not None or specialty_id is not None:
            patient_statement = patient_statement.where(
                _patient_filter(
                    tenant_id,
                    start_at,
                    end_at,
                    site_id,
                    specialty_id,
                )
            )
        patients_registered = session.scalar(patient_statement) or 0

        appointment_statement = (
            select(Appointment.status, func.count(Appointment.id))
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.starts_at >= start_at,
                Appointment.starts_at < end_at,
            )
            .group_by(Appointment.status)
        )
        if site_id is not None:
            appointment_statement = appointment_statement.where(
                Appointment.site_id == site_id
            )
        if specialty_id is not None:
            appointment_statement = appointment_statement.where(
                Appointment.doctor_id.is_not(None),
                select(DoctorSpecialty.id)
                .where(
                    DoctorSpecialty.tenant_id == Appointment.tenant_id,
                    DoctorSpecialty.doctor_id == Appointment.doctor_id,
                    DoctorSpecialty.specialty_id == specialty_id,
                )
                .exists(),
            )
        appointment_counts = dict(session.execute(appointment_statement).all())
        appointments_by_status = [
            AppointmentStatusCount(
                status=appointment_status,
                count=appointment_counts.get(appointment_status, 0),
            )
            for appointment_status in APPOINTMENT_STATUSES
        ]

        weekdays = sorted(
            {
                (start_date + timedelta(days=offset)).weekday()
                for offset in range((end_date - start_date).days + 1)
            }
        )
        availability_statement = (
            select(func.count(func.distinct(Doctor.id)))
            .select_from(DoctorAvailability)
            .join(
                Doctor,
                (Doctor.tenant_id == DoctorAvailability.tenant_id)
                & (Doctor.id == DoctorAvailability.doctor_id),
            )
            .where(
                DoctorAvailability.tenant_id == tenant_id,
                DoctorAvailability.is_available.is_(True),
                DoctorAvailability.weekday.in_(weekdays),
                Doctor.is_active.is_(True),
            )
        )
        if site_id is not None:
            availability_statement = availability_statement.where(
                DoctorAvailability.site_id == site_id
            )
        if specialty_id is not None:
            availability_statement = availability_statement.where(
                _doctor_specialty_exists(specialty_id)
            )
        available_doctors = session.scalar(availability_statement) or 0

        encounter_statement = select(func.count(Encounter.id)).where(
            Encounter.tenant_id == tenant_id,
            Encounter.started_at >= start_at,
            Encounter.started_at < end_at,
            Encounter.status == "completed",
        )
        encounter_doctor_specialty = (
            select(DoctorSpecialty.id)
            .where(
                DoctorSpecialty.tenant_id == Encounter.tenant_id,
                DoctorSpecialty.doctor_id == Encounter.doctor_id,
                DoctorSpecialty.specialty_id == specialty_id,
            )
            .exists()
            if specialty_id is not None
            else None
        )
        if site_id is not None:
            encounter_statement = encounter_statement.where(Encounter.site_id == site_id)
        if encounter_doctor_specialty is not None:
            encounter_statement = encounter_statement.where(encounter_doctor_specialty)
        completed_encounters = session.scalar(encounter_statement) or 0

        productivity_appointments = (
            select(
                Appointment.doctor_id,
                func.count(Appointment.id).label("appointments_total"),
                func.sum(
                    case((Appointment.status == "completed", 1), else_=0)
                ).label("completed_appointments"),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.doctor_id.is_not(None),
                Appointment.starts_at >= start_at,
                Appointment.starts_at < end_at,
                Appointment.status.not_in(("cancelled", "no_show")),
            )
            .group_by(Appointment.doctor_id)
        )
        productivity_encounters = (
            select(
                Encounter.doctor_id,
                func.count(Encounter.id).label("completed_encounters"),
            )
            .where(
                Encounter.tenant_id == tenant_id,
                Encounter.started_at >= start_at,
                Encounter.started_at < end_at,
                Encounter.status == "completed",
            )
            .group_by(Encounter.doctor_id)
        )
        if site_id is not None:
            productivity_appointments = productivity_appointments.where(
                Appointment.site_id == site_id
            )
            productivity_encounters = productivity_encounters.where(
                Encounter.site_id == site_id
            )
        if specialty_id is not None:
            productivity_appointments = productivity_appointments.where(
                select(DoctorSpecialty.id)
                .where(
                    DoctorSpecialty.tenant_id == Appointment.tenant_id,
                    DoctorSpecialty.doctor_id == Appointment.doctor_id,
                    DoctorSpecialty.specialty_id == specialty_id,
                )
                .exists()
            )
            productivity_encounters = productivity_encounters.where(
                select(DoctorSpecialty.id)
                .where(
                    DoctorSpecialty.tenant_id == Encounter.tenant_id,
                    DoctorSpecialty.doctor_id == Encounter.doctor_id,
                    DoctorSpecialty.specialty_id == specialty_id,
                )
                .exists()
            )

        appointment_productivity = {
            doctor_id: (total, completed)
            for doctor_id, total, completed in session.execute(
                productivity_appointments
            ).all()
        }
        encounter_productivity = dict(
            session.execute(productivity_encounters).all()
        )
        doctor_ids = set(appointment_productivity) | set(encounter_productivity)
        doctor_names = {}
        if doctor_ids:
            doctor_names = dict(
                session.execute(
                    select(Doctor.id, User.display_name)
                    .join(
                        Membership,
                        (Membership.tenant_id == Doctor.tenant_id)
                        & (Membership.id == Doctor.membership_id),
                    )
                    .join(User, User.id == Membership.user_id)
                    .where(Doctor.tenant_id == tenant_id, Doctor.id.in_(doctor_ids))
                ).all()
            )

        productivity = []
        for doctor_id in doctor_ids:
            appointment_total, completed_appointments = appointment_productivity.get(
                doctor_id, (0, 0)
            )
            completed_for_doctor = encounter_productivity.get(doctor_id, 0)
            productivity.append(
                DoctorProductivity(
                    doctor_id=doctor_id,
                    doctor_name=doctor_names[doctor_id],
                    completed_encounters=completed_for_doctor,
                    appointments_total=appointment_total,
                    completed_appointments=completed_appointments,
                    completion_rate_percent=(
                        round(completed_appointments / appointment_total * 100, 1)
                        if appointment_total
                        else 0.0
                    ),
                )
            )
        productivity.sort(
            key=lambda row: (
                -row.completed_encounters,
                -row.appointments_total,
                row.doctor_name.casefold(),
            )
        )

        return AdminDashboard(
            generated_at=datetime.now(timezone.utc),
            filters=DashboardFilters(
                start_date=start_date,
                end_date=end_date,
                site_id=site_id,
                specialty_id=specialty_id,
            ),
            sites=[
                DashboardSiteOption(
                    id=site.id,
                    code=site.code,
                    name=site.name,
                )
                for site in sites
            ],
            specialties=[
                DashboardSpecialtyOption(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                )
                for row in specialties
            ],
            patients_registered=patients_registered,
            appointments_by_status=appointments_by_status,
            available_doctors=available_doctors,
            completed_encounters=completed_encounters,
            productivity=productivity,
        )
