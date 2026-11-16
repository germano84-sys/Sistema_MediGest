from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    JSON,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.domains.clinical.models import Doctor
    from app.domains.patients.models import Patient
    from app.domains.tenants.models import Site
    from app.domains.clinical.models import Encounter


class Service(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "site_id", "code"),
        CheckConstraint("duration_minutes > 0", name="positive_duration"),
        CheckConstraint("price >= 0", name="nonnegative_price"),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        server_default="0",
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    site: Mapped[Site] = relationship(
        back_populates="services",
        primaryjoin=(
            "and_(Service.tenant_id == Site.tenant_id, "
            "foreign(Service.site_id) == Site.id)"
        ),
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="service",
        primaryjoin=(
            "and_(Service.tenant_id == Appointment.tenant_id, "
            "Service.id == foreign(Appointment.service_id))"
        ),
    )


class Appointment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "id", "patient_id"),
        Index("ix_appointments_tenant_site_start", "tenant_id", "site_id", "starts_at"),
        Index(
            "ix_appointments_tenant_site_queue_entered",
            "tenant_id",
            "site_id",
            "queue_entered_at",
        ),
        Index("ix_appointments_tenant_patient_start", "tenant_id", "patient_id", "starts_at"),
        Index("ix_appointments_tenant_doctor_start", "tenant_id", "doctor_id", "starts_at"),
        CheckConstraint("ends_at > starts_at", name="end_after_start"),
        CheckConstraint(
            "status IN ('scheduled', 'confirmed', 'checked_in', 'completed', "
            "'cancelled', 'no_show')",
            name="status",
        ),
        CheckConstraint(
            "checked_in_at IS NULL OR arrival_confirmed_at IS NOT NULL",
            name="checkin_requires_arrival",
        ),
        CheckConstraint(
            "queue_entered_at IS NULL OR checked_in_at IS NOT NULL",
            name="queue_requires_checkin",
        ),
        CheckConstraint(
            "service_status IN ('pending', 'preparing', 'ready', 'completed')",
            name="service_status",
        ),
        CheckConstraint(
            "service_status NOT IN ('preparing', 'ready', 'completed') "
            "OR preparation_started_at IS NOT NULL",
            name="preparation_time_required",
        ),
        CheckConstraint(
            "service_status NOT IN ('ready', 'completed') OR ready_at IS NOT NULL",
            name="ready_time_required",
        ),
        CheckConstraint(
            "service_status != 'completed' OR attention_completed_at IS NOT NULL",
            name="completion_time_required",
        ),
        CheckConstraint(
            "preparation_started_at IS NULL OR queue_entered_at IS NOT NULL",
            name="preparation_requires_queue",
        ),
        CheckConstraint(
            "ready_at IS NULL OR preparation_started_at IS NOT NULL",
            name="ready_requires_preparation",
        ),
        CheckConstraint(
            "attention_started_at IS NULL OR ready_at IS NOT NULL",
            name="attention_requires_ready",
        ),
        CheckConstraint(
            "attention_completed_at IS NULL OR attention_started_at IS NOT NULL",
            name="completion_requires_attention",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "site_id", "service_room_id"],
            ["clinic_rooms.tenant_id", "clinic_rooms.site_id", "clinic_rooms.id"],
            name="fk_appointments_tenant_site_room_clinic_rooms",
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    doctor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    service_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="scheduled")
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    operational_notes: Mapped[str | None] = mapped_column(Text)
    arrival_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )
    service_room_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    preparation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attention_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attention_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __mapper_args__ = {"version_id_col": version}

    patient: Mapped[Patient] = relationship(
        back_populates="appointments",
        primaryjoin=(
            "and_(Appointment.tenant_id == Patient.tenant_id, "
            "foreign(Appointment.patient_id) == Patient.id)"
        ),
    )
    site: Mapped[Site] = relationship(
        back_populates="appointments",
        primaryjoin=(
            "and_(Appointment.tenant_id == Site.tenant_id, "
            "foreign(Appointment.site_id) == Site.id)"
        ),
    )
    doctor: Mapped[Doctor | None] = relationship(
        back_populates="appointments",
        primaryjoin=(
            "and_(Appointment.tenant_id == Doctor.tenant_id, "
            "foreign(Appointment.doctor_id) == Doctor.id)"
        ),
    )
    service: Mapped[Service | None] = relationship(
        back_populates="appointments",
        primaryjoin=(
            "and_(Appointment.tenant_id == Service.tenant_id, "
            "foreign(Appointment.service_id) == Service.id)"
        ),
    )
    encounter: Mapped[Encounter | None] = relationship(
        primaryjoin=(
            "and_(Appointment.tenant_id == Encounter.tenant_id, "
            "Appointment.id == foreign(Encounter.appointment_id), "
            "Appointment.patient_id == Encounter.patient_id)"
        ),
        viewonly=True,
    )


class SiteHoliday(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "site_holidays"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "site_id",
            "holiday_date",
            name="uq_site_holidays_tenant_site_date",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_site_holidays_tenant_site_sites",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class AppointmentHistory(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "appointment_history"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index(
            "ix_appointment_history_tenant_appointment_created",
            "tenant_id",
            "appointment_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "appointment_id"],
            ["appointments.tenant_id", "appointments.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
