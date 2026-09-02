from __future__ import annotations

import getpass
import platform
import socket
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.sentinel import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
    DefaultSentinelPolicy,
)
from jarvis_core.tools import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolDescriptor,
    ToolErrorCode,
    ToolExecutionContext,
    ToolExecutionError,
    ToolRegistry,
    ToolRequest,
    ToolResult,
)
from jarvis_core.tools.builtins import RuntimeInfoTool
from jarvis_core.tools.router import ToolExecutionCoordinator


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequiredArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


class SpoofArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side_effect_level: str | None = None
    execution_boundary: str | None = None


class SecretArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str


class FakeTool:
    def __init__(
        self,
        *,
        name: str = "test.fake",
        side_effect_level: SideEffectLevel = SideEffectLevel.READ,
        execution_boundary: ExecutionBoundary = ExecutionBoundary.CORE,
        argument_model: type[BaseModel] = NoArgs,
        result: ToolResult | None = None,
        fail: bool = False,
    ) -> None:
        self._descriptor = ToolDescriptor(
            name=name,
            description=f"{name} test tool.",
            side_effect_level=side_effect_level,
            execution_boundary=execution_boundary,
            input_schema=argument_model.model_json_schema(),
        )
        self._argument_model = argument_model
        self._result = result or ToolResult(success=True, data={"ok": True})
        self._fail = fail
        self.executions = 0
        self.last_arguments: BaseModel | None = None
        self.last_context: ToolExecutionContext | None = None

    @property
    def descriptor(self) -> ToolDescriptor:
        return self._descriptor

    @property
    def argument_model(self) -> type[BaseModel]:
        return self._argument_model

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        self.executions += 1
        self.last_arguments = arguments
        self.last_context = context
        if self._fail:
            raise RuntimeError("raw tool failure")
        return self._result


class RecordingSentinel:
    def __init__(
        self,
        *,
        action: AuthorizationAction = AuthorizationAction.ALLOW,
        reason: str = "recorded decision",
        fail: bool = False,
    ) -> None:
        self.action = action
        self.reason = reason
        self.fail = fail
        self.requests: list[AuthorizationRequest] = []

    async def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("raw sentinel failure")
        return AuthorizationDecision(action=self.action, reason=self.reason)


def registry_with(tool: FakeTool | RuntimeInfoTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)
    return registry


def build_tool_client(settings: Settings, tool: FakeTool) -> TestClient:
    return TestClient(
        create_app(
            settings,
            tool_registry=registry_with(tool),
            sentinel=DefaultSentinelPolicy(),
        )
    )


def test_tool_registry_registers_and_resolves_exact_tool_name() -> None:
    tool = FakeTool(name="system.test")
    registry = ToolRegistry()

    registry.register(tool)

    assert registry.resolve("system.test").tool is tool
    assert registry.descriptor("system.test").name == "system.test"


def test_tool_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(FakeTool(name="system.test"))

    with pytest.raises(ToolExecutionError) as exc_info:
        registry.register(FakeTool(name="system.test"))

    assert exc_info.value.code is ToolErrorCode.DUPLICATE_TOOL
    assert exc_info.value.tool_name == "system.test"


def test_tool_registry_returns_stable_unknown_tool_error() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolExecutionError) as exc_info:
        registry.resolve("missing.tool")

    assert exc_info.value.code is ToolErrorCode.TOOL_NOT_FOUND
    assert exc_info.value.safe_message == "Tool was not found."
    assert exc_info.value.tool_name == "missing.tool"


def test_tool_registry_exposes_trusted_descriptor_copies() -> None:
    registry = ToolRegistry()
    registry.register(
        FakeTool(
            name="system.test",
            side_effect_level=SideEffectLevel.READ,
            execution_boundary=ExecutionBoundary.CORE,
        )
    )

    descriptor = registry.descriptor("system.test")
    descriptor.side_effect_level = SideEffectLevel.DANGEROUS
    descriptor.execution_boundary = ExecutionBoundary.EXTERNAL_SERVICE

    trusted_descriptor = registry.descriptor("system.test")
    assert trusted_descriptor.side_effect_level is SideEffectLevel.READ
    assert trusted_descriptor.execution_boundary is ExecutionBoundary.CORE


@pytest.mark.anyio
async def test_runtime_info_tool_executes_and_returns_safe_metadata() -> None:
    tool = RuntimeInfoTool()
    coordinator = ToolExecutionCoordinator(
        registry_with(tool),
        DefaultSentinelPolicy(),
    )

    outcome = await coordinator.execute(
        ToolRequest(tool_name="system.runtime_info", arguments={})
    )

    assert outcome.tool_name == "system.runtime_info"
    assert outcome.sentinel_decision.action is AuthorizationAction.ALLOW
    assert outcome.result.success is True
    assert outcome.result.data["platform_family"] == (platform.system() or "Unknown")
    assert outcome.result.data["python_version"] == platform.python_version()
    assert outcome.result.data["jarvis_version"] == "0.4.0"
    assert set(outcome.result.data) == {
        "platform_family",
        "python_version",
        "jarvis_version",
    }


def test_runtime_info_descriptor_is_read_and_core() -> None:
    descriptor = RuntimeInfoTool().descriptor

    assert descriptor.side_effect_level is SideEffectLevel.READ
    assert descriptor.execution_boundary is ExecutionBoundary.CORE


@pytest.mark.anyio
async def test_runtime_info_response_excludes_sensitive_system_metadata() -> None:
    tool = RuntimeInfoTool()
    coordinator = ToolExecutionCoordinator(registry_with(tool), DefaultSentinelPolicy())

    outcome = await coordinator.execute(
        ToolRequest(tool_name="system.runtime_info", arguments={})
    )

    rendered = str(outcome.result.data)
    assert getpass.getuser() not in rendered
    assert socket.gethostname() not in rendered
    assert "environment" not in rendered.lower()
    assert "process" not in rendered.lower()
    assert "secret" not in rendered.lower()
    assert "serial" not in rendered.lower()


@pytest.mark.anyio
async def test_invalid_arguments_do_not_call_sentinel_or_execute_tool() -> None:
    tool = FakeTool(argument_model=RequiredArgs)
    sentinel = RecordingSentinel()
    coordinator = ToolExecutionCoordinator(registry_with(tool), sentinel)

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert exc_info.value.code is ToolErrorCode.INVALID_ARGUMENTS
    assert sentinel.requests == []
    assert tool.executions == 0


@pytest.mark.anyio
async def test_sentinel_receives_trusted_registered_metadata_not_caller_spoofs() -> None:
    tool = FakeTool(
        side_effect_level=SideEffectLevel.READ,
        execution_boundary=ExecutionBoundary.CORE,
        argument_model=SpoofArgs,
    )
    sentinel = RecordingSentinel()
    coordinator = ToolExecutionCoordinator(registry_with(tool), sentinel)

    await coordinator.execute(
        ToolRequest(
            tool_name="test.fake",
            arguments={
                "side_effect_level": "dangerous",
                "execution_boundary": "external_service",
            },
            correlation_id="trusted-metadata",
        )
    )

    assert len(sentinel.requests) == 1
    request = sentinel.requests[0]
    assert request.side_effect_level is SideEffectLevel.READ
    assert request.execution_boundary is ExecutionBoundary.CORE
    assert request.correlation_id == "trusted-metadata"
    assert tool.executions == 1


@pytest.mark.anyio
async def test_default_sentinel_policy_allows_none_and_read_tools() -> None:
    policy = DefaultSentinelPolicy()

    for side_effect_level in (SideEffectLevel.NONE, SideEffectLevel.READ):
        decision = await policy.authorize(
            AuthorizationRequest(
                action="test.tool",
                resource="test.tool",
                side_effect_level=side_effect_level,
                execution_boundary=ExecutionBoundary.CORE,
            )
        )
        assert decision.action is AuthorizationAction.ALLOW


@pytest.mark.anyio
async def test_default_sentinel_policy_asks_for_write_tools() -> None:
    policy = DefaultSentinelPolicy()

    decision = await policy.authorize(
        AuthorizationRequest(
            action="test.tool",
            resource="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
        )
    )

    assert decision.action is AuthorizationAction.ASK


@pytest.mark.anyio
async def test_default_sentinel_policy_denies_dangerous_tools() -> None:
    policy = DefaultSentinelPolicy()

    decision = await policy.authorize(
        AuthorizationRequest(
            action="test.tool",
            resource="test.tool",
            side_effect_level=SideEffectLevel.DANGEROUS,
            execution_boundary=ExecutionBoundary.CORE,
        )
    )

    assert decision.action is AuthorizationAction.DENY


@pytest.mark.anyio
async def test_ask_does_not_execute_tool() -> None:
    tool = FakeTool(side_effect_level=SideEffectLevel.WRITE)
    coordinator = ToolExecutionCoordinator(registry_with(tool), DefaultSentinelPolicy())

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert exc_info.value.code is ToolErrorCode.APPROVAL_REQUIRED
    assert tool.executions == 0


@pytest.mark.anyio
async def test_deny_does_not_execute_tool() -> None:
    tool = FakeTool(side_effect_level=SideEffectLevel.DANGEROUS)
    coordinator = ToolExecutionCoordinator(registry_with(tool), DefaultSentinelPolicy())

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert exc_info.value.code is ToolErrorCode.DENIED
    assert tool.executions == 0


@pytest.mark.anyio
async def test_tool_exception_becomes_normalized_failure() -> None:
    tool = FakeTool(fail=True)
    coordinator = ToolExecutionCoordinator(registry_with(tool), RecordingSentinel())

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert exc_info.value.code is ToolErrorCode.EXECUTION_FAILED
    assert exc_info.value.safe_message == "Tool execution failed."


@pytest.mark.anyio
async def test_sentinel_exception_becomes_normalized_failure() -> None:
    tool = FakeTool()
    coordinator = ToolExecutionCoordinator(
        registry_with(tool),
        RecordingSentinel(fail=True),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert exc_info.value.code is ToolErrorCode.SENTINEL_AUTHORIZATION_FAILED
    assert exc_info.value.safe_message == "Sentinel authorization failed."
    assert tool.executions == 0


@pytest.mark.anyio
async def test_correlation_id_preserved_when_supplied_and_generated_when_omitted() -> None:
    sentinel = RecordingSentinel()
    coordinator = ToolExecutionCoordinator(registry_with(FakeTool()), sentinel)

    supplied = await coordinator.execute(
        ToolRequest(tool_name="test.fake", arguments={}, correlation_id="manual-tool")
    )
    generated = await coordinator.execute(ToolRequest(tool_name="test.fake", arguments={}))

    assert supplied.correlation_id == "manual-tool"
    assert sentinel.requests[0].correlation_id == "manual-tool"
    assert UUID(generated.correlation_id)
    assert sentinel.requests[1].correlation_id == generated.correlation_id


@pytest.mark.anyio
async def test_tool_logs_omit_raw_arguments_and_results(tmp_path, caplog) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="INFO")
    tool = FakeTool(
        argument_model=SecretArgs,
        result=ToolResult(success=True, data={"result": "secret-result"}),
    )
    coordinator = ToolExecutionCoordinator(registry_with(tool), RecordingSentinel())
    caplog.set_level("INFO", logger="jarvis_core.tools.router")

    await coordinator.execute(
        ToolRequest(
            tool_name="test.fake",
            arguments={"secret": "secret-input"},
            correlation_id="safe-log",
        )
    )

    assert settings.log_level == "INFO"
    assert "secret-input" not in caplog.text
    assert "secret-result" not in caplog.text
    assert any(record.__dict__.get("correlation_id") == "safe-log" for record in caplog.records)
    assert any(
        record.__dict__.get("sentinel_decision") == AuthorizationAction.ALLOW.value
        for record in caplog.records
    )


def test_tools_execute_api_success_for_runtime_info(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        json={"tool_name": "system.runtime_info", "arguments": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["tool_name"] == "system.runtime_info"
    assert UUID(body["correlation_id"])
    assert body["sentinel"]["decision"] == "allow"
    assert body["result"]["success"] is True
    assert set(body["result"]["data"]) == {
        "platform_family",
        "python_version",
        "jarvis_version",
    }


def test_tools_execute_api_preserves_supplied_correlation_id(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        json={
            "tool_name": "system.runtime_info",
            "arguments": {},
            "correlation_id": "manual-tool-correlation",
        },
    )

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "manual-tool-correlation"


def test_tools_execute_api_unknown_tool_error(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        json={
            "tool_name": "missing.tool",
            "arguments": {},
            "correlation_id": "missing-tool",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "tool_not_found",
            "message": "Tool was not found.",
            "correlation_id": "missing-tool",
            "tool_name": "missing.tool",
        },
    }


def test_tools_execute_api_invalid_arguments_error(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        json={
            "tool_name": "system.runtime_info",
            "arguments": {"unexpected": "value"},
            "correlation_id": "bad-tool-args",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "tool_invalid_arguments",
            "message": "Tool arguments are invalid.",
            "correlation_id": "bad-tool-args",
            "tool_name": "system.runtime_info",
        },
    }


def test_tools_execute_api_rejects_top_level_metadata_spoof(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        json={
            "tool_name": "system.runtime_info",
            "arguments": {},
            "side_effect_level": "none",
            "execution_boundary": "external_service",
        },
    )

    assert response.status_code == 422


def test_tools_execute_api_approval_required_uses_http_409(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")
    tool = FakeTool(name="test.write", side_effect_level=SideEffectLevel.WRITE)

    with build_tool_client(settings, tool) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "test.write",
                "arguments": {},
                "correlation_id": "write-approval",
            },
        )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "tool_approval_required",
        "message": "Tool approval is required.",
        "correlation_id": "write-approval",
        "tool_name": "test.write",
    }
    assert tool.executions == 0


def test_tools_execute_api_denied_uses_http_403(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")
    tool = FakeTool(name="test.dangerous", side_effect_level=SideEffectLevel.DANGEROUS)

    with build_tool_client(settings, tool) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "test.dangerous",
                "arguments": {},
                "correlation_id": "danger-denied",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "tool_denied",
        "message": "Tool execution was denied by Sentinel.",
        "correlation_id": "danger-denied",
        "tool_name": "test.dangerous",
    }
    assert tool.executions == 0
