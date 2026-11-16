from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Membership, Permission, Role, Site, User
from app.db.session import engine, tenant_session
from app.domains.identity.models import (
    membership_roles,
    membership_site_roles,
    role_permissions,
)

PRIVILEGED_ROLE_CODES = frozenset({"superadmin", "administrator", "doctor"})
MFA_METHODS = frozenset({"otp", "totp", "mfa", "hwk", "webauthn"})
MFA_ACR_VALUES = frozenset({"2", "urn:medigest:loa:2"})


@dataclass(frozen=True)
class AuthorizationContext:
    user_id: UUID
    subject: str
    email: str
    display_name: str
    tenant_id: UUID | None
    site_id: UUID | None
    role_codes: frozenset[str]
    permission_codes: frozenset[str]


def token_has_mfa(claims: dict[str, Any]) -> bool:
    methods = claims.get("amr", [])
    if isinstance(methods, str):
        methods = [methods]
    if not isinstance(methods, (list, tuple, set)):
        methods = []
    acr = claims.get("acr")
    valid_methods = {method for method in methods if isinstance(method, str)}
    return bool(MFA_METHODS.intersection(valid_methods)) or acr in MFA_ACR_VALUES


def provision_oidc_user(claims: dict[str, Any]) -> User:
    subject = claims["sub"]
    values = {
        "identity_provider_subject": subject,
        "email": claims["email"],
        "display_name": claims["name"],
        "is_active": True,
    }

    with Session(engine) as session, session.begin():
        session.execute(
            insert(User)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_users_identity_provider_subject",
                set_={
                    "email": values["email"],
                    "display_name": values["display_name"],
                },
            )
        )
        user = session.scalar(
            select(User).where(User.identity_provider_subject == subject)
        )
        if user is None:
            raise RuntimeError("OIDC user synchronization did not return a user")
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        session.expunge(user)
        return user


def _role_access(
    session: Session,
    role_ids: list[UUID],
) -> tuple[frozenset[str], frozenset[str]]:
    if not role_ids:
        return frozenset(), frozenset()

    roles = frozenset(
        session.scalars(select(Role.code).where(Role.id.in_(role_ids))).all()
    )
    permissions = frozenset(
        session.scalars(
            select(Permission.code)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .where(role_permissions.c.role_id.in_(role_ids))
        ).all()
    )
    return roles, permissions


def _platform_access(
    session: Session,
    user: User,
) -> tuple[frozenset[str], frozenset[str]]:
    if user.platform_role_id is None:
        return frozenset(), frozenset()
    return _role_access(session, [user.platform_role_id])


def _tenant_access(
    tenant_id: UUID,
    user_id: UUID,
    site_id: UUID | None = None,
) -> tuple[frozenset[str], frozenset[str]] | None:
    with tenant_session(tenant_id) as session:
        membership = session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        )
        if membership is None:
            return None

        role_ids = set(
            session.scalars(
                select(membership_roles.c.role_id).where(
                    membership_roles.c.tenant_id == tenant_id,
                    membership_roles.c.membership_id == membership.id,
                )
            ).all()
        )
        if site_id is not None:
            site = session.scalar(
                select(Site).where(
                    Site.tenant_id == tenant_id,
                    Site.id == site_id,
                    Site.is_active.is_(True),
                )
            )
            if site is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Site not found",
                )
            role_ids.update(
                session.scalars(
                    select(membership_site_roles.c.role_id).where(
                        membership_site_roles.c.tenant_id == tenant_id,
                        membership_site_roles.c.site_id == site_id,
                        membership_site_roles.c.membership_id == membership.id,
                    )
                ).all()
            )
        return _role_access(session, list(role_ids))


def load_authorization_context(
    claims: dict[str, Any],
    tenant_id: UUID | None,
    site_id: UUID | None = None,
) -> AuthorizationContext:
    if site_id is not None and tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A tenant is required when a site is provided",
        )
    user = provision_oidc_user(claims)
    with Session(engine) as session:
        platform_roles, platform_permissions = _platform_access(session, user)

    tenant_roles: frozenset[str] = frozenset()
    tenant_permissions: frozenset[str] = frozenset()
    if tenant_id is not None:
        tenant_access = _tenant_access(tenant_id, user.id, site_id)
        if tenant_access is None and not platform_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no active membership in this tenant",
            )
        if tenant_access is not None:
            tenant_roles, tenant_permissions = tenant_access

    role_codes = platform_roles | tenant_roles
    if role_codes.intersection(PRIVILEGED_ROLE_CODES) and not token_has_mfa(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Multi-factor authentication is required for this role",
        )

    return AuthorizationContext(
        user_id=user.id,
        subject=user.identity_provider_subject,
        email=user.email,
        display_name=user.display_name,
        tenant_id=tenant_id,
        site_id=site_id,
        role_codes=role_codes,
        permission_codes=platform_permissions | tenant_permissions,
    )


def require_permission(permission_code: str):
    def authorize(context: AuthorizationContext) -> AuthorizationContext:
        if permission_code not in context.permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context

    return authorize
