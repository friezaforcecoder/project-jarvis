"""Normalized Tool Fabric errors."""

from __future__ import annotations

from enum import StrEnum


class ToolErrorCode(StrEnum):
    """Stable Tool Fabric error codes."""

    DUPLICATE_TOOL = "tool_duplicate"
    TOOL_NOT_FOUND = "tool_not_found"
    INVALID_ARGUMENTS = "tool_invalid_arguments"
    APPROVAL_REQUIRED = "tool_approval_required"
    DENIED = "tool_denied"
    EXECUTION_FAILED = "tool_execution_failed"
    SENTINEL_AUTHORIZATION_FAILED = "sentinel_authorization_failed"
    INTERNAL_ERROR = "tool_internal_error"


class ToolExecutionError(Exception):
    """Safe normalized error raised by Tool Fabric components."""

    def __init__(
        self,
        code: ToolErrorCode,
        safe_message: str,
        *,
        tool_name: str | None = None,
        correlation_id: str | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.tool_name = tool_name
        self.correlation_id = correlation_id
        self.safe_metadata = safe_metadata or {}
