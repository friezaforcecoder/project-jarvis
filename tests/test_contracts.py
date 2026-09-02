from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from jarvis_core.events import JarvisEvent
from jarvis_core.intelligence import (
    ProviderCapability,
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
    ProviderResponse,
)
from jarvis_core.sentinel import AuthorizationAction, AuthorizationDecision, AuthorizationRequest
from jarvis_core.tools import ExecutionBoundary, SideEffectLevel, ToolDescriptor, ToolRequest, ToolResult


def test_event_contract_requires_timezone_aware_timestamp() -> None:
    event = JarvisEvent(event_type="core.started", source="tests")

    assert event.timestamp.tzinfo is not None

    with pytest.raises(ValidationError):
        JarvisEvent(
            event_type="core.started",
            source="tests",
            timestamp=datetime(2026, 9, 1),
        )


def test_provider_contracts_are_typed_and_vendor_neutral() -> None:
    request = ProviderRequest(
        messages=[
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content="You are JARVIS."),
            ProviderMessage(role=ProviderMessageRole.USER, content="Summarize status"),
        ],
        context={"service": "jarvis-core"},
    )
    response = ProviderResponse(output="ok", model="fake-model")

    assert request.messages[0].role is ProviderMessageRole.SYSTEM
    assert request.messages[1].content == "Summarize status"
    assert not hasattr(request, "prompt")
    assert response.metadata == {}
    assert response.model == "fake-model"
    assert ProviderCapability.TEXT.value == "text"


def test_provider_response_requires_usable_output_text() -> None:
    with pytest.raises(ValidationError):
        ProviderResponse(output="", model="fake-model")

    with pytest.raises(ValidationError):
        ProviderResponse(output="   ", model="fake-model")


def test_tool_contract_describes_side_effects_for_sentinel() -> None:
    descriptor = ToolDescriptor(
        name="health.read",
        description="Read core health.",
        side_effect_level=SideEffectLevel.READ,
        execution_boundary=ExecutionBoundary.CORE,
        input_schema={"type": "object", "properties": {}},
    )
    request = ToolRequest(tool_name=descriptor.name, arguments={})
    result = ToolResult(success=True, data={"status": "ok"})

    assert descriptor.side_effect_level is SideEffectLevel.READ
    assert request.tool_name == "health.read"
    assert result.error is None


def test_sentinel_contract_returns_action_and_reason() -> None:
    request = AuthorizationRequest(
        action="health.read",
        resource="/v1/health",
        side_effect_level=SideEffectLevel.READ,
        context={"source": "tests"},
    )
    decision = AuthorizationDecision(
        action=AuthorizationAction.ALLOW,
        reason="Read-only health check.",
    )

    assert request.subject == "user"
    assert decision.action is AuthorizationAction.ALLOW
    assert decision.reason


def test_architectural_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        JarvisEvent(event_type="core.started", source="tests", surprise=True)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ProviderRequest(
            messages=[ProviderMessage(role=ProviderMessageRole.USER, content="hello")],
            provider="specific",
        )  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ProviderMessage(role=ProviderMessageRole.USER, content="hello", surprise=True)  # type: ignore[call-arg]
