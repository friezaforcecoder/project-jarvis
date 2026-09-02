"""Minimal tool fabric contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


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

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Execute a tool request after Sentinel authorization."""
        ...
