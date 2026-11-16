from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from uuid import UUID

from app.core.config import get_settings


class KeycloakAdminError(Exception):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _admin_token() -> str:
    settings = get_settings()
    token_url = (
        f"{settings.keycloak_admin_base_url.rstrip('/')}/realms/"
        f"{quote(settings.keycloak_admin_realm, safe='')}/protocol/"
        "openid-connect/token"
    )
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.keycloak_admin_client_id,
            "client_secret": settings.keycloak_admin_client_secret,
        }
    ).encode("ascii")
    request = Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise KeycloakAdminError("Identity provider administration is unavailable") from exc
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise KeycloakAdminError("Identity provider returned an invalid service token")
    return access_token


def _admin_request(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | list[str] | None = None,
) -> tuple[int, dict[str, str]]:
    settings = get_settings()
    realm = quote(settings.keycloak_admin_realm, safe="")
    url = f"{settings.keycloak_admin_base_url.rstrip('/')}/admin/realms/{realm}{path}"
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
            return response.status, dict(response.headers.items())
    except HTTPError as exc:
        if exc.code == 409:
            raise KeycloakAdminError(
                "An identity with this email already exists",
                status_code=409,
            ) from exc
        raise KeycloakAdminError(
            "Identity provider administration request failed"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise KeycloakAdminError("Identity provider administration is unavailable") from exc


def create_identity(
    email: str,
    display_name: str,
    *,
    require_mfa: bool = False,
) -> UUID:
    normalized_email = email.strip().casefold()
    name_parts = display_name.strip().split(maxsplit=1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    required_actions = ["VERIFY_EMAIL", "UPDATE_PASSWORD"]
    if require_mfa:
        required_actions.append("CONFIGURE_TOTP")
    _, headers = _admin_request(
        "POST",
        "/users",
        payload={
            "username": normalized_email,
            "email": normalized_email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": False,
            "requiredActions": required_actions,
        },
    )
    location = next(
        (value for key, value in headers.items() if key.lower() == "location"),
        None,
    )
    if not location:
        raise KeycloakAdminError("Identity provider did not return the new user identifier")
    raw_subject = location.rstrip("/").rsplit("/", 1)[-1]
    try:
        subject = UUID(raw_subject)
    except ValueError as exc:
        raise KeycloakAdminError("Identity provider returned an invalid user identifier") from exc

    try:
        _admin_request(
            "PUT",
            f"/users/{quote(str(subject), safe='')}/execute-actions-email",
            payload=required_actions,
        )
    except KeycloakAdminError:
        try:
            _admin_request("DELETE", f"/users/{quote(str(subject), safe='')}")
        except KeycloakAdminError as cleanup_error:
            raise KeycloakAdminError(
                "Could not send identity activation email or remove the pending identity"
            ) from cleanup_error
        raise
    return subject


def delete_identity(subject: UUID) -> None:
    _admin_request("DELETE", f"/users/{quote(str(subject), safe='')}")
