from __future__ import annotations

import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.context import VisibleApplicationsContext
from jarvis_core.sentinel import AuthorizationAction, AuthorizationDecision
from jarvis_core.tools import ExecutionBoundary, SideEffectLevel, ToolRegistry
from jarvis_core.tools.builtins import (
    VisibleApplicationsArguments,
    VisibleApplicationsTool,
    create_builtin_tool_registry,
)


class RecordingSentinel:
    def __init__(self, order: list[str], action=AuthorizationAction.ALLOW) -> None:
        self.order = order
        self.action = action
        self.requests = []

    async def authorize(self, request):
        self.order.append("authorize")
        self.requests.append(request)
        return AuthorizationDecision(action=self.action, reason="Test policy.")


def test_visible_applications_registration_and_strict_arguments() -> None:
    descriptor = create_builtin_tool_registry().descriptor("context.visible_applications")
    assert descriptor.side_effect_level is SideEffectLevel.READ
    assert descriptor.execution_boundary is ExecutionBoundary.CORE
    assert descriptor.input_schema["additionalProperties"] is False
    assert descriptor.input_schema["properties"] == {}
    assert VisibleApplicationsArguments.model_validate({}).model_dump() == {}
    with pytest.raises(ValidationError):
        VisibleApplicationsArguments.model_validate({"include_background": True})


@pytest.mark.parametrize(
    "data",
    [
        {"available": True, "platform_family": "Windows", "applications": ["Code"], "reason": None},
        {"available": True, "platform_family": "Windows", "applications": [], "reason": None},
        {"available": False, "platform_family": "Linux", "applications": [], "reason": "unsupported_platform"},
    ],
)
def test_direct_tool_runs_after_sentinel_and_returns_only_typed_data(tmp_path, data) -> None:
    order = []
    sentinel = RecordingSentinel(order)

    def collect():
        assert order == ["authorize"]
        order.append("collect")
        return VisibleApplicationsContext.model_validate(data)

    registry = ToolRegistry()
    registry.register(VisibleApplicationsTool(collector=collect))
    settings = Settings(database_path=tmp_path / "direct.sqlite3", log_level="WARNING")
    with TestClient(create_app(settings, tool_registry=registry, sentinel=sentinel)) as client:
        response = client.post("/v1/tools/execute", json={
            "tool_name": "context.visible_applications", "arguments": {},
            "correlation_id": "visible-direct",
        })

    assert response.status_code == 200
    assert response.json()["result"] == {"success": True, "data": data, "error": None}
    assert response.json()["sentinel"]["decision"] == "allow"
    assert order == ["authorize", "collect"]
    assert len(sentinel.requests) == 1
    request = sentinel.requests[0]
    assert request.action == "context.visible_applications"
    assert request.side_effect_level is SideEffectLevel.READ
    assert request.execution_boundary is ExecutionBoundary.CORE
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM conversation_messages").fetchone() == (0,)


@pytest.mark.parametrize(
    ("arguments", "decision", "status", "code", "expected_order"),
    [
        ({"pid": 123}, AuthorizationAction.ALLOW, 422, "tool_invalid_arguments", []),
        ({}, AuthorizationAction.ASK, 409, "tool_approval_required", ["authorize"]),
        ({}, AuthorizationAction.DENY, 403, "tool_denied", ["authorize"]),
    ],
)
def test_invalid_arguments_or_sentinel_refusal_never_collect(
    tmp_path, arguments, decision, status, code, expected_order,
) -> None:
    order = []
    sentinel = RecordingSentinel(order, decision)

    def collect():
        raise AssertionError("Unauthorized collection must not execute")

    registry = ToolRegistry()
    registry.register(VisibleApplicationsTool(collector=collect))
    settings = Settings(database_path=tmp_path / "blocked.sqlite3", log_level="WARNING")
    with TestClient(create_app(settings, tool_registry=registry, sentinel=sentinel)) as client:
        response = client.post("/v1/tools/execute", json={
            "tool_name": "context.visible_applications", "arguments": arguments,
        })

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert order == expected_order


@pytest.mark.parametrize("fail", [False, True])
def test_tool_logs_and_errors_exclude_application_names_and_native_details(
    tmp_path, caplog, fail,
) -> None:
    sensitive_name = "PRIVATE_APP_SENTINEL"
    sensitive_error = r"C:\Users\private-person\PRIVATE_NATIVE_ERROR"

    def collect():
        if fail:
            raise RuntimeError(sensitive_error)
        return VisibleApplicationsContext(
            available=True, platform_family="Windows",
            applications=[sensitive_name], reason=None,
        )

    registry = ToolRegistry()
    registry.register(VisibleApplicationsTool(collector=collect))
    settings = Settings(database_path=tmp_path / "safe.sqlite3", log_level="INFO")
    with TestClient(create_app(settings, tool_registry=registry)) as client:
        caplog.set_level(logging.INFO)
        # App construction installs its production handler; capture the same
        # emitted records after that setup rather than inspecting an empty log.
        logging.getLogger().addHandler(caplog.handler)
        response = client.post("/v1/tools/execute", json={
            "tool_name": "context.visible_applications", "arguments": {},
            "correlation_id": "visible-log-check",
        })

    assert response.status_code == (500 if fail else 200)
    if fail:
        assert response.json()["error"] == {
            "code": "tool_execution_failed", "message": "Tool execution failed.",
            "tool_name": "context.visible_applications", "correlation_id": "visible-log-check",
        }
        assert sensitive_error not in response.text
    records = json.dumps([record.__dict__ for record in caplog.records], default=str)
    assert sensitive_name not in records
    assert sensitive_error not in records
    assert "PRIVATE_NATIVE_ERROR" not in records
    assert any(record.__dict__.get("tool_name") == "context.visible_applications" for record in caplog.records)
