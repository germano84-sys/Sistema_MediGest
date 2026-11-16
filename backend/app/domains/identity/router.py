from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domains.identity.authorization import load_authorization_context
from app.domains.identity.oidc import verify_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


def get_verified_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_access_token(credentials.credentials)


@router.get("/me")
def get_current_identity(
    claims: dict[str, Any] = Depends(get_verified_claims),
    tenant_id: UUID | None = Header(default=None, alias="X-Tenant-ID"),
    site_id: UUID | None = Header(default=None, alias="X-Site-ID"),
) -> dict[str, Any]:
    context = load_authorization_context(claims, tenant_id, site_id)
    return {
        "id": str(context.user_id),
        "subject": context.subject,
        "email": context.email,
        "display_name": context.display_name,
        "tenant_id": str(context.tenant_id) if context.tenant_id else None,
        "site_id": str(site_id) if site_id else None,
        "roles": sorted(context.role_codes),
        "permissions": sorted(context.permission_codes),
    }
