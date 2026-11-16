from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.domains.patients.schemas import PatientAPIModel


class DoctorAgendaAppointment(PatientAPIModel):
    appointment_id: UUID
    patient_name: str
    starts_at: datetime
    ends_at: datetime
    appointment_status: Literal[
        "scheduled", "confirmed", "checked_in", "completed", "cancelled", "no_show"
    ]
    arrival_status: Literal[
        "waiting", "arrived", "checked_in", "completed", "cancelled", "no_show"
    ]
    arrival_confirmed_at: datetime | None
    checked_in_at: datetime | None
    queue_entered_at: datetime | None
    attention_status: Literal[
        "not_started", "pending", "in_progress", "completed", "cancelled"
    ]
    encounter_id: UUID | None
    clinical_record_id: UUID | None


class DoctorDashboard(PatientAPIModel):
    date: date
    timezone: str
    doctor_name: str
    appointments: list[DoctorAgendaAppointment]
    pending_attentions: list[DoctorAgendaAppointment]


class ClinicalDiagnosis(PatientAPIModel):
    code_system: str
    code: str
    description: str
    diagnosed_on: date
    status: str
    is_primary: bool


class ClinicalPrescription(PatientAPIModel):
    medication_name: str
    dosage: str | None
    route: str | None
    frequency: str | None
    instructions: str | None
    issued_at: datetime
    status: str


class ClinicalOrder(PatientAPIModel):
    order_type: str
    description: str
    status: str
    requested_at: datetime


class ClinicalEncounterDetail(PatientAPIModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None
    status: str
    diagnoses: list[ClinicalDiagnosis]
    prescriptions: list[ClinicalPrescription]
    orders: list[ClinicalOrder]


class ClinicalRecordDetail(PatientAPIModel):
    id: UUID
    record_number: str
    status: str
    patient_name: str
    encounters: list[ClinicalEncounterDetail]
