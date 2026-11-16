from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.domains.identity.models import Membership
    from app.domains.identity.models import User
    from app.domains.patients.models import Patient
    from app.domains.scheduling.models import Appointment
    from app.domains.tenants.models import Site, Tenant


class Specialty(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "specialties"
    __table_args__ = (UniqueConstraint("code"),)

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    doctors: Mapped[list[Doctor]] = relationship(back_populates="specialty")


class Doctor(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "membership_id"),
        UniqueConstraint("tenant_id", "license_number"),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    specialty_id: Mapped[UUID] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    license_number: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    membership: Mapped[Membership] = relationship(
        primaryjoin=(
            "and_(Doctor.tenant_id == Membership.tenant_id, "
            "foreign(Doctor.membership_id) == Membership.id)"
        )
    )
    specialty: Mapped[Specialty] = relationship(back_populates="doctors")
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="doctor",
        primaryjoin=(
            "and_(Doctor.tenant_id == Appointment.tenant_id, "
            "Doctor.id == foreign(Appointment.doctor_id))"
        ),
    )
    encounters: Mapped[list[Encounter]] = relationship(
        back_populates="doctor",
        primaryjoin=(
            "and_(Doctor.tenant_id == Encounter.tenant_id, "
            "Doctor.id == foreign(Encounter.doctor_id))"
        ),
    )


class DoctorSpecialty(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctor_specialties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "doctor_id",
            "specialty_id",
            name="uq_doctor_specialties_tenant_doctor_specialty",
        ),
        Index(
            "uq_doctor_specialties_one_primary",
            "tenant_id",
            "doctor_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index(
            "ix_doctor_specialties_tenant_specialty",
            "tenant_id",
            "specialty_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["specialty_id"],
            ["specialties.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    doctor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    specialty_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default="false")


class DoctorAvailability(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "doctor_id",
            "site_id",
            "weekday",
            "starts_at",
            name="uq_doctor_availability_doctor_site_weekday_start",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("ends_at > starts_at", name="valid_interval"),
        ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_doctor_availability_tenant_site_weekday",
            "tenant_id",
            "site_id",
            "weekday",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    doctor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[time] = mapped_column(Time(), nullable=False)
    ends_at: Mapped[time] = mapped_column(Time(), nullable=False)
    is_available: Mapped[bool] = mapped_column(nullable=False, server_default="true")


class ClinicalRecord(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinical_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "id", "patient_id"),
        UniqueConstraint("tenant_id", "patient_id"),
        UniqueConstraint("tenant_id", "record_number"),
        CheckConstraint("status IN ('open', 'closed')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    record_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")

    patient: Mapped[Patient] = relationship(
        back_populates="clinical_record",
        primaryjoin=(
            "and_(ClinicalRecord.tenant_id == Patient.tenant_id, "
            "foreign(ClinicalRecord.patient_id) == Patient.id)"
        ),
    )
    encounters: Mapped[list[Encounter]] = relationship(
        back_populates="clinical_record",
        primaryjoin=(
            "and_(ClinicalRecord.tenant_id == Encounter.tenant_id, "
            "ClinicalRecord.id == foreign(Encounter.clinical_record_id), "
            "ClinicalRecord.patient_id == Encounter.patient_id)"
        ),
    )


class Encounter(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "appointment_id"),
        Index("ix_encounters_tenant_patient_started", "tenant_id", "patient_id", "started_at"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="end_after_start",
        ),
        CheckConstraint("status IN ('in_progress', 'completed', 'cancelled')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "clinical_record_id", "patient_id"],
            ["clinical_records.tenant_id", "clinical_records.id", "clinical_records.patient_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "appointment_id", "patient_id"],
            ["appointments.tenant_id", "appointments.id", "appointments.patient_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    clinical_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    doctor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="in_progress")

    clinical_record: Mapped[ClinicalRecord] = relationship(
        back_populates="encounters",
        primaryjoin=(
            "and_(Encounter.tenant_id == ClinicalRecord.tenant_id, "
            "foreign(Encounter.clinical_record_id) == ClinicalRecord.id, "
            "Encounter.patient_id == ClinicalRecord.patient_id)"
        ),
    )
    patient: Mapped[Patient] = relationship(
        primaryjoin=(
            "and_(Encounter.tenant_id == Patient.tenant_id, "
            "foreign(Encounter.patient_id) == Patient.id)"
        )
    )
    appointment: Mapped[Appointment | None] = relationship(
        primaryjoin=(
            "and_(Encounter.tenant_id == Appointment.tenant_id, "
            "foreign(Encounter.appointment_id) == Appointment.id, "
            "Encounter.patient_id == Appointment.patient_id)"
        ),
        viewonly=True,
    )
    site: Mapped[Site] = relationship(
        back_populates="encounters",
        primaryjoin=(
            "and_(Encounter.tenant_id == Site.tenant_id, "
            "foreign(Encounter.site_id) == Site.id)"
        ),
    )
    doctor: Mapped[Doctor] = relationship(
        back_populates="encounters",
        primaryjoin=(
            "and_(Encounter.tenant_id == Doctor.tenant_id, "
            "foreign(Encounter.doctor_id) == Doctor.id)"
        ),
    )
    diagnoses: Mapped[list[Diagnosis]] = relationship(
        back_populates="encounter",
        primaryjoin=(
            "and_(Encounter.tenant_id == Diagnosis.tenant_id, "
            "Encounter.id == foreign(Diagnosis.encounter_id))"
        ),
    )
    prescriptions: Mapped[list[Prescription]] = relationship(
        back_populates="encounter",
        primaryjoin=(
            "and_(Encounter.tenant_id == Prescription.tenant_id, "
            "Encounter.id == foreign(Prescription.encounter_id))"
        ),
    )
    orders: Mapped[list[MedicalOrder]] = relationship(
        back_populates="encounter",
        primaryjoin=(
            "and_(Encounter.tenant_id == MedicalOrder.tenant_id, "
            "Encounter.id == foreign(MedicalOrder.encounter_id))"
        ),
    )


class Diagnosis(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "encounter_id", "code_system", "code"),
        Index("ix_diagnoses_tenant_encounter", "tenant_id", "encounter_id"),
        CheckConstraint("status IN ('active', 'resolved')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "encounter_id"],
            ["encounters.tenant_id", "encounters.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code_system: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    diagnosed_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    encounter: Mapped[Encounter] = relationship(
        back_populates="diagnoses",
        primaryjoin=(
            "and_(Diagnosis.tenant_id == Encounter.tenant_id, "
            "foreign(Diagnosis.encounter_id) == Encounter.id)"
        ),
    )


class Prescription(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_prescriptions_tenant_encounter", "tenant_id", "encounter_id"),
        CheckConstraint("status IN ('active', 'cancelled', 'completed')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "encounter_id"],
            ["encounters.tenant_id", "encounters.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    medication_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(120))
    route: Mapped[str | None] = mapped_column(String(80))
    frequency: Mapped[str | None] = mapped_column(String(120))
    instructions: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    encounter: Mapped[Encounter] = relationship(
        back_populates="prescriptions",
        primaryjoin=(
            "and_(Prescription.tenant_id == Encounter.tenant_id, "
            "foreign(Prescription.encounter_id) == Encounter.id)"
        ),
    )


class MedicalOrder(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "medical_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_medical_orders_tenant_encounter", "tenant_id", "encounter_id"),
        CheckConstraint("status IN ('requested', 'in_progress', 'completed', 'cancelled')", name="status"),
        ForeignKeyConstraint(
            ["tenant_id", "encounter_id"],
            ["encounters.tenant_id", "encounters.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="requested")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    encounter: Mapped[Encounter] = relationship(
        back_populates="orders",
        primaryjoin=(
            "and_(MedicalOrder.tenant_id == Encounter.tenant_id, "
            "foreign(MedicalOrder.encounter_id) == Encounter.id)"
        ),
    )


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(128))
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    tenant: Mapped[Tenant | None] = relationship(back_populates="audit_events")
    actor: Mapped[User | None] = relationship(back_populates="audit_events")
