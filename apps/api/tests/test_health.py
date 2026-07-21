from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app, engine


def test_health_live() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


def test_health_ready_when_database_is_unavailable(monkeypatch) -> None:
    connection_error = OperationalError(
        "SELECT 1",
        {},
        RuntimeError("database unavailable"),
    )
    monkeypatch.setattr(
        engine,
        "connect",
        MagicMock(side_effect=connection_error),
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
