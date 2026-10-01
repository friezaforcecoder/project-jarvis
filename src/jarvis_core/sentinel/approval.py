"""Sentinel approval contracts, errors, and request-binding service."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis_core.tools.contracts import ExecutionBoundary, SideEffectLevel

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolApprovalError(Exception):
    """Base error for Sentinel approval operations."""

    safe_message: str = "Tool approval operation failed."

    def __init__(self) -> None:
        super().__init__(self.safe_message)


class ToolApprovalBindingError(ToolApprovalError):
    """Raised when request binding computation fails."""

    safe_message = "Tool approval binding computation failed."


class ToolApprovalCanonicalizationError(ToolApprovalError):
    """Raised when argument values cannot be canonically serialized."""

    safe_message = "Tool approval arguments cannot be canonically serialized."


class ToolApprovalNotFoundError(ToolApprovalError):
    """Raised when an approval ID is unknown."""

    safe_message = "Tool approval receipt not found."


class ToolApprovalUnavailableError(ToolApprovalError):
    """Raised when a receipt cannot make the requested transition."""

    safe_message = "Tool approval receipt is unavailable."


class ToolApprovalAlreadyConsumedError(ToolApprovalError):
    """Raised when a consumed receipt is presented again."""

    safe_message = "Tool approval receipt already consumed."


class ToolApprovalExpiredError(ToolApprovalError):
    """Raised when a receipt has expired."""

    safe_message = "Tool approval receipt has expired."


class ToolApprovalMismatchError(ToolApprovalError):
    """Raised when a request binding does not match."""

    safe_message = "Tool approval request binding mismatch."


class ToolApprovalPersistenceError(ToolApprovalError):
    """Raised when approval persistence fails."""

    safe_message = "Tool approval persistence failed."


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class ToolApprovalStatus(StrEnum):
    """Lifecycle states for an approval receipt."""

    PENDING = "pending"
    APPROVED = "approved"
    CONSUMED = "consumed"


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

APPROVAL_LIFETIME: timedelta = timedelta(minutes=5)


class ToolApprovalRecord(BaseModel):
    """Frozen, extra-forbidden approval receipt with lifecycle validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: uuid.UUID
    request_binding: str = Field(min_length=64, max_length=64)
    status: ToolApprovalStatus
    created_at: datetime
    expires_at: datetime
    approved_at: datetime | None = None
    consumed_at: datetime | None = None

    @field_validator("request_binding")
    @classmethod
    def binding_must_be_lowercase_hex(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("request_binding must be exactly 64 lowercase hex characters")
        return value

    @field_validator("created_at", "expires_at", "approved_at", "consumed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware with a valid utcoffset")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.status is ToolApprovalStatus.PENDING:
            if self.approved_at is not None or self.consumed_at is not None:
                raise ValueError("pending record must have no approved_at or consumed_at")
        elif self.status is ToolApprovalStatus.APPROVED:
            if self.approved_at is None:
                raise ValueError("approved record must have approved_at")
            if self.consumed_at is not None:
                raise ValueError("approved record must not have consumed_at")
            if self.approved_at < self.created_at:
                raise ValueError("approved_at must be at or after created_at")
            if self.approved_at > self.expires_at:
                raise ValueError("approved_at must be no later than expires_at")
        elif self.status is ToolApprovalStatus.CONSUMED:
            if self.approved_at is None or self.consumed_at is None:
                raise ValueError("consumed record must have approved_at and consumed_at")
            if self.approved_at < self.created_at:
                raise ValueError("approved_at must be at or after created_at")
            if self.consumed_at < self.approved_at:
                raise ValueError("consumed_at must be at or after approved_at")
            if self.consumed_at > self.expires_at:
                raise ValueError("consumed_at must be no later than expires_at")
        return self


# ---------------------------------------------------------------------------
# Repository Protocol
# ---------------------------------------------------------------------------


class ToolApprovalRepository(Protocol):
    """Synchronous persistence boundary for approval receipts."""

    def create(self, record: ToolApprovalRecord) -> None:
        """Persist a new pending receipt. Raises on conflict."""
        ...

    def get(self, approval_id: uuid.UUID) -> ToolApprovalRecord | None:
        """Read a receipt by ID. Returns None if unknown."""
        ...

    def grant(self, approval_id: uuid.UUID, *, now: datetime) -> ToolApprovalRecord:
        """Atomically transition pending to approved. Raises on failure."""
        ...

    def consume(
        self, approval_id: uuid.UUID, request_binding: str, *, now: datetime
    ) -> ToolApprovalRecord:
        """Atomically transition approved to consumed. Raises on failure."""
        ...


# ---------------------------------------------------------------------------
# Binding Service
# ---------------------------------------------------------------------------


class ToolApprovalBindingService:
    """Process-local HMAC-SHA256 request binding service."""

    _DOMAIN = "jarvis-tool-approval/v1"

    def __init__(self, key: bytes | None = None) -> None:
        if key is not None and (not isinstance(key, bytes) or len(key) != 32):
            raise ToolApprovalBindingError()
        self._key = key if key is not None else secrets.token_bytes(32)

    def compute_binding(
        self,
        *,
        correlation_id: str,
        tool_name: str,
        side_effect_level: SideEffectLevel,
        execution_boundary: ExecutionBoundary,
        arguments: BaseModel,
    ) -> str:
        """Compute a 64-character lowercase hex HMAC-SHA256 binding digest."""
        canonical = self._canonicalize(
            correlation_id=correlation_id,
            tool_name=tool_name,
            side_effect_level=side_effect_level,
            execution_boundary=execution_boundary,
            arguments=arguments,
        )
        digest = hmac.new(self._key, canonical, hashlib.sha256).digest()
        return digest.hex()

    def compare_bindings(self, expected: str, actual: str) -> bool:
        """Constant-time comparison of two binding digests. Returns False for malformed input."""
        if len(expected) != 64 or len(actual) != 64:
            return False
        if any(c not in "0123456789abcdef" for c in expected):
            return False
        if any(c not in "0123456789abcdef" for c in actual):
            return False
        return hmac.compare_digest(expected, actual)

    def _canonicalize(
        self,
        *,
        correlation_id: str,
        tool_name: str,
        side_effect_level: SideEffectLevel,
        execution_boundary: ExecutionBoundary,
        arguments: BaseModel,
    ) -> bytes:
        try:
            payload: dict[str, object] = {
                "domain": self._DOMAIN,
                "correlation_id": correlation_id,
                "tool_name": tool_name,
                "side_effect_level": side_effect_level.value,
                "execution_boundary": execution_boundary.value,
                "arguments": arguments.model_dump(mode="json"),
            }
            return json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (ValueError, TypeError) as exc:
            raise ToolApprovalCanonicalizationError() from exc
