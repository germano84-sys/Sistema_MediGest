from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Appointment,
    ClinicalRecord,
    Doctor,
    Encounter,
    Membership,
    Patient,
    Site,
    User,
)
from app.db.session import tenant_session
from app.domains.clinical.schemas import (
    ClinicalDiagnosis,
    ClinicalEncounterDetail,
    ClinicalOrder,
    ClinicalPrescription,
    ClinicalRecordDetail,
    DoctorAgendaAppointment,
    DoctorDashboard,
)
from app.domains.identity.authorization import (
    AuthorizationContext,
    load_authorization_context,
)
from app.domains.identity.router import get_verified_claims

router = APIRouter(prefix="/api/v1/clinical", tags=["clinical"])


def _clinical_context(
    claims: dict[str, Any],
    tenant_id: UUID,
    site_id: UUID,
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id, site_id)
    if (
        "doctor" not in context.role_codes
        or "clinical:read" not in context.permission_codes
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authorized doctor access is required",
        )
    return context


def _active_site(session: Session, tenant_id: UUID, site_id: UUID) -> Site:
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


def _doctor_for_context(
    session: Session,
    tenant_id: UUID,
    context: AuthorizationContext,
) -> tuple[Doctor, User]:
    doctor_row = session.execute(
        select(Doctor, User)
        .join(
            Membership,
            (Membership.tenant_id == Doctor.tenant_id)
            & (Membership.id == Doctor.membership_id),
        )
        .join(User, User.id == Membership.user_id)
        .where(
            Doctor.tenant_id == tenant_id,
            Doctor.is_active.is_(True),
            Membership.user_id == context.user_id,
            Membership.status == "active",
            User.is_active.is_(True),
        )
    ).first()
    if doctor_row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active doctor profile is required",
        )
    return doctor_row


def _agenda_item(
    appointment: Appointment,
    patient: Patient,
    clinical_record: ClinicalRecord | None,
    encounter: Encounter | None,
) -> DoctorAgendaAppointment:
    if appointment.status == "cancelled":
        arrival_status = "cancelled"
    elif appointment.status == "no_show":
        arrival_status = "no_show"
    elif appointment.status == "completed":
        arrival_status = "completed"
    elif appointment.checked_in_at is not None or appointment.status == "checked_in":
        arrival_status = "checked_in"
    elif appointment.arrival_confirmed_at is not None:
        arrival_status = "arrived"
    else:
        arrival_status = "waiting"

    if appointment.status in {"cancelled", "no_show"} or (
        encounter is not None and encounter.status == "cancelled"
    ):
        attention_status = "cancelled"
    elif encounter is not None and encounter.status == "in_progress":
        attention_status = "in_progress"
    elif appointment.status == "completed" or (
        encounter is not None and encounter.status == "completed"
    ):
        attention_status = "completed"
    elif (
        appointment.arrival_confirmed_at is not None
        or appointment.checked_in_at is not None
        or appointment.status == "checked_in"
    ):
        attention_status = "pending"
    else:
        attention_status = "not_started"

    return DoctorAgendaAppointment(
        appointment_id=appointment.id,
        patient_name=f"{patient.given_name} {patient.family_name}",
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        appointment_status=appointment.status,
        arrival_status=arrival_status,
        arrival_confirmed_at=appointment.arrival_confirmed_at,
        checked_in_at=appointment.checked_in_at,
        queue_entered_at=appointment.queue_entered_at,
        attention_status=attention_status,
        encounter_id=encounter.id if encounter is not None else None,
        clinical_record_id=clinical_record.id if clinical_record is not None else None,
    )


@router.get(
    "/tenants/{tenant_id}/dashboard",
    response_model=DoctorDashboard,
)
def get_doctor_dashboard(
    tenant_id: UUID,
    site_id: UUID,
    day: date | None = Query(default=None, alias="date"),
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> DoctorDashboard:
    context = _clinical_context(claims, tenant_id, site_id)
    with tenant_session(tenant_id) as session:
        site = _active_site(session, tenant_id, site_id)
        doctor, user = _doctor_for_context(session, tenant_id, context)
        zone = ZoneInfo(site.timezone)
        dashboard_date = day or datetime.now(zone).date()
        start_bound = datetime.combine(
            dashboard_date,
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        end_bound = datetime.combine(
            dashboard_date + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        rows = session.execute(
            select(Appointment, Patient, ClinicalRecord, Encounter)
            .join(
                Patient,
                (Patient.tenant_id == Appointment.tenant_id)
                & (Patient.id == Appointment.patient_id),
            )
            .outerjoin(
                ClinicalRecord,
                (ClinicalRecord.tenant_id == Appointment.tenant_id)
                & (ClinicalRecord.patient_id == Appointment.patient_id),
            )
            .outerjoin(
                Encounter,
                (Encounter.tenant_id == Appointment.tenant_id)
                & (Encounter.appointment_id == Appointment.id)
                & (Encounter.doctor_id == doctor.id)
                & (Encounter.site_id == site_id),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.doctor_id == doctor.id,
                Appointment.starts_at >= start_bound,
                Appointment.starts_at < end_bound,
            )
            .order_by(Appointment.starts_at, Appointment.id)
        ).all()
        appointments = [
            _agenda_item(appointment, patient, clinical_record, encounter)
            for appointment, patient, clinical_record, encounter in rows
        ]
        return DoctorDashboard(
            date=dashboard_date,
            timezone=site.timezone,
            doctor_name=user.display_name,
            appointments=appointments,
            pending_attentions=[
                appointment
                for appointment in appointments
                if appointment.attention_status in {"pending", "in_progress"}
            ],
        )


@router.get(
    "/tenants/{tenant_id}/records/{record_id}",
    response_model=ClinicalRecordDetail,
)
def get_authorized_clinical_record(
    tenant_id: UUID,
    record_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ClinicalRecordDetail:
    context = _clinical_context(claims, tenant_id, site_id)
    with tenant_session(tenant_id) as session:
        _active_site(session, tenant_id, site_id)
        doctor, _ = _doctor_for_context(session, tenant_id, context)
        authorized_appointment = select(Appointment.id).where(
            Appointment.tenant_id == tenant_id,
            Appointment.site_id == site_id,
            Appointment.doctor_id == doctor.id,
            Appointment.patient_id == ClinicalRecord.patient_id,
            Appointment.status.not_in(("cancelled", "no_show")),
        )
        authorized_encounter = select(Encounter.id).where(
            Encounter.tenant_id == tenant_id,
            Encounter.site_id == site_id,
            Encounter.doctor_id == doctor.id,
            Encounter.patient_id == ClinicalRecord.patient_id,
        )
        row = session.execute(
            select(ClinicalRecord, Patient)
            .join(
                Patient,
                (Patient.tenant_id == ClinicalRecord.tenant_id)
                & (Patient.id == ClinicalRecord.patient_id),
            )
            .where(
                ClinicalRecord.tenant_id == tenant_id,
                ClinicalRecord.id == record_id,
                or_(
                    authorized_appointment.exists(),
                    authorized_encounter.exists(),
                ),
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Clinical record not found")
        clinical_record, patient = row
        encounters = session.scalars(
            select(Encounter)
            .options(
                selectinload(Encounter.diagnoses),
                selectinload(Encounter.prescriptions),
                selectinload(Encounter.orders),
            )
            .where(
                Encounter.tenant_id == tenant_id,
                Encounter.clinical_record_id == clinical_record.id,
                Encounter.patient_id == clinical_record.patient_id,
                Encounter.site_id == site_id,
                Encounter.doctor_id == doctor.id,
            )
            .order_by(Encounter.started_at.desc(), Encounter.id)
        ).all()
        return ClinicalRecordDetail(
            id=clinical_record.id,
            record_number=clinical_record.record_number,
            status=clinical_record.status,
            patient_name=f"{patient.given_name} {patient.family_name}",
            encounters=[
                ClinicalEncounterDetail(
                    id=encounter.id,
                    started_at=encounter.started_at,
                    ended_at=encounter.ended_at,
                    status=encounter.status,
                    diagnoses=[
                        ClinicalDiagnosis.model_validate(diagnosis)
                        for diagnosis in sorted(
                            encounter.diagnoses,
                            key=lambda item: (item.diagnosed_on, item.id),
                            reverse=True,
                        )
                    ],
                    prescriptions=[
                        ClinicalPrescription.model_validate(prescription)
                        for prescription in sorted(
                            encounter.prescriptions,
                            key=lambda item: (item.issued_at, item.id),
                            reverse=True,
                        )
                    ],
                    orders=[
                        ClinicalOrder.model_validate(order)
                        for order in sorted(
                            encounter.orders,
                            key=lambda item: (item.requested_at, item.id),
                            reverse=True,
                        )
                    ],
                )
                for encounter in encounters
            ],
        )
