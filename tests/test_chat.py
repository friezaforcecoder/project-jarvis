from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from uuid import UUID

import anyio
import pytest
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
from jarvis_core.persistence import SQLiteConversationRepository, initialize_sqlite


class FakeProvider:
    provider_id = "fake"
    capabilities = frozenset({ProviderCapability.TEXT})

    def __init__(
        self,
        error: ProviderError | None = None,
        output: str = "Hello from fake JARVIS.",
    ) -> None:
        self.error = error
        self.output = output
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self.error:
            raise self.error
        return ProviderResponse(output=self.output, model="fake-model")


class SlowTrackingProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.active_calls = 0
        self.max_active_calls = 0

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await anyio.sleep(0.05)
            current_user_message = request.messages[-1].content
            return ProviderResponse(
                output=f"response to {current_user_message}",
                model="fake-model",
            )
        finally:
            self.active_calls -= 1


def build_registry(provider: FakeProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(provider)
    return registry


def build_client(settings: Settings, provider: FakeProvider) -> TestClient:
    return TestClient(create_app(settings, build_registry(provider)))


def build_service(settings: Settings, provider: FakeProvider) -> ChatService:
    initialize_sqlite(settings)
    return ChatService(
        settings,
        build_registry(provider),
        SQLiteConversationRepository(settings.database_path),
    )


def read_database_messages(database_path: Path, session_id: str | None = None) -> list[sqlite3.Row]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        if session_id is None:
            return connection.execute(
                """
                SELECT session_id, sequence, role, content, correlation_id
                FROM conversation_messages
                ORDER BY session_id, sequence
                """
            ).fetchall()
        return connection.execute(
            """
            SELECT session_id, sequence, role, content, correlation_id
            FROM conversation_messages
            WHERE session_id = ?
            ORDER BY sequence
            """,
            (session_id,),
        ).fetchall()


def count_database_sessions(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0])


def provider_messages(request: ProviderRequest) -> list[tuple[str, str]]:
    return [(message.role.value, message.content) for message in request.messages]


def test_post_chat_generates_session_id_and_persists_successful_turn(tmp_path) -> None:
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
    body = response.json()
    session_id = body["session_id"]
    assert UUID(session_id)
    assert body == {
        "message": "Hello from fake JARVIS.",
        "provider": "fake",
        "model": "fake-model",
        "correlation_id": "test-correlation",
        "session_id": session_id,
    }
    assert provider_messages(provider.requests[0]) == [
        ("system", "You are test JARVIS."),
        ("user", "Hello"),
    ]
    assert provider.requests[0].correlation_id == "test-correlation"
    assert not hasattr(provider.requests[0], "prompt")

    rows = read_database_messages(settings.database_path, session_id)
    assert [(row["sequence"], row["role"], row["content"]) for row in rows] == [
        (1, "user", "Hello"),
        (2, "assistant", "Hello from fake JARVIS."),
    ]
    assert {row["correlation_id"] for row in rows} == {"test-correlation"}


def test_post_chat_generates_correlation_id_when_omitted(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        response = client.post("/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    correlation_id = response.json()["correlation_id"]
    assert UUID(correlation_id)
    assert UUID(response.json()["session_id"])
    assert provider.requests[0].correlation_id == correlation_id


def test_post_chat_reuses_existing_session_and_includes_history(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "jarvis.sqlite3",
        intelligence_provider="fake",
        system_instruction="Identity.",
    )
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        first_response = client.post("/v1/chat", json={"message": "First"}).json()
        session_id = first_response["session_id"]
        second_response = client.post(
            "/v1/chat",
            json={
                "message": "Second",
                "session_id": session_id,
                "correlation_id": "second-correlation",
            },
        )

    assert second_response.status_code == 200
    assert second_response.json()["session_id"] == session_id
    assert provider_messages(provider.requests[1]) == [
        ("system", "Identity."),
        ("user", "First"),
        ("assistant", "Hello from fake JARVIS."),
        ("user", "Second"),
    ]
    rows = read_database_messages(settings.database_path, session_id)
    assert [(row["sequence"], row["role"], row["content"]) for row in rows] == [
        (1, "user", "First"),
        (2, "assistant", "Hello from fake JARVIS."),
        (3, "user", "Second"),
        (4, "assistant", "Hello from fake JARVIS."),
    ]


def test_post_chat_with_history_limit_zero_sends_no_prior_messages(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "jarvis.sqlite3",
        intelligence_provider="fake",
        chat_history_limit=0,
        system_instruction="Identity.",
    )
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        session_id = client.post("/v1/chat", json={"message": "First"}).json()["session_id"]
        response = client.post(
            "/v1/chat",
            json={"message": "Second", "session_id": session_id},
        )

    assert response.status_code == 200
    assert provider_messages(provider.requests[1]) == [
        ("system", "Identity."),
        ("user", "Second"),
    ]


def test_session_history_survives_app_restart(tmp_path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    first_settings = Settings(database_path=database_path, intelligence_provider="fake")
    first_provider = FakeProvider()

    with build_client(first_settings, first_provider) as client:
        session_id = client.post(
            "/v1/chat",
            json={"message": "Remember restart state."},
        ).json()["session_id"]

    second_settings = Settings(database_path=database_path, intelligence_provider="fake")
    second_provider = FakeProvider()
    with build_client(second_settings, second_provider) as client:
        response = client.post(
            "/v1/chat",
            json={"message": "What did I ask you to remember?", "session_id": session_id},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
    assert provider_messages(second_provider.requests[0]) == [
        (
            "system",
            "You are JARVIS, a local-first personal AI assistant. Be concise, helpful, and honest.",
        ),
        ("user", "Remember restart state."),
        ("assistant", "Hello from fake JARVIS."),
        ("user", "What did I ask you to remember?"),
    ]


def test_post_chat_returns_unknown_session_error_before_provider_execution(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()
    unknown_session_id = "11111111-1111-4111-8111-111111111111"

    with build_client(settings, provider) as client:
        response = client.post(
            "/v1/chat",
            json={
                "message": "Hello",
                "session_id": unknown_session_id,
                "correlation_id": "unknown-session-correlation",
            },
        )

    assert response.status_code == 404
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "session_not_found",
            "message": "Conversation session was not found.",
            "correlation_id": "unknown-session-correlation",
            "session_id": unknown_session_id,
        },
    }
    assert provider.requests == []
    assert count_database_sessions(settings.database_path) == 0


def test_post_chat_rejects_malformed_session_id_before_provider_execution(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        response = client.post(
            "/v1/chat",
            json={
                "message": "Hello",
                "session_id": "not-a-session-id",
                "correlation_id": "bad-session-correlation",
            },
        )

    assert response.status_code == 422
    assert provider.requests == []
    assert count_database_sessions(settings.database_path) == 0


def test_post_chat_returns_normalized_provider_timeout_without_creating_new_session(
    tmp_path,
) -> None:
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
    assert count_database_sessions(settings.database_path) == 0
    assert read_database_messages(settings.database_path) == []


def test_provider_failure_leaves_existing_session_unchanged(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        session_id = client.post("/v1/chat", json={"message": "First"}).json()["session_id"]
        before_failure = read_database_messages(settings.database_path, session_id)
        provider.error = ProviderError(
            ProviderErrorCode.TIMEOUT,
            "Intelligence provider timed out.",
            provider_id="fake",
            model="fake-model",
        )
        response = client.post(
            "/v1/chat",
            json={
                "message": "Second",
                "session_id": session_id,
                "correlation_id": "failed-existing-session",
            },
        )

    assert response.status_code == 504
    assert read_database_messages(settings.database_path, session_id) == before_failure
    assert provider_messages(provider.requests[1]) == [
        (
            "system",
            "You are JARVIS, a local-first personal AI assistant. Be concise, helpful, and honest.",
        ),
        ("user", "First"),
        ("assistant", "Hello from fake JARVIS."),
        ("user", "Second"),
    ]


def test_persistence_failure_rolls_back_turn_and_returns_stable_error(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = FakeProvider()

    with build_client(settings, provider) as client:
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_assistant_insert
                BEFORE INSERT ON conversation_messages
                WHEN NEW.role = 'assistant'
                BEGIN
                    SELECT RAISE(FAIL, 'assistant insert failed');
                END
                """
            )

        response = client.post(
            "/v1/chat",
            json={"message": "Hello", "correlation_id": "persistence-failure"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "conversation_persistence_failed",
            "message": "Conversation persistence failed.",
            "correlation_id": "persistence-failure",
        },
    }
    assert len(provider.requests) == 1
    assert count_database_sessions(settings.database_path) == 0
    assert read_database_messages(settings.database_path) == []


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
    provider = FakeProvider(output="secret assistant response")
    service = build_service(settings, provider)

    caplog.set_level(logging.INFO, logger="jarvis_core.intelligence.router")

    anyio.run(service.chat, "secret user prompt", "log-correlation")

    assert "secret user prompt" not in caplog.text
    assert "secret assistant response" not in caplog.text
    assert any(
        record.__dict__.get("correlation_id") == "log-correlation"
        for record in caplog.records
    )
    assert any("session_id" in record.__dict__ for record in caplog.records)


@pytest.mark.anyio
async def test_same_session_concurrent_chats_are_serialized_and_ordered(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = SlowTrackingProvider()
    service = build_service(settings, provider)

    seed = await service.chat("seed", "seed-correlation")

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(service.chat, "one", "one-correlation", seed.session_id)
        task_group.start_soon(service.chat, "two", "two-correlation", seed.session_id)

    assert provider.max_active_calls == 1
    rows = read_database_messages(settings.database_path, seed.session_id)
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert [row["role"] for row in rows] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


@pytest.mark.anyio
async def test_different_sessions_can_operate_concurrently(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", intelligence_provider="fake")
    provider = SlowTrackingProvider()
    service = build_service(settings, provider)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(service.chat, "one", "one-correlation")
        task_group.start_soon(service.chat, "two", "two-correlation")

    assert provider.max_active_calls == 2
