import json
from uuid import uuid4

from app.domains.identity import keycloak_admin


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return b""

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_keycloak_invitation_uses_service_token_and_required_actions(
    monkeypatch,
) -> None:
    subject = uuid4()
    requests = []
    responses = iter(
        [
            FakeResponse(
                201,
                {"Location": f"http://keycloak/admin/realms/medigest/users/{subject}"},
            ),
            FakeResponse(204),
        ]
    )
    monkeypatch.setattr(keycloak_admin, "_admin_token", lambda: "synthetic-token")
    monkeypatch.setattr(
        keycloak_admin,
        "urlopen",
        lambda request, timeout: (requests.append(request), next(responses))[1],
    )

    result = keycloak_admin.create_identity(
        "NEW.PERSON@example.invalid",
        "Synthetic Invitee",
        require_mfa=True,
    )

    assert result == subject
    assert [request.get_method() for request in requests] == ["POST", "PUT"]
    assert all(
        request.get_header("Authorization") == "Bearer synthetic-token"
        for request in requests
    )
    user_payload = json.loads(requests[0].data)
    assert user_payload["email"] == "new.person@example.invalid"
    expected_actions = [
        "VERIFY_EMAIL",
        "UPDATE_PASSWORD",
        "CONFIGURE_TOTP",
    ]
    assert user_payload["requiredActions"] == expected_actions
    assert "credentials" not in user_payload
    assert requests[1].full_url.endswith(
        f"/users/{subject}/execute-actions-email"
    )
    assert json.loads(requests[1].data) == expected_actions
