import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import engine as application_engine
from app.db.models import Membership, Permission, Role, Tenant, User
from app.domains.identity.authorization import (
    load_authorization_context,
    require_permission,
)
from app.domains.identity.models import membership_roles, role_permissions


@dataclass(frozen=True)
class IdentityFixture:
    tenant_id: UUID
    subject: str


@pytest.fixture
def identity_fixture() -> IdentityFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for PostgreSQL RBAC tests")

    identity = IdentityFixture(tenant_id=uuid4(), subject=f"test-sub-{uuid4().hex}")
    user_id = uuid4()
    membership_id = uuid4()
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    with migration_engine.begin() as connection:
        role_id = connection.scalar(
            select(Role.id).where(Role.code == "doctor")
        )
        assert role_id is not None, "RBAC roles must be seeded by Alembic"
        connection.execute(
            Tenant.__table__.insert().values(
                id=identity.tenant_id,
                name="Synthetic identity tenant",
                slug=f"identity-{identity.tenant_id.hex[:12]}",
            )
        )
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                identity_provider_subject=identity.subject,
                email="synthetic@example.invalid",
                display_name="Synthetic User",
                is_active=True,
            )
        )
        connection.execute(
            Membership.__table__.insert().values(
                id=membership_id,
                tenant_id=identity.tenant_id,
                user_id=user_id,
                status="active",
            )
        )
        connection.execute(
            membership_roles.insert().values(
                tenant_id=identity.tenant_id,
                membership_id=membership_id,
                role_id=role_id,
            )
        )

    try:
        yield identity
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                membership_roles.delete().where(
                    membership_roles.c.tenant_id == identity.tenant_id
                )
            )
            connection.execute(
                Membership.__table__.delete().where(
                    Membership.tenant_id == identity.tenant_id
                )
            )
            connection.execute(
                User.__table__.delete().where(
                    User.identity_provider_subject == identity.subject
                )
            )
            connection.execute(
                Tenant.__table__.delete().where(Tenant.id == identity.tenant_id)
            )
        migration_engine.dispose()


def _claims(identity: IdentityFixture, *, mfa: bool = True) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": identity.subject,
        "email": "synthetic@example.invalid",
        "name": "Synthetic User",
    }
    if mfa:
        claims["amr"] = ["pwd", "otp"]
    return claims


def test_seeded_doctor_can_write_clinical_data(
    identity_fixture: IdentityFixture,
) -> None:
    context = load_authorization_context(
        _claims(identity_fixture),
        identity_fixture.tenant_id,
    )

    assert "doctor" in context.role_codes
    assert require_permission("clinical:write")(context) == context


def test_migration_registers_the_five_roles_and_role_permissions() -> None:
    migration_engine = create_engine(
        get_settings().migration_database_url,
        pool_pre_ping=True,
    )
    try:
        with migration_engine.connect() as connection:
            roles = set(connection.scalars(select(Role.code)).all())
            doctor_permissions = set(
                connection.scalars(
                    select(Permission.code)
                    .join(
                        role_permissions,
                        role_permissions.c.permission_id == Permission.id,
                    )
                    .join(Role, Role.id == role_permissions.c.role_id)
                    .where(Role.code == "doctor")
                ).all()
            )
            permission_rows = connection.execute(
                select(Role.code, Permission.code)
                .join(
                    role_permissions,
                    role_permissions.c.role_id == Role.id,
                )
                .join(
                    Permission,
                    role_permissions.c.permission_id == Permission.id,
                )
            ).all()
        permissions_by_role: dict[str, set[str]] = {}
        for role_code, permission_code in permission_rows:
            permissions_by_role.setdefault(role_code, set()).add(permission_code)
        assert {
            "superadmin",
            "administrator",
            "doctor",
            "service",
            "receptionist",
        } <= roles
        assert doctor_permissions == {
            "appointments:read",
            "clinical:read",
            "clinical:write",
        }
        assert permissions_by_role["superadmin"] == {
            "platform:manage",
            "tenant:manage",
            "users:manage",
        }
        assert "clinical:read" not in permissions_by_role["administrator"]
        assert "clinical:read" not in permissions_by_role["service"]
        assert "clinical:read" not in permissions_by_role["receptionist"]
        assert "clinical:write" not in permissions_by_role["receptionist"]
        assert permissions_by_role["receptionist"] >= {
            "patients:manage",
            "appointments:manage",
        }
    finally:
        migration_engine.dispose()


def test_seeded_doctor_is_denied_platform_administration(
    identity_fixture: IdentityFixture,
) -> None:
    context = load_authorization_context(
        _claims(identity_fixture),
        identity_fixture.tenant_id,
    )

    with pytest.raises(HTTPException) as error:
        require_permission("platform:manage")(context)
    assert error.value.status_code == 403


def test_privileged_role_requires_mfa_evidence(
    identity_fixture: IdentityFixture,
) -> None:
    with pytest.raises(HTTPException) as error:
        load_authorization_context(
            _claims(identity_fixture, mfa=False),
            identity_fixture.tenant_id,
        )
    assert error.value.status_code == 403
    assert error.value.detail == "Multi-factor authentication is required for this role"


def test_unrelated_tenant_membership_is_not_authorized(
    identity_fixture: IdentityFixture,
) -> None:
    other_tenant_id = uuid4()
    with pytest.raises(HTTPException) as error:
        load_authorization_context(_claims(identity_fixture), other_tenant_id)
    assert error.value.status_code == 403


def test_runtime_cannot_assign_a_platform_role(
    identity_fixture: IdentityFixture,
) -> None:
    with Session(application_engine) as session:
        user = session.scalar(
            select(User).where(
                User.identity_provider_subject == identity_fixture.subject
            )
        )
        role_id = session.scalar(select(Role.id).where(Role.code == "superadmin"))
        assert user is not None and role_id is not None
        user.platform_role_id = role_id
        with pytest.raises(DBAPIError):
            session.flush()
        session.rollback()
