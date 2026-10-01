"""Allowlisted, payload-free tool execution audit contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis_core.sentinel.contracts import AuthorizationAction
from jarvis_core.tools.contracts import ExecutionBoundary, SideEffectLevel
from jarvis_core.tools.errors import ToolErrorCode


class ToolAuditOutcome(StrEnum):
    """Lifecycle outcomes recorded without arguments, results, or error text."""

    STARTED = "started"
    TOOL_NOT_FOUND = "tool_not_found"
    INVALID_ARGUMENTS = "invalid_arguments"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_INVALID = "approval_invalid"
    DENIED = "denied"
    AUTHORIZATION_FAILED = "authorization_failed"
    SUCCEEDED = "succeeded"
    TOOL_FAILED = "tool_failed"
    INTERNAL_FAILURE = "internal_failure"


class ToolAuditRecord(BaseModel):
    """One immutable snapshot of a tool execution's audit lifecycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    side_effect_level: SideEffectLevel | None = None
    execution_boundary: ExecutionBoundary | None = None
    sentinel_decision: AuthorizationAction | None = None
    outcome: ToolAuditOutcome = ToolAuditOutcome.STARTED
    error_code: ToolErrorCode | None = None
    started_at: datetime
    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("audit timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("audit_id")
    @classmethod
    def audit_id_must_be_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.audit_id == self.correlation_id:
            raise ValueError("audit ID must differ from the correlation ID")
        if self.outcome is ToolAuditOutcome.STARTED:
            if self.completed_at is not None or self.error_code is not None:
                raise ValueError("started audit records cannot have completion or error metadata")
        elif self.completed_at is None:
            raise ValueError("completed audit outcomes require a completion timestamp")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("audit completion cannot precede its start")
        if self.outcome is ToolAuditOutcome.SUCCEEDED and self.error_code is not None:
            raise ValueError("successful audit records cannot have an error code")
        if (
            self.outcome not in {ToolAuditOutcome.STARTED, ToolAuditOutcome.SUCCEEDED}
            and self.error_code is None
        ):
            raise ValueError("failed audit records require an error code")
        return self


class ToolAuditRepository(Protocol):
    """Synchronous persistence boundary for durable tool execution evidence."""

    def create(self, record: ToolAuditRecord) -> None:
        """Persist an initial started record before any tool lookup or execution."""
        ...

    def update(self, record: ToolAuditRecord) -> None:
        """Persist a later snapshot while the stored record is still started."""
        ...

    def list_for_correlation(self, correlation_id: str) -> list[ToolAuditRecord]:
        """Read one correlation's records in deterministic start/identifier order."""
        ...
