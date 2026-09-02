"""Stable interfaces for replaceable intelligence providers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderCapability(StrEnum):
    """Small capability labels advertised by intelligence providers."""

    TEXT = "text"


class ProviderRequest(BaseModel):
    """Input contract for a provider call."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1)
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
