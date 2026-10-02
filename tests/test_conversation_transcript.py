from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from jarvis_core.conversations import ConversationPersistenceError


class FailingConversationRepository:
    def session_exists(self, session_id: str) -> bool:
        raise ConversationPersistenceError()


def create_session(client: TestClient, *, turns: int = 1) -> str:
    session_id = str(uuid4())
    repository = client.app.state.conversation_repository
    for index in range(turns):
        repository.append_successful_turn(
            session_id=session_id,
            user_content=f"user-{index}",
            assistant_content=f"assistant-{index}",
            correlation_id=f"correlation-{index}",
            create_session=index == 0,
        )
    return session_id


def test_transcript_returns_bounded_core_owned_messages(client: TestClient) -> None:
    session_id = create_session(client, turns=2)

    response = client.get(f"/v1/conversations/{session_id}/messages?limit=3")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert [(message["role"], message["content"]) for message in body["messages"]] == [
        ("assistant", "assistant-0"),
        ("user", "user-1"),
        ("assistant", "assistant-1"),
    ]
    assert all(set(message) == {"role", "content", "created_at"} for message in body["messages"])
    assert all(datetime.fromisoformat(message["created_at"]).tzinfo is not None for message in body["messages"])


def test_transcript_preserves_content_as_data(client: TestClient) -> None:
    session_id = str(uuid4())
    client.app.state.conversation_repository.append_successful_turn(
        session_id=session_id,
        user_content='<img src=x onerror="alert(1)">',
        assistant_content="Use <strong>plain text</strong> safely.",
        correlation_id="markup-data",
        create_session=True,
    )

    response = client.get(f"/v1/conversations/{session_id}/messages")

    assert response.status_code == 200
    assert [message["content"] for message in response.json()["messages"]] == [
        '<img src=x onerror="alert(1)">',
        "Use <strong>plain text</strong> safely.",
    ]


def test_transcript_returns_safe_unknown_session_error(client: TestClient) -> None:
    session_id = uuid4()

    response = client.get(f"/v1/conversations/{session_id}/messages")

    assert response.status_code == 404
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "session_not_found",
            "message": "Conversation session was not found.",
            "session_id": str(session_id),
        },
    }


def test_transcript_rejects_malformed_session_and_out_of_range_limit(
    client: TestClient,
) -> None:
    malformed = client.get("/v1/conversations/not-a-uuid/messages")
    too_large = client.get(f"/v1/conversations/{uuid4()}/messages?limit=201")

    assert malformed.status_code == 422
    assert too_large.status_code == 422


def test_transcript_normalizes_persistence_failure(client: TestClient) -> None:
    session_id = uuid4()
    client.app.state.conversation_repository = FailingConversationRepository()

    response = client.get(f"/v1/conversations/{session_id}/messages")

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "conversation_persistence_failed",
            "message": "Conversation persistence failed.",
            "session_id": str(session_id),
        },
    }


def test_transcript_contract_uses_uuid_session_id(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.get(f"/v1/conversations/{session_id}/messages")

    assert UUID(response.json()["session_id"]) == UUID(session_id)
