from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app

client = TestClient(app)


def test_health_does_not_depend_on_database() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_connection(monkeypatch) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement):
            return 1

    monkeypatch.setattr("app.api.health.engine.connect", lambda: Connection())

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_ready_returns_service_unavailable_when_database_fails(monkeypatch) -> None:
    def fail_connection():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr("app.api.health.engine.connect", fail_connection)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }
