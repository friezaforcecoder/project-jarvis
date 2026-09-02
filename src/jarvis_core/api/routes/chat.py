"""Chat endpoint for the first text intelligence loop."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from jarvis_core.conversations import (
    ConversationPersistenceError,
    ConversationSessionNotFoundError,
)
from jarvis_core.intelligence import ChatService, ProviderError, ProviderErrorCode

router = APIRouter(tags=["chat"])

_PROVIDER_ERROR_STATUS = {
    ProviderErrorCode.UNKNOWN_PROVIDER: 500,
    ProviderErrorCode.UNAVAILABLE: 502,
    ProviderErrorCode.REQUEST_FAILED: 502,
    ProviderErrorCode.INVALID_RESPONSE: 502,
    ProviderErrorCode.TIMEOUT: 504,
}


class ChatRequest(BaseModel):
    """User input for a single text chat turn."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    """Normalized assistant response for a single text chat turn."""

    model_config = ConfigDict(extra="forbid")

    message: str
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class ChatError(BaseModel):
    """Safe API error details for provider failures."""

    model_config = ConfigDict(extra="forbid")

    code: ProviderErrorCode
    message: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)


class SessionError(BaseModel):
    """Safe API error details for session failures."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["session_not_found"]
    message: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class PersistenceError(BaseModel):
    """Safe API error details for persistence failures."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["conversation_persistence_failed"]
    message: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


class ChatErrorResponse(BaseModel):
    """Stable error envelope for chat provider failures."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error: ChatError | SessionError | PersistenceError


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        500: {"model": ChatErrorResponse},
        404: {"model": ChatErrorResponse},
        502: {"model": ChatErrorResponse},
        504: {"model": ChatErrorResponse},
    },
)
async def post_chat(chat_request: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    """Route one text message through the configured intelligence provider."""

    correlation_id = chat_request.correlation_id or str(uuid4())
    chat_service: ChatService = request.app.state.chat_service

    try:
        result = await chat_service.chat(
            message=chat_request.message,
            correlation_id=correlation_id,
            session_id=str(chat_request.session_id) if chat_request.session_id else None,
        )
    except ConversationSessionNotFoundError as exc:
        error = ChatErrorResponse(
            error=SessionError(
                code=exc.code.value,
                message=exc.safe_message,
                correlation_id=correlation_id,
                session_id=exc.session_id,
            )
        )
        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))
    except ConversationPersistenceError as exc:
        error = ChatErrorResponse(
            error=PersistenceError(
                code=exc.code.value,
                message=exc.safe_message,
                correlation_id=correlation_id,
            )
        )
        return JSONResponse(status_code=500, content=error.model_dump(mode="json"))
    except ProviderError as exc:
        error = ChatErrorResponse(
            error=ChatError(
                code=exc.code,
                message=exc.safe_message,
                correlation_id=correlation_id,
                provider=exc.provider_id,
                model=exc.model,
            )
        )
        return JSONResponse(
            status_code=_PROVIDER_ERROR_STATUS[exc.code],
            content=error.model_dump(mode="json"),
        )

    return ChatResponse(
        message=result.message,
        provider=result.provider,
        model=result.model,
        correlation_id=result.correlation_id,
        session_id=result.session_id,
    )
