from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.patients.schemas import PatientAPIModel
from app.domains.operations.service_queue import ServiceAction, ServiceStatus


class ReceptionAppointment(PatientAPIModel):
    id: UUID
    patient_id: UUID
    patient_number: str
    patient_name: str
    doctor_id: UUID
    doctor_name: str
    starts_at: datetime
    ends_at: datetime
    status: str
    version: int
    arrival_confirmed_at: datetime | None
    checked_in_at: datetime | None
    queue_entered_at: datetime | None


class ReceptionAppointmentPage(PatientAPIModel):
    date: date
    timezone: str
    items: list[ReceptionAppointment]
    total: int


class ReceptionActionRequest(PatientAPIModel):
    expected_version: int = Field(ge=1)


class ReceptionActionResult(PatientAPIModel):
    appointment_id: UUID
    action: Literal["confirm-arrival", "check-in", "send-to-queue"]
    occurred_at: datetime
    status: str
    version: int


class ServiceRoomOption(PatientAPIModel):
    id: UUID
    code: str
    name: str


class ServiceQueueItem(PatientAPIModel):
    appointment_id: UUID
    patient_name: str
    doctor_name: str | None
    appointment_starts_at: datetime
    queue_entered_at: datetime
    service_status: ServiceStatus
    version: int
    room_id: UUID | None
    room_code: str | None
    room_name: str | None
    preparation_started_at: datetime | None
    ready_at: datetime | None
    attention_started_at: datetime | None
    attention_completed_at: datetime | None


class ServiceQueuePage(PatientAPIModel):
    date: date
    timezone: str
    items: list[ServiceQueueItem]
    rooms: list[ServiceRoomOption]
    total: int


class ServiceQueueActionRequest(PatientAPIModel):
    action: ServiceAction
    expected_version: int = Field(ge=1)
    room_id: UUID | None = None

    @model_validator(mode="after")
    def validate_room_assignment(self) -> "ServiceQueueActionRequest":
        if self.action == "assign-room" and self.room_id is None:
            raise ValueError("room_id is required when assigning a room")
        if self.action != "assign-room" and self.room_id is not None:
            raise ValueError("room_id is only valid when assigning a room")
        return self


class ServiceQueueActionResult(PatientAPIModel):
    appointment_id: UUID
    action: ServiceAction
    service_status: ServiceStatus
    version: int
