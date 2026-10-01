"""Minimal tool fabric contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SideEffectLevel(StrEnum):
    """How much real-world impact a tool may have."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    DANGEROUS = "dangerous"


class ExecutionBoundary(StrEnum):
    """Where a tool is expected to execute."""

    CORE = "core"
    USER_SPACE = "user_space"
    EXTERNAL_SERVICE = "external_service"


class ToolDescriptor(BaseModel):
    """Static metadata for routing and Sentinel authorization."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    side_effect_level: SideEffectLevel
    execution_boundary: ExecutionBoundary
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolRequest(BaseModel):
    """A typed request to execute a tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, min_length=1)
    approval_id: UUID | None = None


class ToolApprovalChallenge(BaseModel):
    """Direct-client approval capability returned for a Sentinel ASK decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: UUID
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approval expiry must be timezone-aware")
        return value.astimezone(UTC)


class ToolExecutionContext(BaseModel):
    """Safe execution context supplied by the coordinator."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


class ToolResult(BaseModel):
    """A normalized tool execution result."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class Tool(Protocol):
    """Interface implemented by future tools."""

    @property
    def descriptor(self) -> ToolDescriptor:
        """Return static tool metadata."""
        ...

    @property
    def argument_model(self) -> type[BaseModel]:
        """Return the typed Pydantic model used to validate tool arguments."""
        ...

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Execute with validated arguments after Sentinel authorization."""
        ...
