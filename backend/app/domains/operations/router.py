from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, text
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import Session

from app.db.models import (
    Appointment,
    AuditEvent,
    ClinicRoom,
    Doctor,
    Membership,
    Patient,
    Site,
    User,
)
from app.db.session import tenant_session
from app.domains.identity.authorization import AuthorizationContext, load_authorization_context
from app.domains.identity.router import get_verified_claims
from app.domains.operations.reception import ReceptionAction, apply_reception_action
from app.domains.operations.service_queue import apply_service_action
from app.domains.operations.schemas import (
    ReceptionActionRequest,
    ReceptionActionResult,
    ReceptionAppointment,
    ReceptionAppointmentPage,
    ServiceQueueActionRequest,
    ServiceQueueActionResult,
    ServiceQueueItem,
    ServiceQueuePage,
    ServiceRoomOption,
)

router = APIRouter(prefix="/api/v1/admin/tenants", tags=["patient reception"])


def _context(
    claims: dict[str, Any],
    tenant_id: UUID,
    site_id: UUID,
    permissions: tuple[str, ...],
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id, site_id)
    if not set(permissions).issubset(context.permission_codes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient operations permissions",
        )
    return context


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


@router.get(
    "/{tenant_id}/operations/reception/appointments",
    response_model=ReceptionAppointmentPage,
)
def list_reception_appointments(
    tenant_id: UUID,
    site_id: UUID,
    day: date | None = Query(default=None, alias="date"),
    q: str | None = Query(default=None, max_length=100),
    doctor_id: UUID | None = None,
    status_filter: Literal[
        "scheduled", "confirmed", "checked_in", "completed", "cancelled", "no_show"
    ] | None = Query(default=None, alias="status"),
    queue: Literal["waiting", "sent"] | None = None,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ReceptionAppointmentPage:
    _context(
        claims,
        tenant_id,
        site_id,
        ("appointments:read", "patients:manage"),
    )
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, site_id)
        zone = ZoneInfo(site.timezone)
        reception_date = day or datetime.now(zone).date()
        start_bound = datetime.combine(
            reception_date, time.min, tzinfo=zone
        ).astimezone(timezone.utc)
        end_bound = datetime.combine(
            reception_date + timedelta(days=1), time.min, tzinfo=zone
        ).astimezone(timezone.utc)
        query = (
            select(Appointment, Patient, User)
            .join(
                Patient,
                (Patient.tenant_id == Appointment.tenant_id)
                & (Patient.id == Appointment.patient_id),
            )
            .join(
                Doctor,
                (Doctor.tenant_id == Appointment.tenant_id)
                & (Doctor.id == Appointment.doctor_id),
            )
            .join(Membership, Membership.id == Doctor.membership_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.starts_at >= start_bound,
                Appointment.starts_at < end_bound,
            )
        )
        if doctor_id is not None:
            query = query.where(Appointment.doctor_id == doctor_id)
        if status_filter is not None:
            query = query.where(Appointment.status == status_filter)
        if queue == "waiting":
            query = query.where(
                Appointment.checked_in_at.is_not(None),
                Appointment.queue_entered_at.is_(None),
            )
        elif queue == "sent":
            query = query.where(Appointment.queue_entered_at.is_not(None))
        if q and q.strip():
            search_term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{search_term}%"
            query = query.where(
                or_(
                    Patient.patient_number.ilike(pattern, escape="\\"),
                    Patient.given_name.ilike(pattern, escape="\\"),
                    Patient.family_name.ilike(pattern, escape="\\"),
                    (Patient.given_name + " " + Patient.family_name).ilike(
                        pattern, escape="\\"
                    ),
                )
            )
        rows = session.execute(
            query.order_by(Appointment.starts_at, Patient.family_name, Appointment.id)
        ).all()
        items = [
            ReceptionAppointment(
                id=appointment.id,
                patient_id=patient.id,
                patient_number=patient.patient_number,
                patient_name=f"{patient.given_name} {patient.family_name}",
                doctor_id=appointment.doctor_id,
                doctor_name=user.display_name,
                starts_at=appointment.starts_at,
                ends_at=appointment.ends_at,
                status=appointment.status,
                version=appointment.version,
                arrival_confirmed_at=appointment.arrival_confirmed_at,
                checked_in_at=appointment.checked_in_at,
                queue_entered_at=appointment.queue_entered_at,
            )
            for appointment, patient, user in rows
        ]
        return ReceptionAppointmentPage(
            date=reception_date,
            timezone=site.timezone,
            items=items,
            total=len(items),
        )


@router.post(
    "/{tenant_id}/operations/reception/appointments/{appointment_id}/{action}",
    response_model=ReceptionActionResult,
)
def update_reception_status(
    tenant_id: UUID,
    appointment_id: UUID,
    action: ReceptionAction,
    site_id: UUID,
    payload: ReceptionActionRequest,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ReceptionActionResult:
    context = _context(
        claims,
        tenant_id,
        site_id,
        ("appointments:manage", "patients:manage"),
    )
    with tenant_session(tenant_id) as session:
        _site(session, tenant_id, site_id)
        appointment = session.scalar(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.id == appointment_id,
            )
            .with_for_update()
        )
        if appointment is None:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if appointment.version != payload.expected_version:
            raise HTTPException(
                status_code=409,
                detail="Appointment was changed by another request; reload and retry",
            )

        occurred_at = datetime.now(timezone.utc)
        apply_reception_action(appointment, action, occurred_at)
        try:
            session.flush()
        except StaleDataError as error:
            raise HTTPException(
                status_code=409,
                detail="Appointment was changed by another request; reload and retry",
            ) from error
        session.add(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor_user_id=context.user_id,
                action=f"reception_{action.replace('-', '_')}",
                entity_type="appointment",
                entity_id=appointment.id,
                event_data={"site_id": str(site_id), "status": appointment.status},
            )
        )
        return ReceptionActionResult(
            appointment_id=appointment.id,
            action=action,
            occurred_at=occurred_at,
            status=appointment.status,
            version=appointment.version,
        )


@router.get(
    "/{tenant_id}/operations/service/queue",
    response_model=ServiceQueuePage,
)
def list_service_queue(
    tenant_id: UUID,
    site_id: UUID,
    day: date | None = Query(default=None, alias="date"),
    status_filter: Literal["pending", "preparing", "ready", "completed"] | None = Query(
        default=None,
        alias="status",
    ),
    room_id: UUID | None = None,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ServiceQueuePage:
    _context(
        claims,
        tenant_id,
        site_id,
        ("appointments:read", "operations:manage"),
    )
    with tenant_session(tenant_id) as session:
        site = _site(session, tenant_id, site_id)
        zone = ZoneInfo(site.timezone)
        queue_date = day or datetime.now(zone).date()
        start_bound = datetime.combine(queue_date, time.min, tzinfo=zone).astimezone(
            timezone.utc
        )
        end_bound = datetime.combine(
            queue_date + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        query = (
            select(Appointment, Patient, User, ClinicRoom)
            .join(
                Patient,
                (Patient.tenant_id == Appointment.tenant_id)
                & (Patient.id == Appointment.patient_id),
            )
            .outerjoin(
                Doctor,
                (Doctor.tenant_id == Appointment.tenant_id)
                & (Doctor.id == Appointment.doctor_id),
            )
            .outerjoin(Membership, Membership.id == Doctor.membership_id)
            .outerjoin(User, User.id == Membership.user_id)
            .outerjoin(
                ClinicRoom,
                (ClinicRoom.tenant_id == Appointment.tenant_id)
                & (ClinicRoom.site_id == Appointment.site_id)
                & (ClinicRoom.id == Appointment.service_room_id),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.queue_entered_at >= start_bound,
                Appointment.queue_entered_at < end_bound,
            )
        )
        if status_filter is not None:
            query = query.where(Appointment.service_status == status_filter)
        if room_id is not None:
            query = query.where(Appointment.service_room_id == room_id)

        rows = session.execute(
            query.order_by(Appointment.queue_entered_at, Appointment.id)
        ).all()
        rooms = session.scalars(
            select(ClinicRoom)
            .where(
                ClinicRoom.tenant_id == tenant_id,
                ClinicRoom.site_id == site_id,
                ClinicRoom.is_active.is_(True),
            )
            .order_by(ClinicRoom.name, ClinicRoom.id)
        ).all()
        items = [
            ServiceQueueItem(
                appointment_id=appointment.id,
                patient_name=f"{patient.given_name} {patient.family_name}",
                doctor_name=user.display_name if user else None,
                appointment_starts_at=appointment.starts_at,
                queue_entered_at=appointment.queue_entered_at,
                service_status=appointment.service_status,
                version=appointment.version,
                room_id=appointment.service_room_id,
                room_code=room.code if room else None,
                room_name=room.name if room else None,
                preparation_started_at=appointment.preparation_started_at,
                ready_at=appointment.ready_at,
                attention_started_at=appointment.attention_started_at,
                attention_completed_at=appointment.attention_completed_at,
            )
            for appointment, patient, user, room in rows
        ]
        return ServiceQueuePage(
            date=queue_date,
            timezone=site.timezone,
            items=items,
            rooms=[
                ServiceRoomOption(id=room.id, code=room.code, name=room.name)
                for room in rooms
            ],
            total=len(items),
        )


def _lock_service_room(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    appointment_id: UUID,
    room_id: UUID,
) -> None:
    lock_key = f"service-room:{tenant_id}:{site_id}:{room_id}"
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
    occupied = session.scalar(
        select(Appointment.id)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.site_id == site_id,
            Appointment.id != appointment_id,
            Appointment.service_room_id == room_id,
            Appointment.attention_started_at.is_not(None),
            Appointment.attention_completed_at.is_(None),
        )
        .limit(1)
    )
    if occupied is not None:
        raise HTTPException(status_code=409, detail="Room is currently in use")


@router.patch(
    "/{tenant_id}/operations/service/queue/{appointment_id}",
    response_model=ServiceQueueActionResult,
)
def update_service_queue_item(
    tenant_id: UUID,
    appointment_id: UUID,
    site_id: UUID,
    payload: ServiceQueueActionRequest,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ServiceQueueActionResult:
    context = _context(
        claims,
        tenant_id,
        site_id,
        ("appointments:read", "operations:manage"),
    )
    with tenant_session(tenant_id) as session:
        _site(session, tenant_id, site_id)
        appointment = session.scalar(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.id == appointment_id,
                Appointment.queue_entered_at.is_not(None),
            )
            .with_for_update()
        )
        if appointment is None:
            raise HTTPException(status_code=404, detail="Queued appointment not found")
        if appointment.version != payload.expected_version:
            raise HTTPException(
                status_code=409,
                detail="Appointment was changed by another request; reload and retry",
            )

        if payload.action == "assign-room":
            room = session.scalar(
                select(ClinicRoom).where(
                    ClinicRoom.tenant_id == tenant_id,
                    ClinicRoom.site_id == site_id,
                    ClinicRoom.id == payload.room_id,
                    ClinicRoom.is_active.is_(True),
                )
            )
            if room is None:
                raise HTTPException(status_code=404, detail="Active room not found")
        if payload.action == "start-attention":
            if appointment.service_room_id is None:
                raise HTTPException(status_code=409, detail="Assign a room before attention")
            _lock_service_room(
                session,
                tenant_id=tenant_id,
                site_id=site_id,
                appointment_id=appointment.id,
                room_id=appointment.service_room_id,
            )

        occurred_at = datetime.now(timezone.utc)
        apply_service_action(
            appointment,
            payload.action,
            occurred_at,
            room_id=payload.room_id,
        )
        try:
            session.flush()
        except StaleDataError as error:
            raise HTTPException(
                status_code=409,
                detail="Appointment was changed by another request; reload and retry",
            ) from error
        session.add(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor_user_id=context.user_id,
                action=f"service_{payload.action.replace('-', '_')}",
                entity_type="appointment",
                entity_id=appointment.id,
                event_data={
                    "site_id": str(site_id),
                    "service_status": appointment.service_status,
                    "room_id": str(appointment.service_room_id)
                    if appointment.service_room_id
                    else None,
                },
            )
        )
        return ServiceQueueActionResult(
            appointment_id=appointment.id,
            action=payload.action,
            service_status=appointment.service_status,
            version=appointment.version,
        )
