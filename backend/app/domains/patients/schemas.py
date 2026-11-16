from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class PatientAPIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )


class DocumentRule(PatientAPIModel):
    identifier_type: str = Field(min_length=2, max_length=32)
    min_length: int = Field(ge=1, le=64)
    max_length: int = Field(ge=1, le=64)
    character_set: Literal["digits", "alphanumeric", "uppercase_alphanumeric"]
    checksum_algorithm: Literal["none", "ec_cedula"] = "none"
    is_active: bool = True

    @field_validator("identifier_type")
    @classmethod
    def valid_identifier_type(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", normalized):
            raise ValueError("El tipo de identificación debe ser un código válido")
        return normalized

    @model_validator(mode="after")
    def validate_bounds(self) -> "DocumentRule":
        if self.max_length < self.min_length:
            raise ValueError("La longitud máxima debe ser mayor o igual a la mínima")
        if self.checksum_algorithm == "ec_cedula" and (
            self.character_set != "digits"
            or self.min_length != 10
            or self.max_length != 10
        ):
            raise ValueError(
                "La validación de cédula ecuatoriana requiere exactamente 10 dígitos"
            )
        return self


class PatientDocumentRulesUpdate(PatientAPIModel):
    rules: list[DocumentRule] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_active_rules(self) -> "PatientDocumentRulesUpdate":
        types = [rule.identifier_type for rule in self.rules]
        if len(set(types)) != len(types):
            raise ValueError("No repitas tipos de identificación")
        if not any(rule.is_active for rule in self.rules):
            raise ValueError("Debe existir al menos una regla activa")
        return self


class EmergencyContactInput(PatientAPIModel):
    name: str = Field(min_length=2, max_length=160)
    relationship: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=24)
    email: str | None = Field(default=None, max_length=320)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str) -> str:
        if not re.fullmatch(r"[+0-9() .-]{7,24}", value):
            raise ValueError("Ingresa un teléfono de contacto válido")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Ingresa un correo electrónico válido")
        return value.casefold() if value else None


class PatientCreate(PatientAPIModel):
    identifier_type: str = Field(min_length=2, max_length=32)
    identifier_value: str = Field(min_length=1, max_length=64)
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
    birth_date: date
    phone: str | None = Field(default=None, max_length=24)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=500)
    emergency_contacts: list[EmergencyContactInput] = Field(
        default_factory=list,
        max_length=10,
    )

    @field_validator("identifier_type")
    @classmethod
    def normalize_identifier_type(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", normalized):
            raise ValueError("Tipo de identificación inválido")
        return normalized

    @field_validator("identifier_value")
    @classmethod
    def normalize_identifier_value(cls, value: str) -> str:
        normalized = re.sub(r"[\s-]", "", value).upper()
        if not normalized:
            raise ValueError("La identificación es obligatoria")
        return normalized

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        if value is not None and value and not re.fullmatch(r"[+0-9() .-]{7,24}", value):
            raise ValueError("Ingresa un teléfono de contacto válido")
        return value or None

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Ingresa un correo electrónico válido")
        return value.casefold() if value else None


class PatientUpdate(PatientAPIModel):
    identifier_type: str | None = Field(default=None, min_length=2, max_length=32)
    identifier_value: str | None = Field(default=None, min_length=1, max_length=64)
    given_name: str | None = Field(default=None, min_length=1, max_length=120)
    family_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=24)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=500)
    emergency_contacts: list[EmergencyContactInput] | None = Field(
        default=None,
        max_length=10,
    )

    @field_validator("identifier_type")
    @classmethod
    def normalize_identifier_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", normalized):
            raise ValueError("Tipo de identificación inválido")
        return normalized

    @field_validator("identifier_value")
    @classmethod
    def normalize_identifier_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[\s-]", "", value).upper()
        if not normalized:
            raise ValueError("La identificación no puede estar vacía")
        return normalized

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        if value is not None and value and not re.fullmatch(r"[+0-9() .-]{7,24}", value):
            raise ValueError("Ingresa un teléfono de contacto válido")
        return value or None

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Ingresa un correo electrónico válido")
        return value.casefold() if value else None

    @model_validator(mode="after")
    def validate_update_fields(self) -> "PatientUpdate":
        if not self.model_fields_set:
            raise ValueError("Debe proporcionar al menos un campo")
        if ("identifier_type" in self.model_fields_set) != (
            "identifier_value" in self.model_fields_set
        ):
            raise ValueError(
                "El tipo y el valor de identificación deben corregirse juntos"
            )
        for field in ("given_name", "family_name", "birth_date"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("Nombres y fecha de nacimiento no pueden ser nulos")
        return self


class PatientSummary(PatientAPIModel):
    id: UUID
    tenant_id: UUID
    patient_number: str
    given_name: str
    family_name: str
    birth_date: date | None
    status: str
    identifier_type: str
    identifier_last_four: str | None


class EmergencyContactOut(EmergencyContactInput):
    id: UUID


class PatientDetail(PatientAPIModel):
    id: UUID
    tenant_id: UUID
    patient_number: str
    given_name: str
    family_name: str
    birth_date: date | None
    status: str
    identifier_type: str
    identifier_last_four: str | None
    phone: str | None
    email: str | None
    address: str | None
    emergency_contacts: list[EmergencyContactOut]
    created_at: datetime
    updated_at: datetime


class PatientPage(PatientAPIModel):
    items: list[PatientSummary]
    total: int
    limit: int
    offset: int


AdministrativeDocumentType = Literal[
    "identity",
    "proof_of_address",
    "administrative_form",
    "other",
]


class AdministrativeDocumentOut(PatientAPIModel):
    id: UUID
    document_type: AdministrativeDocumentType
    file_name: str
    content_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int
    created_at: datetime


class AdministrativeFileOut(PatientAPIModel):
    id: UUID
    site_id: UUID
    patient_id: UUID
    record_code: str
    created_at: datetime
    documents: list[AdministrativeDocumentOut]
