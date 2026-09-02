"""Normalized intelligence provider errors."""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorCode(StrEnum):
    """Stable provider error codes exposed by the intelligence boundary."""

    UNKNOWN_PROVIDER = "unknown_provider"
    UNAVAILABLE = "provider_unavailable"
    REQUEST_FAILED = "provider_request_failed"
    INVALID_RESPONSE = "provider_invalid_response"
    TIMEOUT = "provider_timeout"


class ProviderError(Exception):
    """Safe normalized error raised by provider registry, router, or adapters."""

    def __init__(
        self,
        code: ProviderErrorCode,
        safe_message: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.provider_id = provider_id
        self.model = model
        self.safe_metadata = safe_metadata or {}
