"""Deterministic default Sentinel policy."""

from __future__ import annotations

from jarvis_core.sentinel.contracts import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
)
from jarvis_core.tools.contracts import SideEffectLevel


class DefaultSentinelPolicy:
    """Authorize tools using the v0.4 side-effect policy table."""

    async def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        """Return the deterministic decision for the requested side-effect level."""

        if request.side_effect_level in {SideEffectLevel.NONE, SideEffectLevel.READ}:
            return AuthorizationDecision(
                action=AuthorizationAction.ALLOW,
                reason="Safe no-write tool execution is allowed.",
            )
        if request.side_effect_level == SideEffectLevel.WRITE:
            return AuthorizationDecision(
                action=AuthorizationAction.ASK,
                reason="Write-capable tool execution requires approval.",
            )
        return AuthorizationDecision(
            action=AuthorizationAction.DENY,
            reason="Dangerous tool execution is denied.",
        )
