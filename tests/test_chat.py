from __future__ import annotations

import logging
from uuid import UUID

from fastapi.testclient import TestClient

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.intelligence import (
    ChatService,
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
)


class FakeProvider:
    provider_id = "fake"
    capabilities = frozenset({ProviderCapability.TEXT})

    def __init__(self, error: ProviderError | None = None) -> None:
        self.error = error
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self.error:
            raise self.error
        return ProviderResponse(output="Hello from fake JARVIS.", model="fake-model")


def build_client(settings: Settings, provider: FakeProvider) -> TestClient:
    registry = ProviderRegistry()
    registry.register(provider)
    return TestClient(create_app(settings, registry))


def test_post_chat_routes_to_fake_provider_and_returns_response(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "jarvis.sqlite3",
        intelligence_provider="fake",
        system_instruction="You are test JARVIS.",
    )
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "Hello", "correlation_id": "test-correlation"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Hello from fake JARVIS.",
        "provider": "fake",
        "model": "fake-model",
        "correlation_id": "test-correlation",
    }
    assert provider.requests[0].prompt == "Hello"
    assert provider.requests[0].system_instruction == "You are test JARVIS."
    assert provider.requests[0].correlation_id == "test-correlation"


def test_post_chat_generates_correlation_id_when_omitted(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        response = client.post("/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    correlation_id = response.json()["correlation_id"]
    assert UUID(correlation_id)
    assert provider.requests[0].correlation_id == correlation_id


def test_post_chat_returns_normalized_provider_timeout(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider(
        ProviderError(
            ProviderErrorCode.TIMEOUT,
            "Intelligence provider timed out.",
            provider_id="fake",
            model="fake-model",
        )
    )

    with build_client(settings, provider) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "Hello", "correlation_id": "timeout-correlation"},
        )

    assert response.status_code == 504
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "provider_timeout",
            "message": "Intelligence provider timed out.",
            "correlation_id": "timeout-correlation",
            "provider": "fake",
            "model": "fake-model",
        },
    }


def test_post_chat_returns_normalized_unavailable_provider(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider(
        ProviderError(
            ProviderErrorCode.UNAVAILABLE,
            "Intelligence provider is unavailable.",
            provider_id="fake",
            model="fake-model",
        )
    )

    with build_client(settings, provider) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "Hello", "correlation_id": "unavailable-correlation"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert response.json()["error"]["correlation_id"] == "unavailable-correlation"


def test_post_chat_returns_unknown_provider_error(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "jarvis.sqlite3",
        intelligence_provider="missing",
    )
    registry = ProviderRegistry()

    with TestClient(create_app(settings, registry)) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "Hello", "correlation_id": "unknown-correlation"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "unknown_provider",
            "message": "Configured intelligence provider is not registered.",
            "correlation_id": "unknown-correlation",
            "provider": "missing",
            "model": None,
        },
    }


def test_chat_logging_omits_raw_prompts_and_responses(tmp_path, caplog) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = ChatService(settings, registry)

    caplog.set_level(logging.INFO, logger="jarvis_core.intelligence.router")

    import anyio

    anyio.run(service.chat, "secret user prompt", "log-correlation")

    assert "secret user prompt" not in caplog.text
    assert "Hello from fake JARVIS." not in caplog.text
    assert any(
        record.__dict__.get("correlation_id") == "log-correlation"
        for record in caplog.records
    )
