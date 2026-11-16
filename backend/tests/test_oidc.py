from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domains.identity import oidc
from app.main import app


@pytest.fixture
def oidc_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://user:pass@localhost/db",
        migration_database_url="postgresql+psycopg://user:pass@localhost/db",
        tenant_context_secret="test-tenant-context-secret-long-enough",
        oidc_issuer="https://identity.example.invalid/realms/medigest",
        oidc_audience="medigest-api",
        oidc_jwks_url="https://identity.example.invalid/keys",
    )


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(oidc, "_jwks_client", lambda _url: FakeJwksClient())
    return private_key


def _token(signing_key, **overrides: object) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "iss": "https://identity.example.invalid/realms/medigest",
        "aud": "medigest-api",
        "sub": "synthetic-subject",
        "email": "synthetic@example.invalid",
        "name": "Synthetic User",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test"})


def test_valid_access_token_is_verified_and_profile_normalized(
    oidc_settings: Settings,
    signing_key,
) -> None:
    claims = oidc.verify_access_token(_token(signing_key), oidc_settings)

    assert claims["sub"] == "synthetic-subject"
    assert claims["email"] == "synthetic@example.invalid"
    assert claims["name"] == "Synthetic User"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example.invalid/realms/medigest"},
        {"aud": "another-api"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_invalid_issuer_audience_or_expiry_is_rejected(
    oidc_settings: Settings,
    signing_key,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(HTTPException) as error:
        oidc.verify_access_token(_token(signing_key, **overrides), oidc_settings)
    assert error.value.status_code == 401


def test_missing_identity_claims_are_rejected(
    oidc_settings: Settings,
    signing_key,
) -> None:
    with pytest.raises(HTTPException) as error:
        oidc.verify_access_token(
            _token(signing_key, email=None),
            oidc_settings,
        )
    assert error.value.status_code == 401


def test_identity_endpoint_requires_bearer_token() -> None:
        response = TestClient(app).get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
