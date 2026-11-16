from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings, get_settings


class OIDCProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sub: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=320)
    name: str | None = Field(default=None, max_length=200)
    preferred_username: str | None = Field(default=None, max_length=200)


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=5)


def verify_access_token(
    encoded_token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    config = settings or get_settings()

    try:
        signing_key = _jwks_client(config.oidc_jwks_url).get_signing_key_from_jwt(
            encoded_token
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider keys are unavailable",
        ) from exc
    except jwt.PyJWKClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        claims = jwt.decode(
            encoded_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.oidc_audience,
            issuer=config.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        profile = OIDCProfile.model_validate(claims)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is missing required identity claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    normalized_claims = dict(claims)
    normalized_claims["sub"] = profile.sub
    normalized_claims["email"] = profile.email
    normalized_claims["name"] = (
        profile.name or profile.preferred_username or profile.email
    )
    return normalized_claims
