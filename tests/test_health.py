from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis_core.config import Settings


def test_health_endpoint_returns_bootstrap_semantics(
    client: TestClient,
    settings: Settings,
) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "jarvis-core",
        "version": settings.version,
    }


def test_startup_initializes_sqlite_database(settings: Settings, client: TestClient) -> None:
    client.get("/v1/health")

    assert settings.database_path.exists()
