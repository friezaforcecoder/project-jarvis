"""Stable interfaces for replaceable intelligence providers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderCapability(StrEnum):
    """Small capability labels advertised by intelligence providers."""

    TEXT = "text"


class ProviderMessageRole(StrEnum):
    """Provider-neutral roles for ordered model input."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ProviderMessage(BaseModel):
    """One provider-neutral message in an ordered model request."""

    model_config = ConfigDict(extra="forbid")

    role: ProviderMessageRole
    content: str = Field(min_length=1)


class ProviderRequest(BaseModel):
    """Input contract for a provider call."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ProviderMessage] = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, min_length=1)


class ProviderResponse(BaseModel):
    """Normalized provider response contract."""

    model_config = ConfigDict(extra="forbid")

    output: str
    model: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntelligenceProvider(Protocol):
    """Interface implemented by future model provider adapters."""

    @property
    def provider_id(self) -> str:
        """Return a stable provider identifier."""
        ...

    @property
    def capabilities(self) -> frozenset[ProviderCapability]:
        """Return the provider capabilities available to the core."""
        ...

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a response for the given request."""
        ...
