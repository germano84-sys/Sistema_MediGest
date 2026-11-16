import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select

from app.db.models import (
    AuditEvent,
    Doctor,
    DoctorAvailability,
    DoctorSpecialty,
    Membership,
    Role,
    Site,
    Specialty,
    Tenant,
    TenantSpecialty,
    User,
)
from app.domains.identity.models import membership_roles, membership_site_roles
from app.domains.identity.router import get_verified_claims
from app.db.session import tenant_session
from app.main import app


@dataclass(frozen=True)
class ManagementFixture:
    tenant_id: UUID
    other_tenant_id: UUID
    site_id: UUID
    other_site_id: UUID
    admin_subject: str
    doctor_subject: str
    doctor_membership_id: UUID
    other_membership_id: UUID
    doctor_id: UUID
    specialty_id: UUID
    specialty_code: str


@pytest.fixture
def management_fixture() -> ManagementFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for user management API tests")

    tenant_id = uuid4()
    other_tenant_id = uuid4()
    site_id = uuid4()
    other_site_id = uuid4()
    admin_subject = f"admin-{uuid4().hex}"
    doctor_subject = f"doctor-{uuid4().hex}"
    admin_id = uuid4()
    doctor_user_id = uuid4()
    admin_membership_id = uuid4()
    doctor_membership_id = uuid4()
    other_membership_id = uuid4()
    doctor_id = uuid4()
    specialty_id = uuid4()
    specialty_code = f"TEST{uuid4().hex[:8].upper()}"
    fixture = ManagementFixture(
        tenant_id=tenant_id,
        other_tenant_id=other_tenant_id,
        site_id=site_id,
        other_site_id=other_site_id,
        admin_subject=admin_subject,
        doctor_subject=doctor_subject,
        doctor_membership_id=doctor_membership_id,
        other_membership_id=other_membership_id,
        doctor_id=doctor_id,
        specialty_id=specialty_id,
        specialty_code=specialty_code,
    )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    with migration_engine.begin() as connection:
        administrator_role_id = connection.scalar(
            select(Role.id).where(Role.code == "administrator")
        )
        doctor_role_id = connection.scalar(select(Role.id).where(Role.code == "doctor"))
        assert administrator_role_id is not None
        assert doctor_role_id is not None
        connection.execute(
            Tenant.__table__.insert(),
            [
                {
                    "id": tenant_id,
                    "name": "Synthetic management tenant",
                    "slug": f"management-{tenant_id.hex[:12]}",
                },
                {
                    "id": other_tenant_id,
                    "name": "Synthetic other tenant",
                    "slug": f"management-other-{other_tenant_id.hex[:12]}",
                },
            ],
        )
        connection.execute(
            Site.__table__.insert().values(
                id=site_id,
                tenant_id=tenant_id,
                code="TEST-SITE",
                name="Synthetic site",
                timezone="America/Guayaquil",
                is_active=True,
            )
        )
        connection.execute(
            Site.__table__.insert().values(
                id=other_site_id,
                tenant_id=other_tenant_id,
                code="TEST-SITE",
                name="Synthetic other site",
                timezone="America/Guayaquil",
                is_active=True,
            )
        )
        connection.execute(
            Specialty.__table__.insert().values(
                id=specialty_id,
                code=specialty_code,
                name="Synthetic specialty",
                is_active=True,
            )
        )
        connection.execute(
            TenantSpecialty.__table__.insert().values(
                id=uuid4(),
                tenant_id=tenant_id,
                specialty_id=specialty_id,
                is_active=True,
            )
        )
        connection.execute(
            User.__table__.insert(),
            [
                {
                    "id": admin_id,
                    "identity_provider_subject": admin_subject,
                    "email": "manager@example.invalid",
                    "display_name": "Synthetic Manager",
                    "is_active": True,
                },
                {
                    "id": doctor_user_id,
                    "identity_provider_subject": doctor_subject,
                    "email": "physician@example.invalid",
                    "display_name": "Synthetic Physician",
                    "is_active": True,
                },
            ],
        )
        connection.execute(
            Membership.__table__.insert(),
            [
                {
                    "id": admin_membership_id,
                    "tenant_id": tenant_id,
                    "user_id": admin_id,
                    "status": "active",
                },
                {
                    "id": doctor_membership_id,
                    "tenant_id": tenant_id,
                    "user_id": doctor_user_id,
                    "status": "active",
                },
            ],
        )
        connection.execute(
            Membership.__table__.insert().values(
                id=other_membership_id,
                tenant_id=other_tenant_id,
                user_id=doctor_user_id,
                status="active",
            )
        )
        connection.execute(
            membership_roles.insert().values(
                tenant_id=tenant_id,
                membership_id=admin_membership_id,
                role_id=administrator_role_id,
            )
        )
        connection.execute(
            membership_site_roles.insert().values(
                tenant_id=tenant_id,
                site_id=site_id,
                membership_id=doctor_membership_id,
                role_id=doctor_role_id,
            )
        )
        connection.execute(
            membership_site_roles.insert().values(
                tenant_id=other_tenant_id,
                site_id=other_site_id,
                membership_id=other_membership_id,
                role_id=doctor_role_id,
            )
        )
        connection.execute(
            Doctor.__table__.insert().values(
                id=doctor_id,
                tenant_id=tenant_id,
                membership_id=doctor_membership_id,
                specialty_id=specialty_id,
                license_number=f"LIC-{uuid4().hex[:12]}",
                is_active=True,
            )
        )
        connection.execute(
            DoctorSpecialty.__table__.insert().values(
                id=uuid4(),
                tenant_id=tenant_id,
                doctor_id=doctor_id,
                specialty_id=specialty_id,
                is_primary=True,
            )
        )

    try:
        yield fixture
    finally:
        with migration_engine.begin() as connection:
            user_ids = select(User.id).where(
                User.identity_provider_subject.in_([admin_subject, doctor_subject])
            )
            connection.execute(
                delete(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
            )
            connection.execute(
                delete(DoctorAvailability).where(
                    DoctorAvailability.tenant_id == tenant_id
                )
            )
            connection.execute(
                delete(DoctorSpecialty).where(DoctorSpecialty.tenant_id == tenant_id)
            )
            connection.execute(delete(Doctor).where(Doctor.tenant_id == tenant_id))
            connection.execute(
                delete(TenantSpecialty).where(TenantSpecialty.tenant_id == tenant_id)
            )
            connection.execute(
                membership_site_roles.delete().where(
                    membership_site_roles.c.tenant_id.in_(
                        [tenant_id, other_tenant_id]
                    )
                )
            )
            connection.execute(
                membership_roles.delete().where(
                    membership_roles.c.tenant_id == tenant_id
                )
            )
            connection.execute(
                delete(Membership).where(
                    Membership.tenant_id.in_([tenant_id, other_tenant_id])
                )
            )
            connection.execute(
                delete(Site).where(Site.tenant_id.in_([tenant_id, other_tenant_id]))
            )
            connection.execute(
                delete(Tenant).where(
                    Tenant.id.in_([tenant_id, other_tenant_id])
                )
            )
            connection.execute(delete(Specialty).where(Specialty.id == specialty_id))
            connection.execute(delete(User).where(User.id.in_(user_ids)))
        migration_engine.dispose()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _client(subject: str, email: str, display_name: str) -> TestClient:
    claims = {
        "sub": subject,
        "email": email,
        "name": display_name,
        "amr": ["pwd", "otp"],
    }
    app.dependency_overrides[get_verified_claims] = lambda: claims
    return TestClient(app)


def test_tenant_admin_can_filter_page_and_assign_site_roles(
    management_fixture: ManagementFixture,
) -> None:
    fixture = management_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.admin_subject,
        "manager@example.invalid",
        "Synthetic Manager",
    ) as client:
        listed = client.get(
            f"{base}/users",
            params={"site_id": str(fixture.site_id), "role_code": "doctor"},
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["role_codes"] == ["doctor"]

        page = client.get(
            f"{base}/users",
            params={
                "site_id": str(fixture.site_id),
                "limit": 1,
                "offset": 1,
            },
        )
        assert page.status_code == 200
        assert page.json()["total"] == 2
        assert len(page.json()["items"]) == 1
        assert page.json()["offset"] == 1

        filtered = client.get(
            f"{base}/users",
            params={
                "site_id": str(fixture.site_id),
                "q": "Synthetic Physician",
            },
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["email"] == "physician@example.invalid"

        updated = client.put(
            f"{base}/users/{fixture.doctor_membership_id}/sites/"
            f"{fixture.site_id}/roles",
            json={"role_codes": ["receptionist"]},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["role_codes"] == ["receptionist"]

        suspended = client.patch(
            f"{base}/users/{fixture.doctor_membership_id}/status",
            json={"status": "suspended"},
        )
        assert suspended.status_code == 200
        assert suspended.json()["membership_status"] == "suspended"
        suspended_page = client.get(
            f"{base}/users",
            params={"site_id": str(fixture.site_id), "status": "suspended"},
        )
        assert suspended_page.status_code == 200
        assert suspended_page.json()["total"] == 1
        assert client.patch(
            f"{base}/users/{fixture.doctor_membership_id}/status",
            json={"status": "active"},
        ).json()["membership_status"] == "active"

        forbidden_role = client.put(
            f"{base}/users/{fixture.doctor_membership_id}/sites/"
            f"{fixture.site_id}/roles",
            json={"role_codes": ["administrator"]},
        )
        assert forbidden_role.status_code == 422

        assert client.get(
            f"/api/v1/admin/tenants/{fixture.other_tenant_id}/users",
            params={"site_id": str(fixture.site_id)},
        ).status_code == 403


def test_non_administrator_cannot_manage_users(
    management_fixture: ManagementFixture,
) -> None:
    fixture = management_fixture
    with _client(
        fixture.doctor_subject,
        "physician@example.invalid",
        "Synthetic Physician",
    ) as client:
        response = client.get(
            f"/api/v1/admin/tenants/{fixture.tenant_id}/users",
            params={"site_id": str(fixture.site_id)},
        )
    assert response.status_code == 403


def test_site_context_loads_site_scoped_permissions(
    management_fixture: ManagementFixture,
) -> None:
    fixture = management_fixture
    with _client(
        fixture.doctor_subject,
        "physician@example.invalid",
        "Synthetic Physician",
    ) as client:
        response = client.get(
            "/api/v1/auth/me",
            headers={
                "X-Tenant-ID": str(fixture.tenant_id),
                "X-Site-ID": str(fixture.site_id),
            },
        )
    assert response.status_code == 200, response.text
    assert "doctor" in response.json()["roles"]
    assert "clinical:write" in response.json()["permissions"]


def test_site_role_assignments_are_hidden_by_tenant_rls(
    management_fixture: ManagementFixture,
) -> None:
    fixture = management_fixture
    with tenant_session(fixture.tenant_id) as session:
        visible_memberships = session.scalars(
            select(membership_site_roles.c.membership_id)
        ).all()
        cross_tenant_delete = session.execute(
            membership_site_roles.delete().where(
                membership_site_roles.c.tenant_id == fixture.other_tenant_id,
                membership_site_roles.c.membership_id == fixture.other_membership_id,
            )
        )
    assert visible_memberships == [fixture.doctor_membership_id]
    assert cross_tenant_delete.rowcount == 0


def test_keycloak_invitation_creates_identity_without_password(
    management_fixture: ManagementFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.administration import users_router

    fixture = management_fixture
    subject = uuid4()
    mfa_requirements: list[bool] = []
    monkeypatch.setattr(
        users_router,
        "create_identity",
        lambda *_args, **kwargs: (
            mfa_requirements.append(kwargs["require_mfa"]) or subject
        ),
    )
    deleted: list[UUID] = []
    monkeypatch.setattr(users_router, "delete_identity", deleted.append)

    with _client(
        fixture.admin_subject,
        "manager@example.invalid",
        "Synthetic Manager",
    ) as client:
        response = client.post(
            f"/api/v1/admin/tenants/{fixture.tenant_id}/users",
            json={
                "email": "new.person@example.invalid",
                "display_name": "Synthetic Invitee",
                "site_id": str(fixture.site_id),
                "role_codes": ["doctor"],
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["identity_provider_subject"] == str(subject)
    assert response.json()["role_codes"] == ["doctor"]
    assert mfa_requirements == [True]
    assert not deleted

    migration_url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    test_engine = create_engine(migration_url)
    try:
        with test_engine.connect() as connection:
            email = connection.scalar(
                select(User.email).where(
                    User.identity_provider_subject == str(subject)
                )
            )
            assert email == "new.person@example.invalid"
            assert not any(
                "password" in column.name.lower()
                for column in User.__table__.columns
            )
    finally:
        with test_engine.begin() as connection:
            invited_user_ids = select(User.id).where(
                User.identity_provider_subject == str(subject)
            )
            connection.execute(
                delete(Membership).where(Membership.user_id.in_(invited_user_ids))
            )
            connection.execute(
                delete(User).where(User.identity_provider_subject == str(subject))
            )
        test_engine.dispose()


def test_doctor_pagination_and_availability_overlap_are_enforced(
    management_fixture: ManagementFixture,
) -> None:
    fixture = management_fixture
    base = f"/api/v1/admin/tenants/{fixture.tenant_id}"
    with _client(
        fixture.admin_subject,
        "manager@example.invalid",
        "Synthetic Manager",
    ) as client:
        doctors = client.get(
            f"{base}/doctors",
            params={"specialty_id": str(fixture.specialty_id), "limit": 1},
        )
        assert doctors.status_code == 200, doctors.text
        assert doctors.json()["total"] == 1
        doctor = doctors.json()["items"][0]
        assert doctor["id"] == str(fixture.doctor_id)
        next_page = client.get(
            f"{base}/doctors",
            params={"specialty_id": str(fixture.specialty_id), "limit": 1, "offset": 1},
        )
        assert next_page.status_code == 200
        assert next_page.json()["total"] == 1
        assert next_page.json()["items"] == []

        created = client.post(
            f"{base}/doctors/{fixture.doctor_id}/availability",
            json={
                "site_id": str(fixture.site_id),
                "weekday": 0,
                "starts_at": "08:00",
                "ends_at": "12:00",
            },
        )
        assert created.status_code == 201, created.text
        availability_id = created.json()["id"]
        overlap = client.post(
            f"{base}/doctors/{fixture.doctor_id}/availability",
            json={
                "site_id": str(fixture.site_id),
                "weekday": 0,
                "starts_at": "11:00",
                "ends_at": "13:00",
            },
        )
        assert overlap.status_code == 409
        assert client.delete(
            f"{base}/doctors/{fixture.doctor_id}/availability/{availability_id}"
        ).status_code == 204
