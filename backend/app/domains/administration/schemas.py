import json
import re
from datetime import time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
SETTING_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
SENSITIVE_SETTING_PARTS = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "private_key",
)


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )


class TenantCreate(APIModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=80)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not SLUG_PATTERN.fullmatch(value):
            raise ValueError("El identificador debe usar minúsculas, números y guiones")
        return value


class TenantUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    status: str | None = None

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str | None) -> str | None:
        if value is not None and not SLUG_PATTERN.fullmatch(value):
            raise ValueError("El identificador debe usar minúsculas, números y guiones")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"active", "suspended"}:
            raise ValueError("El estado debe ser active o suspended")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class TenantOut(APIModel):
    id: UUID
    name: str
    slug: str
    status: str


class SiteCreate(APIModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_PATTERN.fullmatch(value):
            raise ValueError("El código solo admite letras, números, guion y guion bajo")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Zona horaria IANA desconocida") from exc
        return value


class SiteUpdate(APIModel):
    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if not CODE_PATTERN.fullmatch(value):
            raise ValueError("El código solo admite letras, números, guion y guion bajo")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Zona horaria IANA desconocida") from exc
        return value

    @model_validator(mode="after")
    def reject_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class SiteOut(APIModel):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    timezone: str
    is_active: bool


class SpecialtyCreate(APIModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_PATTERN.fullmatch(value):
            raise ValueError("El código solo admite letras, números, guion y guion bajo")
        return value


class SpecialtyUpdate(APIModel):
    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if not CODE_PATTERN.fullmatch(value):
            raise ValueError("El código solo admite letras, números, guion y guion bajo")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class SpecialtyOut(APIModel):
    id: UUID
    code: str
    name: str
    is_active: bool


class TenantSpecialtyCreate(APIModel):
    specialty_id: UUID
    is_active: bool = True


class TenantSpecialtyUpdate(APIModel):
    is_active: bool


class TenantSpecialtyOut(APIModel):
    id: UUID
    tenant_id: UUID
    specialty_id: UUID
    code: str
    name: str
    is_active: bool


class RoomCreate(APIModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    room_type: str = Field(default="consultation", min_length=2, max_length=40)
    is_active: bool = True

    @field_validator("code", "room_type")
    @classmethod
    def valid_code(cls, value: str) -> str:
        value = value.upper() if value == value.upper() else value.lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value, re.IGNORECASE):
            raise ValueError("Use letras, números, guiones o guiones bajos")
        return value


class RoomUpdate(APIModel):
    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    room_type: str | None = Field(default=None, min_length=2, max_length=40)
    is_active: bool | None = None

    @field_validator("code", "room_type")
    @classmethod
    def valid_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value, re.IGNORECASE):
            raise ValueError("Use letras, números, guiones o guiones bajos")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class RoomOut(APIModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    code: str
    name: str
    room_type: str
    is_active: bool


class SiteHoursCreate(APIModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: time | None = None
    closes_at: time | None = None
    is_closed: bool = False

    @model_validator(mode="after")
    def validate_interval(self):
        if self.is_closed:
            if self.opens_at is not None or self.closes_at is not None:
                raise ValueError("Un día cerrado no puede definir horas")
        elif (
            self.opens_at is None
            or self.closes_at is None
            or self.closes_at <= self.opens_at
        ):
            raise ValueError("La hora de cierre debe ser posterior a la apertura")
        return self


class SiteHoursUpdate(APIModel):
    opens_at: time | None = None
    closes_at: time | None = None
    is_closed: bool | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if "is_closed" in self.model_fields_set and self.is_closed is None:
            raise ValueError("is_closed no puede ser nulo")
        if (
            "opens_at" in self.model_fields_set
            and self.opens_at is None
            and self.is_closed is not True
        ):
            raise ValueError("opens_at no puede ser nulo")
        if (
            "closes_at" in self.model_fields_set
            and self.closes_at is None
            and self.is_closed is not True
        ):
            raise ValueError("closes_at no puede ser nulo")
        if self.is_closed is True and (
            self.opens_at is not None or self.closes_at is not None
        ):
            raise ValueError("Un día cerrado no puede definir horas")
        return self


class SiteHoursOut(APIModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    weekday: int
    opens_at: time | None
    closes_at: time | None
    is_closed: bool


class TenantSettingCreate(APIModel):
    key: str = Field(min_length=1, max_length=100)
    value: dict[str, Any]

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not SETTING_KEY_PATTERN.fullmatch(value):
            raise ValueError("La clave debe usar minúsculas, números, punto o guion")
        if any(part in value for part in SENSITIVE_SETTING_PARTS):
            raise ValueError("No almacenes secretos o credenciales institucionales aquí")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 8192:
            raise ValueError("El parámetro no puede superar 8 KiB")

        def validate_keys(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    normalized = key.casefold()
                    if any(part in normalized for part in SENSITIVE_SETTING_PARTS):
                        raise ValueError(
                            "No almacenes secretos o credenciales institucionales aquí"
                        )
                    validate_keys(child)
            elif isinstance(node, list):
                for child in node:
                    validate_keys(child)

        validate_keys(value)
        return value


class TenantSettingUpdate(APIModel):
    value: dict[str, Any]

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: dict[str, Any]) -> dict[str, Any]:
        return TenantSettingCreate(key="institution.setting", value=value).value


class TenantSettingOut(APIModel):
    id: UUID
    tenant_id: UUID
    key: str
    value: dict[str, Any]


class UserInvite(APIModel):
    email: str = Field(min_length=5, max_length=320)
    display_name: str = Field(min_length=2, max_length=200)
    site_id: UUID
    role_codes: list[str] = Field(min_length=1, max_length=3)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Ingresa un correo electrónico válido")
        return normalized

    @field_validator("role_codes")
    @classmethod
    def distinct_roles(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("No repitas roles")
        return value


class SiteRoleUpdate(APIModel):
    role_codes: list[str] = Field(max_length=3)

    @field_validator("role_codes")
    @classmethod
    def distinct_roles(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("No repitas roles")
        return value


class MembershipStatusUpdate(APIModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"active", "suspended"}:
            raise ValueError("El estado debe ser active o suspended")
        return value


class ManagedRoleOut(APIModel):
    code: str
    name: str


class ManagedUserOut(APIModel):
    membership_id: UUID
    user_id: UUID
    identity_provider_subject: str
    email: str
    display_name: str
    is_active: bool
    membership_status: str
    role_codes: list[str]


class ManagedUserPage(APIModel):
    items: list[ManagedUserOut]
    total: int
    limit: int
    offset: int


class DoctorInvite(APIModel):
    membership_id: UUID
    site_id: UUID
    license_number: str = Field(min_length=3, max_length=80)
    specialty_ids: list[UUID] = Field(min_length=1, max_length=20)

    @field_validator("specialty_ids")
    @classmethod
    def distinct_specialties(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("No repitas especialidades")
        return value


class DoctorUpdate(APIModel):
    license_number: str | None = Field(default=None, min_length=3, max_length=80)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class DoctorSpecialtiesUpdate(APIModel):
    specialty_ids: list[UUID] = Field(min_length=1, max_length=20)
    primary_specialty_id: UUID

    @model_validator(mode="after")
    def validate_primary_and_distinct(self):
        if len(set(self.specialty_ids)) != len(self.specialty_ids):
            raise ValueError("No repitas especialidades")
        if self.primary_specialty_id not in self.specialty_ids:
            raise ValueError("La especialidad principal debe estar en la lista")
        return self


class DoctorOut(APIModel):
    id: UUID
    tenant_id: UUID
    membership_id: UUID
    email: str
    display_name: str
    license_number: str
    is_active: bool
    specialty_ids: list[UUID]
    primary_specialty_id: UUID


class DoctorPage(APIModel):
    items: list[DoctorOut]
    total: int
    limit: int
    offset: int


class DoctorAvailabilityCreate(APIModel):
    site_id: UUID
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    is_available: bool = True

    @model_validator(mode="after")
    def validate_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("La hora de fin debe ser posterior al inicio")
        return self


class DoctorAvailabilityUpdate(APIModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    starts_at: time | None = None
    ends_at: time | None = None
    is_available: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class DoctorAvailabilityOut(APIModel):
    id: UUID
    tenant_id: UUID
    doctor_id: UUID
    site_id: UUID
    weekday: int
    starts_at: time
    ends_at: time
    is_available: bool
