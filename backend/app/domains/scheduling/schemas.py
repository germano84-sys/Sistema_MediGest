from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domains.patients.schemas import PatientAPIModel


class SchedulingModel(PatientAPIModel):
    pass


class AppointmentCreate(SchedulingModel):
    site_id: UUID
    patient_id: UUID
    doctor_id: UUID
    service_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    reason: str = Field(min_length=1, max_length=300)
    operational_notes: str | None = Field(default=None, max_length=1000)
    status: Literal["scheduled", "confirmed"] = "scheduled"

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("starts_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_duration_or_service(self) -> "AppointmentCreate":
        if self.duration_minutes is None and self.service_id is None:
            raise ValueError("duration_minutes is required when no service is selected")
        return self


class AppointmentChangeRequest(SchedulingModel):
    action: Literal["confirm", "cancel", "reschedule"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=300)
    starts_at: datetime | None = None
    doctor_id: UUID | None = None
    service_id: UUID | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("starts_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_action_fields(self) -> "AppointmentChangeRequest":
        if self.action == "reschedule" and self.starts_at is None:
            raise ValueError("starts_at is required when rescheduling")
        if self.action != "reschedule" and any(
            value is not None
            for value in (self.starts_at, self.doctor_id, self.service_id, self.duration_minutes)
        ):
            raise ValueError("Schedule fields are only valid when rescheduling")
        return self


class AppointmentOut(SchedulingModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    patient_id: UUID
    patient_name: str
    doctor_id: UUID
    doctor_name: str
    service_id: UUID | None
    service_name: str | None
    starts_at: datetime
    ends_at: datetime
    duration_minutes: int
    reason: str
    operational_notes: str | None
    status: str
    version: int


class AppointmentHistoryOut(SchedulingModel):
    id: UUID
    appointment_id: UUID
    actor_user_id: UUID
    action: str
    reason: str
    changes: dict[str, object]
    created_at: datetime


class AppointmentPage(SchedulingModel):
    items: list[AppointmentOut]
    total: int


class AvailabilitySlot(SchedulingModel):
    doctor_id: UUID
    doctor_name: str
    specialty_ids: list[UUID]
    service_id: UUID | None
    starts_at: datetime
    ends_at: datetime
    duration_minutes: int


class AvailabilityResponse(SchedulingModel):
    site_id: UUID
    timezone: str
    duration_minutes: int
    items: list[AvailabilitySlot]


class HolidayCreate(SchedulingModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=120)


class HolidayOut(SchedulingModel):
    id: UUID
    site_id: UUID
    holiday_date: date
    name: str


class SchedulingDoctorOption(SchedulingModel):
    id: UUID
    name: str
    specialty_ids: list[UUID]


class SchedulingSpecialtyOption(SchedulingModel):
    id: UUID
    name: str


class SchedulingServiceOption(SchedulingModel):
    id: UUID
    name: str
    duration_minutes: int


class SchedulingCatalog(SchedulingModel):
    site_id: UUID
    timezone: str
    doctors: list[SchedulingDoctorOption]
    specialties: list[SchedulingSpecialtyOption]
    services: list[SchedulingServiceOption]
