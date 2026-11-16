import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select

from app.db.models import (
    AuditEvent,
    ClinicRoom,
    Membership,
    Role,
    Site,
    SiteHours,
    Specialty,
    Tenant,
    TenantSetting,
    TenantSpecialty,
    User,
)
from app.domains.identity.models import membership_roles
from app.domains.identity.router import get_verified_claims
from app.main import app


@dataclass(frozen=True)
class AdministrationFixture:
    tenant_a: UUID
    tenant_b: UUID
    admin_subject: str
    other_admin_subject: str
    platform_subject: str
    specialty_code_prefix: str
    platform_tenant_slug: str


@pytest.fixture
def administration_fixture() -> AdministrationFixture:
    migration_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if not migration_url:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL for administration API tests")

    fixture = AdministrationFixture(
        tenant_a=uuid4(),
        tenant_b=uuid4(),
        admin_subject=f"admin-{uuid4().hex}",
        other_admin_subject=f"admin-{uuid4().hex}",
        platform_subject=f"platform-{uuid4().hex}",
        specialty_code_prefix=f"TEST{uuid4().hex[:8].upper()}",
        platform_tenant_slug=f"platform-test-{uuid4().hex[:10]}",
    )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    tenant_admin_role_id = None
    platform_role_id = None
    with migration_engine.begin() as connection:
        tenant_admin_role_id = connection.scalar(
            select(Role.id).where(Role.code == "administrator")
        )
        platform_role_id = connection.scalar(
            select(Role.id).where(Role.code == "superadmin")
        )
        assert tenant_admin_role_id is not None
        assert platform_role_id is not None

        for tenant_id, suffix in (
            (fixture.tenant_a, "a"),
            (fixture.tenant_b, "b"),
        ):
            connection.execute(
                Tenant.__table__.insert().values(
                    id=tenant_id,
                    name=f"Synthetic admin tenant {suffix}",
                    slug=f"admin-test-{suffix}-{tenant_id.hex[:10]}",
                )
            )

        user_data = (
            (fixture.admin_subject, "admin-a@example.invalid", "Admin A", None),
            (
                fixture.other_admin_subject,
                "admin-b@example.invalid",
                "Admin B",
                None,
            ),
            (
                fixture.platform_subject,
                "platform@example.invalid",
                "Platform User",
                platform_role_id,
            ),
        )
        users: dict[str, UUID] = {}
        for subject, email, display_name, global_role_id in user_data:
            user_id = uuid4()
            users[subject] = user_id
            connection.execute(
                User.__table__.insert().values(
                    id=user_id,
                    identity_provider_subject=subject,
                    email=email,
                    display_name=display_name,
                    is_active=True,
                    platform_role_id=global_role_id,
                )
            )

        for tenant_id, subject in (
            (fixture.tenant_a, fixture.admin_subject),
            (fixture.tenant_b, fixture.other_admin_subject),
        ):
            membership_id = uuid4()
            connection.execute(
                Membership.__table__.insert().values(
                    id=membership_id,
                    tenant_id=tenant_id,
                    user_id=users[subject],
                    status="active",
                )
            )
            connection.execute(
                membership_roles.insert().values(
                    tenant_id=tenant_id,
                    membership_id=membership_id,
                    role_id=tenant_admin_role_id,
                )
            )

    try:
        yield fixture
    finally:
        with migration_engine.begin() as connection:
            tenant_ids = [fixture.tenant_a, fixture.tenant_b]
            created_platform_tenant = connection.scalar(
                select(Tenant.id).where(Tenant.slug == fixture.platform_tenant_slug)
            )
            if created_platform_tenant is not None:
                tenant_ids.append(created_platform_tenant)
            connection.execute(
                delete(AuditEvent).where(
                    AuditEvent.tenant_id.in_(tenant_ids)
                    | AuditEvent.actor_user_id.in_(
                        select(User.id).where(
                            User.identity_provider_subject.in_(
                                [
                                    fixture.admin_subject,
                                    fixture.other_admin_subject,
                                    fixture.platform_subject,
                                ]
                            )
                        )
                    )
                )
            )
            connection.execute(
                delete(TenantSpecialty).where(
                    TenantSpecialty.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(TenantSetting).where(TenantSetting.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(SiteHours).where(SiteHours.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(ClinicRoom).where(ClinicRoom.tenant_id.in_(tenant_ids))
            )
            connection.execute(delete(Site).where(Site.tenant_id.in_(tenant_ids)))
            connection.execute(
                membership_roles.delete().where(
                    membership_roles.c.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(Membership).where(Membership.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(Tenant).where(Tenant.id.in_(tenant_ids))
            )
            connection.execute(
                delete(Specialty).where(
                    Specialty.code.like(f"{fixture.specialty_code_prefix}%")
                )
            )
            connection.execute(
                delete(User).where(
                    User.identity_provider_subject.in_(
                        [
                            fixture.admin_subject,
                            fixture.other_admin_subject,
                            fixture.platform_subject,
                        ]
                    )
                )
            )
        migration_engine.dispose()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _client(subject: str, email: str, name: str) -> TestClient:
    claims = {
        "sub": subject,
        "email": email,
        "name": name,
        "amr": ["pwd", "otp"],
    }
    app.dependency_overrides[get_verified_claims] = lambda: claims
    return TestClient(app)


def test_tenant_admin_can_manage_scoped_clinic_resources(
    administration_fixture: AdministrationFixture,
) -> None:
    fixture = administration_fixture
    with _client(
        fixture.admin_subject,
        "admin-a@example.invalid",
        "Admin A",
    ) as client:
        base = f"/api/v1/admin/tenants/{fixture.tenant_a}"
        sites_response = client.post(
            f"{base}/sites",
            json={
                "code": "north",
                "name": "North clinic",
                "timezone": "America/Guayaquil",
            },
        )
        assert sites_response.status_code == 201, sites_response.text
        site = sites_response.json()
        assert site["code"] == "NORTH"
        site_id = site["id"]

        listed_sites = client.get(f"{base}/sites")
        assert listed_sites.status_code == 200
        assert [row["id"] for row in listed_sites.json()] == [site_id]

        room_response = client.post(
            f"{base}/sites/{site_id}/rooms",
            json={"code": "R-01", "name": "Consultation room"},
        )
        assert room_response.status_code == 201, room_response.text
        room_id = room_response.json()["id"]
        updated_room = client.patch(
            f"{base}/sites/{site_id}/rooms/{room_id}",
            json={"name": "Consultation room 1", "is_active": False},
        )
        assert updated_room.status_code == 200
        assert updated_room.json()["is_active"] is False
        assert client.delete(
            f"{base}/sites/{site_id}/rooms/{room_id}"
        ).status_code == 204

        hours_response = client.post(
            f"{base}/sites/{site_id}/hours",
            json={
                "weekday": 0,
                "opens_at": "08:00",
                "closes_at": "17:00",
            },
        )
        assert hours_response.status_code == 201, hours_response.text
        hours_id = hours_response.json()["id"]
        closed_response = client.patch(
            f"{base}/sites/{site_id}/hours/{hours_id}",
            json={"is_closed": True, "opens_at": None, "closes_at": None},
        )
        assert closed_response.status_code == 200, closed_response.text
        assert closed_response.json()["is_closed"] is True
        assert closed_response.json()["opens_at"] is None
        assert client.delete(
            f"{base}/sites/{site_id}/hours/{hours_id}"
        ).status_code == 204

        setting_response = client.post(
            f"{base}/settings",
            json={"key": "locale.timezone", "value": {"name": "es-EC"}},
        )
        assert setting_response.status_code == 201, setting_response.text
        assert setting_response.json()["value"] == {"name": "es-EC"}
        setting_update = client.patch(
            f"{base}/settings/locale.timezone",
            json={"value": {"name": "es"}},
        )
        assert setting_update.status_code == 200
        assert setting_update.json()["value"] == {"name": "es"}
        assert client.delete(f"{base}/settings/locale.timezone").status_code == 204

        assert client.delete(f"{base}/sites/{site_id}").status_code == 204

    app.dependency_overrides.clear()


def test_platform_admin_and_tenant_admin_have_distinct_scopes(
    administration_fixture: AdministrationFixture,
) -> None:
    fixture = administration_fixture
    with _client(
        fixture.admin_subject,
        "admin-a@example.invalid",
        "Admin A",
    ) as tenant_admin:
        assert tenant_admin.get("/api/v1/admin/tenants").status_code == 403
        assert tenant_admin.post(
            "/api/v1/admin/specialties",
            json={"code": f"{fixture.specialty_code_prefix}X", "name": "Test specialty"},
        ).status_code == 403
        assert tenant_admin.get(
            f"/api/v1/admin/tenants/{fixture.tenant_b}/sites"
        ).status_code == 403

    with _client(
        fixture.platform_subject,
        "platform@example.invalid",
        "Platform User",
    ) as platform_admin:
        tenants = platform_admin.get("/api/v1/admin/tenants")
        assert tenants.status_code == 200, tenants.text
        assert {fixture.tenant_a.hex, fixture.tenant_b.hex} <= {
            row["id"].replace("-", "") for row in tenants.json()
        }

        created_tenant = platform_admin.post(
            "/api/v1/admin/tenants",
            json={
                "name": "Platform-created clinic",
                "slug": fixture.platform_tenant_slug,
            },
        )
        assert created_tenant.status_code == 201, created_tenant.text
        created_id = created_tenant.json()["id"]
        updated_tenant = platform_admin.patch(
            f"/api/v1/admin/tenants/{created_id}",
            json={"status": "suspended"},
        )
        assert updated_tenant.status_code == 200
        assert updated_tenant.json()["status"] == "suspended"
        delete_response = platform_admin.delete(
            f"/api/v1/admin/tenants/{created_id}"
        )
        assert delete_response.status_code == 409
        assert "suspend" in delete_response.json()["detail"]

        specialty = platform_admin.post(
            "/api/v1/admin/specialties",
            json={
                "code": f"{fixture.specialty_code_prefix}X",
                "name": "Synthetic specialty",
            },
        )
        assert specialty.status_code == 201, specialty.text
        specialty_id = specialty.json()["id"]

        tenant_base = f"/api/v1/admin/tenants/{fixture.tenant_a}"
        link = platform_admin.post(
            f"{tenant_base}/specialties",
            json={"specialty_id": specialty_id},
        )
        assert link.status_code == 201, link.text
        link_id = link.json()["id"]
        assert platform_admin.patch(
            f"{tenant_base}/specialties/{link_id}",
            json={"is_active": False},
        ).json()["is_active"] is False
        assert platform_admin.delete(
            f"{tenant_base}/specialties/{link_id}"
        ).status_code == 204

        specialty_update = platform_admin.patch(
            f"/api/v1/admin/specialties/{specialty_id}",
            json={"name": "Updated synthetic specialty"},
        )
        assert specialty_update.status_code == 200
        assert specialty_update.json()["name"] == "Updated synthetic specialty"
        assert platform_admin.delete(
            f"/api/v1/admin/specialties/{specialty_id}"
        ).status_code == 204

    app.dependency_overrides.clear()


def test_tenant_admin_cannot_read_or_write_another_tenant_resources(
    administration_fixture: AdministrationFixture,
) -> None:
    fixture = administration_fixture
    with _client(
        fixture.other_admin_subject,
        "admin-b@example.invalid",
        "Admin B",
    ) as other_admin:
        site_response = other_admin.post(
            f"/api/v1/admin/tenants/{fixture.tenant_b}/sites",
            json={"code": "B-01", "name": "Tenant B site"},
        )
        assert site_response.status_code == 201, site_response.text
        site_id = site_response.json()["id"]

    with _client(
        fixture.admin_subject,
        "admin-a@example.invalid",
        "Admin A",
    ) as tenant_admin:
        cross_tenant_list = tenant_admin.get(
            f"/api/v1/admin/tenants/{fixture.tenant_b}/sites"
        )
        assert cross_tenant_list.status_code == 403
        cross_tenant_update = tenant_admin.patch(
            f"/api/v1/admin/tenants/{fixture.tenant_b}/sites/{site_id}",
            json={"name": "Unauthorized"},
        )
        assert cross_tenant_update.status_code == 403
        cross_tenant_delete = tenant_admin.delete(
            f"/api/v1/admin/tenants/{fixture.tenant_b}/sites/{site_id}"
        )
        assert cross_tenant_delete.status_code == 403

    app.dependency_overrides.clear()


def test_platform_administration_validates_inputs_and_reports_conflicts(
    administration_fixture: AdministrationFixture,
) -> None:
    fixture = administration_fixture
    with _client(
        fixture.admin_subject,
        "admin-a@example.invalid",
        "Admin A",
    ) as tenant_admin:
        tenant_base = f"/api/v1/admin/tenants/{fixture.tenant_a}"
        invalid_site = tenant_admin.post(
            f"{tenant_base}/sites",
            json={"code": "NORTH", "name": "North", "timezone": "Invalid/Zone"},
        )
        assert invalid_site.status_code == 422
        duplicate_site = {
            "code": "SAME",
            "name": "Site",
        }
        assert tenant_admin.post(
            f"{tenant_base}/sites", json=duplicate_site
        ).status_code == 201
        assert tenant_admin.post(
            f"{tenant_base}/sites", json=duplicate_site
        ).status_code == 409
        assert tenant_admin.post(
            f"{tenant_base}/settings",
            json={"key": "integration.api_token", "value": {"enabled": False}},
        ).status_code == 422
        assert tenant_admin.post(
            f"{tenant_base}/sites/00000000-0000-4000-8000-000000000001/hours",
            json={"weekday": 0, "opens_at": "17:00", "closes_at": "08:00"},
        ).status_code == 422

    app.dependency_overrides.clear()
