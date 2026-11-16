from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://medigest_app:medigest_app_dev_only@localhost:5432/medigest"
    )
    migration_database_url: str = (
        "postgresql+psycopg://medigest:medigest_dev_only@localhost:5432/medigest"
    )
    tenant_context_secret: str = Field(
        default="medigest-local-only-tenant-context-secret-change-me",
        min_length=32,
    )
    oidc_issuer: str = "http://localhost:8080/realms/medigest"
    oidc_audience: str = "medigest-api"
    oidc_jwks_url: str = (
        "http://keycloak:8080/realms/medigest/protocol/"
        "openid-connect/certs"
    )
    keycloak_admin_base_url: str = "http://keycloak:8080"
    keycloak_admin_realm: str = "medigest"
    keycloak_admin_client_id: str = "medigest-admin-api"
    keycloak_admin_client_secret: str = "medigest-local-only-admin-client-secret"
    patient_data_encryption_key: str = (
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    )
    patient_identifier_hmac_secret: str = (
        "medigest-local-only-patient-identifier-hmac-secret"
    )
    administrative_document_encryption_key: str = (
        "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="
    )
    app_env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def require_production_tenant_secret(self) -> "Settings":
        if (
            self.app_env == "production"
            and self.tenant_context_secret
            == "medigest-local-only-tenant-context-secret-change-me"
        ):
            raise ValueError("TENANT_CONTEXT_SECRET must be set outside development")
        if self.app_env == "production" and (
            not self.oidc_issuer.startswith("https://")
            or not self.oidc_jwks_url.startswith("https://")
        ):
            raise ValueError("Production OIDC issuer and JWKS URL must use HTTPS")
        if self.app_env == "production" and (
            self.keycloak_admin_client_secret
            == "medigest-local-only-admin-client-secret"
            or not self.keycloak_admin_base_url.startswith("https://")
        ):
            raise ValueError(
                "Production Keycloak administration requires a unique secret and HTTPS"
            )
        if self.app_env == "production" and (
            self.patient_data_encryption_key
            == "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
            or self.patient_identifier_hmac_secret
            == "medigest-local-only-patient-identifier-hmac-secret"
            or self.administrative_document_encryption_key
            == "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="
            or self.administrative_document_encryption_key
            == self.patient_data_encryption_key
        ):
            raise ValueError(
                "Production patient and document encryption secrets must be set"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
