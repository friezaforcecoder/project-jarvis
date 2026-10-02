"""Read-only conversation transcript endpoint for trusted local interfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from jarvis_core.conversations import (
    ConversationMessageRole,
    ConversationPersistenceError,
    ConversationRepository,
)

router = APIRouter(tags=["conversations"])


class TranscriptMessage(BaseModel):
    """Minimal persisted message representation for a local interface."""

    model_config = ConfigDict(extra="forbid")

    role: ConversationMessageRole
    content: str = Field(min_length=1)
    created_at: datetime


class TranscriptResponse(BaseModel):
    """Bounded transcript for one known durable session."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    messages: list[TranscriptMessage]


class TranscriptError(BaseModel):
    """Safe transcript lookup error details."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["session_not_found", "conversation_persistence_failed"]
    message: str = Field(min_length=1)
    session_id: UUID


class TranscriptErrorResponse(BaseModel):
    """Stable transcript lookup error envelope."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error: TranscriptError


@router.get(
    "/conversations/{session_id}/messages",
    response_model=TranscriptResponse,
    responses={
        404: {"model": TranscriptErrorResponse},
        500: {"model": TranscriptErrorResponse},
    },
)
def get_transcript(
    session_id: UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
) -> TranscriptResponse | JSONResponse:
    """Load bounded persisted messages for one caller-supplied session ID."""

    repository: ConversationRepository = request.app.state.conversation_repository
    normalized_session_id = str(session_id)
    try:
        if not repository.session_exists(normalized_session_id):
            return _transcript_error(
                status_code=404,
                code="session_not_found",
                message="Conversation session was not found.",
                session_id=session_id,
            )
        messages = repository.load_transcript(normalized_session_id, limit)
    except ConversationPersistenceError:
        return _transcript_error(
            status_code=500,
            code="conversation_persistence_failed",
            message="Conversation persistence failed.",
            session_id=session_id,
        )

    return TranscriptResponse(
        session_id=session_id,
        messages=[
            TranscriptMessage(
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


def _transcript_error(
    *,
    status_code: int,
    code: Literal["session_not_found", "conversation_persistence_failed"],
    message: str,
    session_id: UUID,
) -> JSONResponse:
    response = TranscriptErrorResponse(
        error=TranscriptError(
            code=code,
            message=message,
            session_id=session_id,
        )
    )
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))
