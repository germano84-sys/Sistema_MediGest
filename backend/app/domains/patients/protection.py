from __future__ import annotations

import hashlib
import hmac
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def encrypt_value(value: str) -> bytes:
    key = get_settings().patient_data_encryption_key.encode("ascii")
    return Fernet(key).encrypt(value.encode("utf-8"))


def decrypt_value(value: bytes) -> str:
    key = get_settings().patient_data_encryption_key.encode("ascii")
    try:
        return Fernet(key).decrypt(value).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Stored patient data could not be decrypted") from exc


def encrypt_json(value: dict[str, object]) -> bytes:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encrypt_value(serialized)


def decrypt_json(value: bytes) -> dict[str, object]:
    try:
        result = json.loads(decrypt_value(value))
    except json.JSONDecodeError as exc:
        raise ValueError("Stored patient data is not valid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Stored patient data must be an object")
    return result


def encrypt_administrative_document(value: bytes) -> bytes:
    key = get_settings().administrative_document_encryption_key.encode("ascii")
    return Fernet(key).encrypt(value)


def decrypt_administrative_document(value: bytes) -> bytes:
    key = get_settings().administrative_document_encryption_key.encode("ascii")
    try:
        return Fernet(key).decrypt(value)
    except InvalidToken as exc:
        raise ValueError("Stored administrative document could not be decrypted") from exc


def identifier_digest(identifier_type: str, identifier_value: str) -> str:
    settings = get_settings()
    normalized_type = identifier_type.strip().casefold()
    normalized_value = identifier_value.strip().upper()
    message = f"{normalized_type}\0{normalized_value}".encode("utf-8")
    return hmac.new(
        settings.patient_identifier_hmac_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
