from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Appointment,
    AppointmentHistory,
    AuditEvent,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Membership,
    Patient,
    Service,
    Site,
    SiteHoliday,
    SiteHours,
    Specialty,
    TenantSpecialty,
    User,
)
from app.db.session import tenant_session
from app.domains.identity.authorization import AuthorizationContext, load_authorization_context
from app.domains.identity.router import get_verified_claims
from app.domains.scheduling.schemas import (
    AppointmentCreate,
    AppointmentChangeRequest,
    AppointmentHistoryOut,
    AppointmentOut,
    AppointmentPage,
    AvailabilityResponse,
    AvailabilitySlot,
    HolidayCreate,
    HolidayOut,
    SchedulingCatalog,
    SchedulingDoctorOption,
    SchedulingServiceOption,
    SchedulingSpecialtyOption,
)

router = APIRouter(prefix="/api/v1/admin/tenants", tags=["appointment scheduling"])
BLOCKING_STATUSES = ("scheduled", "confirmed", "checked_in", "completed")
MAX_CALENDAR_RANGE_DAYS = 62
SLOT_INTERVAL_MINUTES = 15


def _context(
    claims: dict[str, Any],
    tenant_id: UUID,
    site_id: UUID,
    permission: str,
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id, site_id)
    if permission not in context.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient appointment permissions",
        )
    return context


def _doctor_scope(
    session: Session,
    tenant_id: UUID,
    context: AuthorizationContext,
) -> UUID | None:
    if "doctor" not in context.role_codes:
        return None
    doctor_id = session.scalar(
        select(Doctor.id)
        .join(
            Membership,
            (Membership.tenant_id == Doctor.tenant_id)
            & (Membership.id == Doctor.membership_id),
        )
        .where(
            Doctor.tenant_id == tenant_id,
            Doctor.is_active.is_(True),
            Membership.user_id == context.user_id,
            Membership.status == "active",
        )
    )
    if doctor_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active doctor profile is required",
        )
    return doctor_id


def _site(session: Session, tenant_id: UUID, site_id: UUID) -> Site:
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


def _configured_specialty(
    session: Session,
    tenant_id: UUID,
    specialty_id: UUID,
) -> Specialty:
    specialty = session.scalar(
        select(Specialty)
        .join(TenantSpecialty, TenantSpecialty.specialty_id == Specialty.id)
        .where(
            TenantSpecialty.tenant_id == tenant_id,
            TenantSpecialty.is_active.is_(True),
            Specialty.id == specialty_id,
            Specialty.is_active.is_(True),
        )
    )
    if specialty is None:
        raise HTTPException(status_code=404, detail="Specialty not found")
    return specialty


def _doctor_rows(
    session: Session,
    tenant_id: UUID,
    site_id: UUID,
    specialty_id: UUID | None = None,
    doctor_id: UUID | None = None,
) -> list[tuple[Doctor, User]]:
    has_site_hours = (
        select(DoctorAvailability.id)
        .where(
            DoctorAvailability.tenant_id == tenant_id,
            DoctorAvailability.doctor_id == Doctor.id,
            DoctorAvailability.site_id == site_id,
            DoctorAvailability.is_available.is_(True),
        )
        .exists()
    )
    query = (
        select(Doctor, User)
        .join(Membership, Membership.id == Doctor.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Doctor.tenant_id == tenant_id,
            Doctor.is_active.is_(True),
            Membership.status == "active",
            User.is_active.is_(True),
            has_site_hours,
        )
    )
    if doctor_id is not None:
        query = query.where(Doctor.id == doctor_id)
    if specialty_id is not None:
        query = query.where(
            select(DoctorSpecialty.id)
            .where(
                DoctorSpecialty.tenant_id == tenant_id,
                DoctorSpecialty.doctor_id == Doctor.id,
                DoctorSpecialty.specialty_id == specialty_id,
            )
            .exists()
        )
    return list(session.execute(query.order_by(User.display_name, Doctor.id)).all())


def _doctor_specialties(
    session: Session,
    tenant_id: UUID,
    doctor_id: UUID,
) -> list[UUID]:
    return list(
        session.scalars(
            select(DoctorSpecialty.specialty_id)
            .join(Specialty, Specialty.id == DoctorSpecialty.specialty_id)
            .join(
                TenantSpecialty,
                TenantSpecialty.specialty_id == Specialty.id,
            )
            .where(
                DoctorSpecialty.tenant_id == tenant_id,
                DoctorSpecialty.doctor_id == doctor_id,
                Specialty.is_active.is_(True),
                TenantSpecialty.tenant_id == tenant_id,
                TenantSpecialty.is_active.is_(True),
            )
            .order_by(DoctorSpecialty.specialty_id)
        ).all()
    )


def _date_bounds(
    date_from: date,
    date_to: date,
    *,
    max_days: int = MAX_CALENDAR_RANGE_DAYS,
) -> None:
    if date_to < date_from:
        raise HTTPException(
            status_code=422,
            detail="date_to must not be earlier than date_from",
        )
    if (date_to - date_from).days + 1 > max_days:
        raise HTTPException(
            status_code=422,
            detail=f"Date range must not exceed {max_days} days",
        )


def _valid_local_instants(value: datetime, zone: ZoneInfo) -> list[datetime]:
    instants: list[datetime] = []
    seen: set[datetime] = set()
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        utc_value = candidate.astimezone(timezone.utc)
        if utc_value.astimezone(zone).replace(tzinfo=None) == value and utc_value not in seen:
            instants.append(candidate)
            seen.add(utc_value)
    return instants


def _site_holiday(
    session: Session,
    tenant_id: UUID,
    site_id: UUID,
    day: date,
) -> SiteHoliday | None:
    return session.scalar(
        select(SiteHoliday).where(
            SiteHoliday.tenant_id == tenant_id,
            SiteHoliday.site_id == site_id,
            SiteHoliday.holiday_date == day,
        )
    )


def _site_hours_allow(
    session: Session,
    tenant_id: UUID,
    site_id: UUID,
    day: date,
    starts_at: time,
    ends_at: time,
) -> bool:
    hours = session.scalar(
        select(SiteHours).where(
            SiteHours.tenant_id == tenant_id,
            SiteHours.site_id == site_id,
            SiteHours.weekday == day.weekday(),
        )
    )
    if hours is None:
        return True
    return bool(
        not hours.is_closed
        and hours.opens_at is not None
        and hours.closes_at is not None
        and starts_at >= hours.opens_at
        and ends_at <= hours.closes_at
    )


def _doctor_schedule_allows(
    session: Session,
    tenant_id: UUID,
    doctor_id: UUID,
    site_id: UUID,
    day: date,
    starts_at: time,
    ends_at: time,
) -> bool:
    return (
        session.scalar(
            select(DoctorAvailability.id).where(
                DoctorAvailability.tenant_id == tenant_id,
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.site_id == site_id,
                DoctorAvailability.weekday == day.weekday(),
                DoctorAvailability.is_available.is_(True),
                DoctorAvailability.starts_at <= starts_at,
                DoctorAvailability.ends_at >= ends_at,
            )
        )
        is not None
    )


def _validate_working_hours(
    session: Session,
    *,
    tenant_id: UUID,
    site: Site,
    doctor_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    zone = ZoneInfo(site.timezone)
    local_start = starts_at.astimezone(zone)
    local_end = ends_at.astimezone(zone)
    if local_start.date() != local_end.date():
        raise HTTPException(status_code=422, detail="Appointment must stay within one local day")
    if _site_holiday(session, tenant_id, site.id, local_start.date()) is not None:
        raise HTTPException(status_code=409, detail="Appointments cannot be booked on a site holiday")
    if not _doctor_schedule_allows(
        session,
        tenant_id,
        doctor_id,
        site.id,
        local_start.date(),
        local_start.timetz().replace(tzinfo=None),
        local_end.timetz().replace(tzinfo=None),
    ):
        raise HTTPException(
            status_code=409,
            detail="Appointment is outside the doctor's available hours",
        )
    if not _site_hours_allow(
        session,
        tenant_id,
        site.id,
        local_start.date(),
        local_start.timetz().replace(tzinfo=None),
        local_end.timetz().replace(tzinfo=None),
    ):
        raise HTTPException(status_code=409, detail="Appointment is outside site opening hours")


def _appointment_out(
    appointment: Appointment,
    patient_name: str,
    doctor_name: str,
    service_name: str | None,
) -> AppointmentOut:
    duration = int((appointment.ends_at - appointment.starts_at).total_seconds() // 60)
    return AppointmentOut(
        id=appointment.id,
        tenant_id=appointment.tenant_id,
        site_id=appointment.site_id,
        patient_id=appointment.patient_id,
        patient_name=patient_name,
        doctor_id=appointment.doctor_id,
        doctor_name=doctor_name,
        service_id=appointment.service_id,
        service_name=service_name,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        duration_minutes=duration,
        reason=appointment.reason,
        operational_notes=appointment.operational_notes,
        status=appointment.status,
        version=appointment.version,
    )


def _audit(
    session: Session,
    context: AuthorizationContext,
    *,
    tenant_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    event_data: dict[str, Any],
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=context.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            event_data=event_data,
        )
    )


def _lock_appointment_resources(
    session: Session,
    *,
    tenant_id: UUID,
    doctor_ids: set[UUID],
    patient_id: UUID,
    site_id: UUID,
    dates: set[date],
) -> None:
    keys = sorted(
        {
            *(f"doctor:{tenant_id}:{doctor_id}" for doctor_id in doctor_ids),
            f"patient:{tenant_id}:{patient_id}",
            *(
                f"holiday:{tenant_id}:{site_id}:{day.isoformat()}"
                for day in dates
            ),
        }
    )
    for lock_key in keys:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )


def _appointment_history(
    session: Session,
    *,
    context: AuthorizationContext,
    appointment: Appointment,
    action: str,
    reason: str,
    changes: dict[str, Any],
) -> None:
    session.add(
        AppointmentHistory(
            id=uuid4(),
            tenant_id=appointment.tenant_id,
            appointment_id=appointment.id,
            actor_user_id=context.user_id,
            action=action,
            reason=reason,
            changes=changes,
        )
    )


def _current_appointment_state(appointment: Appointment) -> dict[str, str | None]:
    return {
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
        "doctor_id": str(appointment.doctor_id) if appointment.doctor_id else None,
        "service_id": str(appointment.service_id) if appointment.service_id else None,
        "site_id": str(appointment.site_id),
    }


@router.get(
    "/{tenant_id}/scheduling/catalog",
    response_model=SchedulingCatalog,
)
def get_scheduling_catalog(
    tenant_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> SchedulingCatalog:
    _context(claims, tenant_id, site_id, "appointments:read")
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, site_id)
        doctors = _doctor_rows(session, tenant_id, site_id)
        specialties = session.execute(
            select(Specialty.id, Specialty.name)
            .join(TenantSpecialty, TenantSpecialty.specialty_id == Specialty.id)
            .where(
                TenantSpecialty.tenant_id == tenant_id,
                TenantSpecialty.is_active.is_(True),
                Specialty.is_active.is_(True),
            )
            .order_by(Specialty.name, Specialty.id)
        ).all()
        services = session.scalars(
            select(Service)
            .where(
                Service.tenant_id == tenant_id,
                Service.site_id == site_id,
                Service.is_active.is_(True),
            )
            .order_by(Service.name, Service.id)
        ).all()
        return SchedulingCatalog(
            site_id=site_id,
            timezone=site.timezone,
            doctors=[
                SchedulingDoctorOption(
                    id=doctor.id,
                    name=user.display_name,
                    specialty_ids=_doctor_specialties(session, tenant_id, doctor.id),
                )
                for doctor, user in doctors
            ],
            specialties=[
                SchedulingSpecialtyOption(id=row.id, name=row.name)
                for row in specialties
            ],
            services=[
                SchedulingServiceOption(
                    id=service.id,
                    name=service.name,
                    duration_minutes=service.duration_minutes,
                )
                for service in services
            ],
        )


@router.get(
    "/{tenant_id}/scheduling/availability",
    response_model=AvailabilityResponse,
)
def get_availability(
    tenant_id: UUID,
    site_id: UUID,
    date_from: date,
    date_to: date,
    doctor_id: UUID | None = None,
    specialty_id: UUID | None = None,
    service_id: UUID | None = None,
    duration_minutes: int = Query(default=30, ge=5, le=480),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> AvailabilityResponse:
    _context(claims, tenant_id, site_id, "appointments:read")
    _date_bounds(date_from, date_to, max_days=31)
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, site_id)
        if specialty_id is not None:
            _configured_specialty(session, tenant_id, specialty_id)
        if service_id is not None:
            service = session.scalar(
                select(Service).where(
                    Service.tenant_id == tenant_id,
                    Service.site_id == site_id,
                    Service.id == service_id,
                    Service.is_active.is_(True),
                )
            )
            if service is None:
                raise HTTPException(status_code=404, detail="Active service not found")
            duration_minutes = service.duration_minutes
        doctors = _doctor_rows(
            session,
            tenant_id,
            site_id,
            specialty_id=specialty_id,
            doctor_id=doctor_id,
        )
        zone = ZoneInfo(site.timezone)
        start_bound = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc)
        end_bound = datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        holidays = set(
            session.scalars(
                select(SiteHoliday.holiday_date).where(
                    SiteHoliday.tenant_id == tenant_id,
                    SiteHoliday.site_id == site_id,
                    SiteHoliday.holiday_date >= date_from,
                    SiteHoliday.holiday_date <= date_to,
                )
            ).all()
        )
        schedules = session.scalars(
            select(DoctorAvailability).where(
                DoctorAvailability.tenant_id == tenant_id,
                DoctorAvailability.site_id == site_id,
                DoctorAvailability.is_available.is_(True),
                DoctorAvailability.doctor_id.in_([doctor.id for doctor, _ in doctors]),
            )
        ).all() if doctors else []
        schedules_by_doctor: dict[UUID, list[DoctorAvailability]] = {}
        for schedule in schedules:
            schedules_by_doctor.setdefault(schedule.doctor_id, []).append(schedule)
        busy_rows = session.execute(
            select(Appointment.doctor_id, Appointment.starts_at, Appointment.ends_at)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.doctor_id.in_([doctor.id for doctor, _ in doctors]),
                Appointment.status.in_(BLOCKING_STATUSES),
                Appointment.starts_at < end_bound,
                Appointment.ends_at > start_bound,
            )
        ).all() if doctors else []
        busy_by_doctor: dict[UUID, list[tuple[datetime, datetime]]] = {}
        for busy_doctor_id, busy_start, busy_end in busy_rows:
            busy_by_doctor.setdefault(busy_doctor_id, []).append((busy_start, busy_end))

        slots: list[AvailabilitySlot] = []
        now = datetime.now(timezone.utc)
        for doctor, user in doctors:
            doctor_specialties = _doctor_specialties(session, tenant_id, doctor.id)
            for offset in range((date_to - date_from).days + 1):
                day = date_from + timedelta(days=offset)
                if day in holidays:
                    continue
                day_schedules = [
                    item
                    for item in schedules_by_doctor.get(doctor.id, [])
                    if item.weekday == day.weekday()
                ]
                if not day_schedules:
                    continue
                site_hours = session.scalar(
                    select(SiteHours).where(
                        SiteHours.tenant_id == tenant_id,
                        SiteHours.site_id == site_id,
                        SiteHours.weekday == day.weekday(),
                    )
                )
                if site_hours is not None and (
                    site_hours.is_closed
                    or site_hours.opens_at is None
                    or site_hours.closes_at is None
                ):
                    continue
                for schedule in day_schedules:
                    minute = schedule.starts_at.hour * 60 + schedule.starts_at.minute
                    remainder = minute % SLOT_INTERVAL_MINUTES
                    if remainder:
                        minute += SLOT_INTERVAL_MINUTES - remainder
                    end_minute = schedule.ends_at.hour * 60 + schedule.ends_at.minute
                    while minute + duration_minutes <= end_minute:
                        naive_start = datetime.combine(day, time(minute // 60, minute % 60))
                        naive_end = naive_start + timedelta(minutes=duration_minutes)
                        if naive_end.date() != day:
                            minute += SLOT_INTERVAL_MINUTES
                            continue
                        if site_hours is not None and (
                            naive_start.time() < site_hours.opens_at
                            or naive_end.time() > site_hours.closes_at
                        ):
                            minute += SLOT_INTERVAL_MINUTES
                            continue
                        for local_start in _valid_local_instants(naive_start, zone):
                            utc_start = local_start.astimezone(timezone.utc)
                            utc_end = utc_start + timedelta(minutes=duration_minutes)
                            local_end = utc_end.astimezone(zone)
                            if local_end.date() != day:
                                continue
                            if any(
                                utc_start < busy_end and utc_end > busy_start
                                for busy_start, busy_end in busy_by_doctor.get(doctor.id, [])
                            ):
                                continue
                            if utc_start <= now:
                                continue
                            slots.append(
                                AvailabilitySlot(
                                    doctor_id=doctor.id,
                                    doctor_name=user.display_name,
                                    specialty_ids=doctor_specialties,
                                    service_id=service_id,
                                    starts_at=local_start,
                                    ends_at=local_end,
                                    duration_minutes=duration_minutes,
                                )
                            )
                        minute += SLOT_INTERVAL_MINUTES
        slots.sort(key=lambda slot: (slot.starts_at, slot.doctor_name, slot.doctor_id))
        return AvailabilityResponse(
            site_id=site_id,
            timezone=site.timezone,
            duration_minutes=duration_minutes,
            items=slots,
        )


@router.get(
    "/{tenant_id}/appointments",
    response_model=AppointmentPage,
)
def list_appointments(
    tenant_id: UUID,
    site_id: UUID,
    date_from: date,
    date_to: date,
    doctor_id: UUID | None = None,
    specialty_id: UUID | None = None,
    service_id: UUID | None = None,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(scheduled|confirmed|checked_in|completed|cancelled|no_show)$",
    ),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> AppointmentPage:
    context = _context(claims, tenant_id, site_id, "appointments:read")
    _date_bounds(date_from, date_to)
    with tenant_session(tenant_id) as session:
        authorized_doctor_id = _doctor_scope(session, tenant_id, context)
        if (
            authorized_doctor_id is not None
            and doctor_id is not None
            and doctor_id != authorized_doctor_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Doctors can only view their own appointments",
            )
        site = _site(session, tenant_id, site_id)
        if specialty_id is not None:
            _configured_specialty(session, tenant_id, specialty_id)
        zone = ZoneInfo(site.timezone)
        start_bound = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc)
        end_bound = datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        query = (
            select(Appointment, Patient, User, Service)
            .join(Patient, Patient.id == Appointment.patient_id)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .join(Membership, Membership.id == Doctor.membership_id)
            .join(User, User.id == Membership.user_id)
            .outerjoin(Service, Service.id == Appointment.service_id)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.starts_at >= start_bound,
                Appointment.starts_at < end_bound,
            )
        )
        if authorized_doctor_id is not None:
            query = query.where(Appointment.doctor_id == authorized_doctor_id)
        elif doctor_id is not None:
            query = query.where(Appointment.doctor_id == doctor_id)
        if service_id is not None:
            query = query.where(Appointment.service_id == service_id)
        if specialty_id is not None:
            query = query.where(
                select(DoctorSpecialty.id)
                .where(
                    DoctorSpecialty.tenant_id == tenant_id,
                    DoctorSpecialty.doctor_id == Appointment.doctor_id,
                    DoctorSpecialty.specialty_id == specialty_id,
                )
                .exists()
            )
        if status_filter is not None:
            query = query.where(Appointment.status == status_filter)
        rows = session.execute(
            query.order_by(Appointment.starts_at, User.display_name, Appointment.id)
        ).all()
        return AppointmentPage(
            items=[
                _appointment_out(
                    appointment,
                    f"{patient.given_name} {patient.family_name}",
                    user.display_name,
                    service.name if service else None,
                )
                for appointment, patient, user, service in rows
            ],
            total=len(rows),
        )


@router.post(
    "/{tenant_id}/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    tenant_id: UUID,
    payload: AppointmentCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> AppointmentOut:
    context = _context(
        claims,
        tenant_id,
        payload.site_id,
        "appointments:manage",
    )
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, payload.site_id)
        patient = session.scalar(
            select(Patient).where(
                Patient.tenant_id == tenant_id,
                Patient.id == payload.patient_id,
                Patient.status == "active",
            )
        )
        if patient is None:
            raise HTTPException(status_code=404, detail="Active patient not found")
        doctor_rows = _doctor_rows(
            session,
            tenant_id,
            payload.site_id,
            doctor_id=payload.doctor_id,
        )
        if not doctor_rows:
            raise HTTPException(status_code=404, detail="Active doctor is not available at this site")
        doctor, doctor_user = doctor_rows[0]
        service = None
        if payload.service_id is not None:
            service = session.scalar(
                select(Service).where(
                    Service.tenant_id == tenant_id,
                    Service.site_id == payload.site_id,
                    Service.id == payload.service_id,
                    Service.is_active.is_(True),
                )
            )
            if service is None:
                raise HTTPException(status_code=404, detail="Active service not found")
        if (
            service is not None
            and payload.duration_minutes is not None
            and payload.duration_minutes != service.duration_minutes
        ):
            raise HTTPException(
                status_code=422,
                detail="Appointment duration must match the selected service",
            )
        duration = service.duration_minutes if service else payload.duration_minutes
        if duration is None:
            raise HTTPException(status_code=422, detail="Appointment duration is required")
        if not 5 <= duration <= 480:
            raise HTTPException(
                status_code=422,
                detail="Appointment duration must be between 5 and 480 minutes",
            )
        starts_at = payload.starts_at.astimezone(timezone.utc)
        ends_at = starts_at + timedelta(minutes=duration)
        if starts_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="Appointments must be scheduled in the future")
        local_date = starts_at.astimezone(ZoneInfo(site.timezone)).date()
        _lock_appointment_resources(
            session,
            tenant_id=tenant_id,
            doctor_ids={doctor.id},
            patient_id=patient.id,
            site_id=site.id,
            dates={local_date},
        )
        _validate_working_hours(
            session,
            tenant_id=tenant_id,
            site=site,
            doctor_id=doctor.id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        overlap = session.scalar(
            select(Appointment.id)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.doctor_id == doctor.id,
                Appointment.status.in_(BLOCKING_STATUSES),
                Appointment.starts_at < ends_at,
                Appointment.ends_at > starts_at,
            )
            .limit(1)
        )
        if overlap is not None:
            raise HTTPException(status_code=409, detail="Doctor already has an overlapping appointment")
        patient_overlap = session.scalar(
            select(Appointment.id)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.patient_id == patient.id,
                Appointment.status.in_(BLOCKING_STATUSES),
                Appointment.starts_at < ends_at,
                Appointment.ends_at > starts_at,
            )
            .limit(1)
        )
        if patient_overlap is not None:
            raise HTTPException(status_code=409, detail="Patient already has an overlapping appointment")
        appointment = Appointment(
            id=uuid4(),
            tenant_id=tenant_id,
            site_id=payload.site_id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            service_id=service.id if service else None,
            starts_at=starts_at,
            ends_at=ends_at,
            status=payload.status,
            reason=payload.reason,
            operational_notes=payload.operational_notes,
        )
        session.add(appointment)
        session.flush()
        _appointment_history(
            session,
            context=context,
            appointment=appointment,
            action="created",
            reason="Cita agendada",
            changes={"after": _current_appointment_state(appointment)},
        )
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="create",
            entity_type="appointment",
            entity_id=appointment.id,
            event_data={
                "site_id": str(payload.site_id),
                "doctor_id": str(doctor.id),
                "starts_at": starts_at.isoformat(),
                "duration_minutes": duration,
                "status": appointment.status,
            },
        )
        return _appointment_out(
            appointment,
            f"{patient.given_name} {patient.family_name}",
            doctor_user.display_name,
            service.name if service else None,
        )


@router.patch(
    "/{tenant_id}/appointments/{appointment_id}",
    response_model=AppointmentOut,
)
def change_appointment(
    tenant_id: UUID,
    appointment_id: UUID,
    site_id: UUID,
    payload: AppointmentChangeRequest,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> AppointmentOut:
    context = _context(
        claims,
        tenant_id,
        site_id,
        "appointments:manage",
    )
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, site_id)
        appointment = session.scalar(
            select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.id == appointment_id,
            ).with_for_update()
        )
        if appointment is None:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if appointment.version != payload.expected_version:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Appointment was changed by another request; reload and retry "
                    f"(current version: {appointment.version})"
                ),
            )
        before = _current_appointment_state(appointment)
        if payload.action == "confirm":
            if appointment.status != "scheduled":
                raise HTTPException(
                    status_code=409,
                    detail="Only scheduled appointments can be confirmed",
                )
            _lock_appointment_resources(
                session,
                tenant_id=tenant_id,
                doctor_ids={appointment.doctor_id} if appointment.doctor_id else set(),
                patient_id=appointment.patient_id,
                site_id=site_id,
                dates={appointment.starts_at.astimezone(ZoneInfo(site.timezone)).date()},
            )
            appointment.status = "confirmed"
            action = "confirmed"
        elif payload.action == "cancel":
            if appointment.status not in {"scheduled", "confirmed"}:
                raise HTTPException(
                    status_code=409,
                    detail="Only scheduled or confirmed appointments can be cancelled",
                )
            _lock_appointment_resources(
                session,
                tenant_id=tenant_id,
                doctor_ids={appointment.doctor_id} if appointment.doctor_id else set(),
                patient_id=appointment.patient_id,
                site_id=site_id,
                dates={appointment.starts_at.astimezone(ZoneInfo(site.timezone)).date()},
            )
            appointment.status = "cancelled"
            action = "cancelled"
        else:
            if appointment.status not in {"scheduled", "confirmed"}:
                raise HTTPException(
                    status_code=409,
                    detail="Only scheduled or confirmed appointments can be rescheduled",
                )
            if payload.starts_at is None:
                raise HTTPException(status_code=422, detail="starts_at is required")
            service_id = (
                payload.service_id
                if "service_id" in payload.model_fields_set
                else appointment.service_id
            )
            service = None
            if service_id is not None:
                service = session.scalar(
                    select(Service).where(
                        Service.tenant_id == tenant_id,
                        Service.site_id == site_id,
                        Service.id == service_id,
                        Service.is_active.is_(True),
                    )
                )
                if service is None:
                    raise HTTPException(status_code=404, detail="Active service not found")
            if service is not None:
                if (
                    payload.duration_minutes is not None
                    and payload.duration_minutes != service.duration_minutes
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Appointment duration must match the selected service",
                    )
                duration = service.duration_minutes
            else:
                duration = (
                    payload.duration_minutes
                    if payload.duration_minutes is not None
                    else int((appointment.ends_at - appointment.starts_at).total_seconds() // 60)
                )
            if not 5 <= duration <= 480:
                raise HTTPException(
                    status_code=422,
                    detail="Appointment duration must be between 5 and 480 minutes",
                )
            doctor_id = payload.doctor_id or appointment.doctor_id
            if doctor_id is None:
                raise HTTPException(status_code=409, detail="Appointment has no assigned doctor")
            doctor_rows = _doctor_rows(
                session,
                tenant_id,
                site_id,
                doctor_id=doctor_id,
            )
            if not doctor_rows:
                raise HTTPException(
                    status_code=404,
                    detail="Active doctor is not available at this site",
                )
            doctor, _ = doctor_rows[0]
            starts_at = payload.starts_at.astimezone(timezone.utc)
            ends_at = starts_at + timedelta(minutes=duration)
            if starts_at <= datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=422,
                    detail="Appointments must be scheduled in the future",
                )
            local_date = starts_at.astimezone(ZoneInfo(site.timezone)).date()
            old_local_date = appointment.starts_at.astimezone(
                ZoneInfo(site.timezone)
            ).date()
            _lock_appointment_resources(
                session,
                tenant_id=tenant_id,
                doctor_ids={doctor_id, appointment.doctor_id} if appointment.doctor_id else {doctor_id},
                patient_id=appointment.patient_id,
                site_id=site_id,
                dates={local_date, old_local_date},
            )
            _validate_working_hours(
                session,
                tenant_id=tenant_id,
                site=site,
                doctor_id=doctor_id,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            overlaps = session.scalar(
                select(Appointment.id)
                .where(
                    Appointment.tenant_id == tenant_id,
                    Appointment.id != appointment.id,
                    Appointment.doctor_id == doctor_id,
                    Appointment.status.in_(BLOCKING_STATUSES),
                    Appointment.starts_at < ends_at,
                    Appointment.ends_at > starts_at,
                )
                .limit(1)
            )
            if overlaps is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Doctor already has an overlapping appointment",
                )
            patient_overlap = session.scalar(
                select(Appointment.id)
                .where(
                    Appointment.tenant_id == tenant_id,
                    Appointment.id != appointment.id,
                    Appointment.patient_id == appointment.patient_id,
                    Appointment.status.in_(BLOCKING_STATUSES),
                    Appointment.starts_at < ends_at,
                    Appointment.ends_at > starts_at,
                )
                .limit(1)
            )
            if patient_overlap is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Patient already has an overlapping appointment",
                )
            appointment.starts_at = starts_at
            appointment.ends_at = ends_at
            appointment.doctor_id = doctor_id
            appointment.service_id = service.id if service else None
            action = "rescheduled"
        session.flush()
        after = _current_appointment_state(appointment)
        _appointment_history(
            session,
            context=context,
            appointment=appointment,
            action=action,
            reason=payload.reason,
            changes={"before": before, "after": after},
        )
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action=f"appointment_{action}",
            entity_type="appointment",
            entity_id=appointment.id,
            event_data={"status": appointment.status, "version": appointment.version},
        )
        patient = session.scalar(
            select(Patient).where(
                Patient.tenant_id == tenant_id,
                Patient.id == appointment.patient_id,
            )
        )
        doctor_row = session.execute(
            select(User.display_name)
            .join(Membership, Membership.user_id == User.id)
            .join(Doctor, Doctor.membership_id == Membership.id)
            .where(
                Doctor.tenant_id == tenant_id,
                Doctor.id == appointment.doctor_id,
            )
        ).one()
        service = (
            session.scalar(
                select(Service).where(
                    Service.tenant_id == tenant_id,
                    Service.id == appointment.service_id,
                )
            )
            if appointment.service_id
            else None
        )
        if patient is None:
            raise HTTPException(status_code=404, detail="Appointment patient not found")
        return _appointment_out(
            appointment,
            f"{patient.given_name} {patient.family_name}",
            doctor_row.display_name,
            service.name if service else None,
        )


@router.get(
    "/{tenant_id}/appointments/{appointment_id}/history",
    response_model=list[AppointmentHistoryOut],
)
def list_appointment_history(
    tenant_id: UUID,
    appointment_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[AppointmentHistoryOut]:
    context = _context(claims, tenant_id, site_id, "appointments:read")
    with tenant_session(tenant_id) as session:
        authorized_doctor_id = _doctor_scope(session, tenant_id, context)
        appointment = session.scalar(
            select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.id == appointment_id,
            )
        )
        if (
            appointment is None
            or (
                authorized_doctor_id is not None
                and appointment.doctor_id != authorized_doctor_id
            )
        ):
            raise HTTPException(status_code=404, detail="Appointment not found")
        rows = session.scalars(
            select(AppointmentHistory)
            .where(
                AppointmentHistory.tenant_id == tenant_id,
                AppointmentHistory.appointment_id == appointment_id,
            )
            .order_by(AppointmentHistory.created_at, AppointmentHistory.id)
        ).all()
        return [
            AppointmentHistoryOut.model_validate(row)
            for row in rows
        ]


@router.get(
    "/{tenant_id}/sites/{site_id}/holidays",
    response_model=list[HolidayOut],
)
def list_site_holidays(
    tenant_id: UUID,
    site_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[HolidayOut]:
    _context(claims, tenant_id, site_id, "appointments:read")
    if date_from is not None and date_to is not None:
        _date_bounds(date_from, date_to)
    with tenant_session(tenant_id) as session:
        _site(session, tenant_id, site_id)
        query = select(SiteHoliday).where(
            SiteHoliday.tenant_id == tenant_id,
            SiteHoliday.site_id == site_id,
        )
        if date_from is not None:
            query = query.where(SiteHoliday.holiday_date >= date_from)
        if date_to is not None:
            query = query.where(SiteHoliday.holiday_date <= date_to)
        holidays = session.scalars(
            query.order_by(SiteHoliday.holiday_date, SiteHoliday.id)
        ).all()
        return [
            HolidayOut(
                id=holiday.id,
                site_id=holiday.site_id,
                holiday_date=holiday.holiday_date,
                name=holiday.name,
            )
            for holiday in holidays
        ]


@router.post(
    "/{tenant_id}/sites/{site_id}/holidays",
    response_model=HolidayOut,
    status_code=status.HTTP_201_CREATED,
)
def create_site_holiday(
    tenant_id: UUID,
    site_id: UUID,
    payload: HolidayCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> HolidayOut:
    context = _context(claims, tenant_id, site_id, "tenant:manage")
    try:
        with tenant_session(tenant_id) as session:
            _site(session, tenant_id, site_id)
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {
                    "lock_key": (
                        f"holiday:{tenant_id}:{site_id}:"
                        f"{payload.holiday_date.isoformat()}"
                    )
                },
            )
            holiday = SiteHoliday(
                id=uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                holiday_date=payload.holiday_date,
                name=payload.name,
            )
            session.add(holiday)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="site_holiday",
                entity_id=holiday.id,
                event_data={"site_id": str(site_id), "holiday_date": payload.holiday_date.isoformat()},
            )
            return HolidayOut(
                id=holiday.id,
                site_id=site_id,
                holiday_date=holiday.holiday_date,
                name=holiday.name,
            )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A holiday is already configured for this site and date",
        ) from exc


@router.delete(
    "/{tenant_id}/sites/{site_id}/holidays/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_site_holiday(
    tenant_id: UUID,
    site_id: UUID,
    holiday_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Response:
    context = _context(claims, tenant_id, site_id, "tenant:manage")
    with tenant_session(tenant_id) as session:
        holiday = session.scalar(
            select(SiteHoliday).where(
                SiteHoliday.tenant_id == tenant_id,
                SiteHoliday.site_id == site_id,
                SiteHoliday.id == holiday_id,
            )
        )
        if holiday is None:
            raise HTTPException(status_code=404, detail="Holiday not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="site_holiday",
            entity_id=holiday.id,
            event_data={"site_id": str(site_id), "holiday_date": holiday.holiday_date.isoformat()},
        )
        session.delete(holiday)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
