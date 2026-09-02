"""Typed conversation working-memory contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationMessageRole(StrEnum):
    """Conversation roles that may be persisted in working memory."""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationSession(BaseModel):
    """Durable conversation session metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("conversation timestamps must be timezone-aware")
        return value


class ConversationMessage(BaseModel):
    """Persisted conversation message ordered within one session."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    role: ConversationMessageRole
    content: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("conversation timestamps must be timezone-aware")
        return value


class ConversationRepository(Protocol):
    """Persistence boundary for conversation working memory."""

    def session_exists(self, session_id: str) -> bool:
        """Return whether a durable session exists."""
        ...

    def load_recent_messages(self, session_id: str, limit: int) -> list[ConversationMessage]:
        """Load bounded recent messages in original conversational order."""
        ...

    def append_successful_turn(
        self,
        *,
        session_id: str,
        user_content: str,
        assistant_content: str,
        correlation_id: str,
        create_session: bool,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Atomically persist a successful user/assistant turn."""
        ...
