from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Column,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Index,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.domains.tenants.models import Tenant
    from app.domains.clinical.models import AuditEvent


membership_roles = Table(
    "membership_roles",
    Base.metadata,
    Column("tenant_id", ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True),
    Column("membership_id", primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    ForeignKeyConstraint(
        ["tenant_id", "membership_id"],
        ["memberships.tenant_id", "memberships.id"],
        ondelete="CASCADE",
    ),
)

membership_site_roles = Table(
    "membership_site_roles",
    Base.metadata,
    Column("tenant_id", ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True),
    Column("site_id", primary_key=True),
    Column("membership_id", primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    ForeignKeyConstraint(
        ["tenant_id", "site_id"],
        ["sites.tenant_id", "sites.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["tenant_id", "membership_id"],
        ["memberships.tenant_id", "memberships.id"],
        ondelete="CASCADE",
    ),
)
Index(
    "ix_membership_site_roles_tenant_site_membership",
    membership_site_roles.c.tenant_id,
    membership_site_roles.c.site_id,
    membership_site_roles.c.membership_id,
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("identity_provider_subject"),)

    identity_provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform_role_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="actor")


class Role(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )


class Permission(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code"),)

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )


class Membership(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "user_id"),
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    roles: Mapped[list[Role]] = relationship(
        secondary=membership_roles,
        primaryjoin=lambda: (Membership.tenant_id == membership_roles.c.tenant_id)
        & (Membership.id == membership_roles.c.membership_id),
        secondaryjoin=lambda: Role.id == membership_roles.c.role_id,
    )
