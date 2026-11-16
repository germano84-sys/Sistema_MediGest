from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.domains.clinical.models import ClinicalRecord
    from app.domains.scheduling.models import Appointment


class Patient(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "patient_number"),
        Index("ix_patients_tenant_name", "tenant_id", "family_name", "given_name"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_number: Mapped[str] = mapped_column(String(40), nullable=False)
    given_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_date: Mapped[date | None]
    contact_data_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    identifiers: Mapped[list[PatientIdentifier]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )
    emergency_contacts: Mapped[list[PatientEmergencyContact]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
        primaryjoin=(
            "and_(Patient.tenant_id == PatientEmergencyContact.tenant_id, "
            "Patient.id == foreign(PatientEmergencyContact.patient_id))"
        ),
    )
    clinical_record: Mapped[ClinicalRecord | None] = relationship(
        back_populates="patient",
        primaryjoin=(
            "and_(Patient.tenant_id == ClinicalRecord.tenant_id, "
            "Patient.id == foreign(ClinicalRecord.patient_id))"
        ),
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="patient",
        primaryjoin=(
            "and_(Patient.tenant_id == Appointment.tenant_id, "
            "Patient.id == foreign(Appointment.patient_id))"
        ),
    )


class PatientIdentifier(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_identifiers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "identifier_type", "lookup_digest"),
        Index(
            "uq_patient_identifiers_one_primary",
            "tenant_id",
            "patient_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary"),
        ),
        Index("ix_patient_identifiers_patient", "tenant_id", "patient_id"),
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
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lookup_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    value_last_four: Mapped[str | None] = mapped_column(String(4))
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    patient: Mapped[Patient] = relationship(back_populates="identifiers")


class PatientEmergencyContact(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_emergency_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index(
            "ix_patient_emergency_contacts_tenant_patient",
            "tenant_id",
            "patient_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    patient: Mapped[Patient] = relationship(
        back_populates="emergency_contacts",
        primaryjoin=(
            "and_(PatientEmergencyContact.tenant_id == Patient.tenant_id, "
            "foreign(PatientEmergencyContact.patient_id) == Patient.id)"
        ),
    )


class AdministrativeFile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_administrative_files"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "site_id", "patient_id"),
        UniqueConstraint("tenant_id", "site_id", "record_code"),
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
        Index(
            "ix_patient_administrative_files_tenant_site_patient",
            "tenant_id",
            "site_id",
            "patient_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    record_code: Mapped[str] = mapped_column(String(80), nullable=False)


class AdministrativeDocument(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_administrative_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index(
            "ix_patient_administrative_documents_tenant_file",
            "tenant_id",
            "administrative_file_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "administrative_file_id"],
            ["patient_administrative_files.tenant_id", "patient_administrative_files.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="valid_size"),
        CheckConstraint(
            "document_type IN "
            "('identity', 'proof_of_address', 'administrative_form', 'other')",
            name="authorized_type",
        ),
        CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="authorized_content_type",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    administrative_file_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
