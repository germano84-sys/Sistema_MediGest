from __future__ import annotations

from datetime import time
from typing import Any
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.domains.identity.models import Membership
    from app.domains.clinical.models import Specialty
    from app.domains.scheduling.models import Appointment, Service
    from app.domains.clinical.models import AuditEvent, Encounter


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug"),
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    sites: Mapped[list[Site]] = relationship(back_populates="tenant")
    memberships: Mapped[list[Membership]] = relationship(back_populates="tenant")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="tenant")
    rooms: Mapped[list[ClinicRoom]] = relationship(back_populates="tenant")
    opening_hours: Mapped[list[SiteHours]] = relationship(back_populates="tenant")
    settings: Mapped[list[TenantSetting]] = relationship(back_populates="tenant")
    specialties: Mapped[list[TenantSpecialty]] = relationship(back_populates="tenant")


class Site(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    tenant: Mapped[Tenant] = relationship(back_populates="sites")
    services: Mapped[list[Service]] = relationship(
        back_populates="site",
        primaryjoin=(
            "and_(Site.tenant_id == Service.tenant_id, "
            "Site.id == foreign(Service.site_id))"
        ),
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="site",
        primaryjoin=(
            "and_(Site.tenant_id == Appointment.tenant_id, "
            "Site.id == foreign(Appointment.site_id))"
        ),
    )
    encounters: Mapped[list[Encounter]] = relationship(
        back_populates="site",
        primaryjoin=(
            "and_(Site.tenant_id == Encounter.tenant_id, "
            "Site.id == foreign(Encounter.site_id))"
        ),
    )
    rooms: Mapped[list[ClinicRoom]] = relationship(
        back_populates="site",
        primaryjoin=(
            "and_(Site.tenant_id == ClinicRoom.tenant_id, "
            "Site.id == foreign(ClinicRoom.site_id))"
        ),
    )
    opening_hours: Mapped[list[SiteHours]] = relationship(
        back_populates="site",
        primaryjoin=(
            "and_(SiteHours.tenant_id == Site.tenant_id, "
            "foreign(SiteHours.site_id) == Site.id)"
        ),
    )


class ClinicRoom(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_rooms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "site_id",
            "id",
            name="uq_clinic_rooms_tenant_site_id",
        ),
        UniqueConstraint("tenant_id", "site_id", "code"),
        Index("ix_clinic_rooms_tenant_site_active", "tenant_id", "site_id", "is_active"),
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
    room_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="consultation")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    tenant: Mapped[Tenant] = relationship(back_populates="rooms")
    site: Mapped[Site] = relationship(
        back_populates="rooms",
        primaryjoin=(
            "and_(ClinicRoom.tenant_id == Site.tenant_id, "
            "foreign(ClinicRoom.site_id) == Site.id)"
        ),
    )


class SiteHours(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "site_hours"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "site_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint(
            "is_closed OR (opens_at IS NOT NULL AND closes_at IS NOT NULL "
            "AND closes_at > opens_at)",
            name="valid_opening_interval",
        ),
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
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time())
    closes_at: Mapped[time | None] = mapped_column(Time())
    is_closed: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    tenant: Mapped[Tenant] = relationship(back_populates="opening_hours")
    site: Mapped[Site] = relationship(
        back_populates="opening_hours",
        primaryjoin=(
            "and_(SiteHours.tenant_id == Site.tenant_id, "
            "foreign(SiteHours.site_id) == Site.id)"
        ),
    )


class TenantSetting(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "key"),
        CheckConstraint("length(key) BETWEEN 1 AND 100", name="key_length"),
        Index("ix_tenant_settings_tenant_key", "tenant_id", "key"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="settings")


class TenantSpecialty(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenant_specialties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "specialty_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="RESTRICT",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    specialty_id: Mapped[UUID] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    tenant: Mapped[Tenant] = relationship(back_populates="specialties")
    specialty: Mapped[Specialty] = relationship()
