"""Sentinel security and authorization contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from jarvis_core.tools import SideEffectLevel


class AuthorizationAction(StrEnum):
    """Possible Sentinel authorization outcomes."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class AuthorizationRequest(BaseModel):
    """Information Sentinel needs before a side-effecting action can run."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="user", min_length=1)
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    side_effect_level: SideEffectLevel
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, min_length=1)


class AuthorizationDecision(BaseModel):
    """Sentinel's decision and reason."""

    model_config = ConfigDict(extra="forbid")

    action: AuthorizationAction
    reason: str = Field(min_length=1)


class Sentinel(Protocol):
    """Interface implemented by future Sentinel policy engines."""

    async def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        """Authorize, deny, or request approval for an action."""
        ...
