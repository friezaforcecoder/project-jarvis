from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.context import (
    ActiveWindowCollectionError,
    ActiveWindowContext,
    ActiveWindowUnavailableReason,
    WindowsForegroundWindowSnapshot,
    active_window_context_from_windows_snapshot,
    collect_active_window,
    collect_active_window_async,
)
from jarvis_core.context import active_window as active_window_module
from jarvis_core.sentinel import AuthorizationAction, DefaultSentinelPolicy
from jarvis_core.tools import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolErrorCode,
    ToolExecutionError,
    ToolRegistry,
    ToolRequest,
)
from jarvis_core.tools.builtins import (
    ActiveWindowTool,
    RuntimeInfoTool,
    SystemStatusTool,
    create_builtin_tool_registry,
)
from jarvis_core.tools.router import ToolExecutionCoordinator


def sample_active_window(
    *,
    application_name: str | None = "Code",
    window_title: str | None = "ACTIVE_WINDOW_CONTEXT_V0.7.md - project-jarvis",
    reason: ActiveWindowUnavailableReason | None = None,
) -> ActiveWindowContext:
    return ActiveWindowContext(
        available=True,
        platform_family="Windows",
        application_name=application_name,
        window_title=window_title,
        reason=reason,
    )


def registry_with_active_window(active_window: ActiveWindowContext) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RuntimeInfoTool())
    registry.register(SystemStatusTool())
    registry.register(ActiveWindowTool(collector=lambda: active_window))
    return registry


def active_window_client(settings: Settings, active_window: ActiveWindowContext) -> TestClient:
    return TestClient(
        create_app(
            settings,
            tool_registry=registry_with_active_window(active_window),
            sentinel=DefaultSentinelPolicy(),
        )
    )


def test_default_registry_registers_active_window() -> None:
    registry = create_builtin_tool_registry()

    descriptor = registry.descriptor("context.active_window")

    assert descriptor.name == "context.active_window"
    assert descriptor.side_effect_level is SideEffectLevel.READ
    assert descriptor.execution_boundary is ExecutionBoundary.CORE
    assert registry.descriptor("system.runtime_info").name == "system.runtime_info"
    assert registry.descriptor("system.status").name == "system.status"


def test_active_window_argument_model_rejects_unexpected_arguments() -> None:
    with pytest.raises(ValidationError):
        ActiveWindowTool().argument_model.model_validate({"unexpected": "value"})


@pytest.mark.anyio
async def test_active_window_sentinel_allows_read_core_tool() -> None:
    coordinator = ToolExecutionCoordinator(
        registry_with_active_window(sample_active_window()),
        DefaultSentinelPolicy(),
    )

    outcome = await coordinator.execute(
        ToolRequest(
            tool_name="context.active_window",
            arguments={},
            correlation_id="active-window-read",
        )
    )

    assert outcome.tool_name == "context.active_window"
    assert outcome.correlation_id == "active-window-read"
    assert outcome.sentinel_decision.action is AuthorizationAction.ALLOW
    assert outcome.result.success is True


def test_active_window_api_returns_stable_result_shape(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")
    expected = sample_active_window()

    with active_window_client(settings, expected) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "context.active_window",
                "arguments": {},
                "correlation_id": "manual-active-window",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["tool_name"] == "context.active_window"
    assert body["correlation_id"] == "manual-active-window"
    assert body["sentinel"]["decision"] == "allow"
    assert body["result"] == {
        "success": True,
        "data": expected.model_dump(mode="json"),
        "error": None,
    }


def test_active_window_api_generates_correlation_id_when_omitted(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with active_window_client(settings, sample_active_window()) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "context.active_window", "arguments": {}},
        )

    assert response.status_code == 200
    UUID(response.json()["correlation_id"])


def test_active_window_rejects_unexpected_arguments_before_collection(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    def collector() -> ActiveWindowContext:
        raise AssertionError("collector should not run")

    registry = ToolRegistry()
    registry.register(ActiveWindowTool(collector=collector))

    with TestClient(
        create_app(
            settings,
            tool_registry=registry,
            sentinel=DefaultSentinelPolicy(),
        )
    ) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "context.active_window",
                "arguments": {"unexpected": "value"},
                "correlation_id": "bad-active-window-args",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "tool_invalid_arguments",
        "message": "Tool arguments are invalid.",
        "correlation_id": "bad-active-window-args",
        "tool_name": "context.active_window",
    }


def test_active_window_result_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ActiveWindowContext.model_validate(
            {
                "available": True,
                "platform_family": "Windows",
                "application_name": "Code",
                "window_title": "project",
                "reason": None,
                "pid": 1234,
            }
        )


def test_windows_snapshot_maps_to_available_public_contract() -> None:
    context = active_window_context_from_windows_snapshot(
        WindowsForegroundWindowSnapshot(
            has_foreground_window=True,
            application_name="Code",
            window_title="project-jarvis",
        )
    )

    assert context == ActiveWindowContext(
        available=True,
        platform_family="Windows",
        application_name="Code",
        window_title="project-jarvis",
        reason=None,
    )


def test_missing_foreground_window_maps_to_no_active_window() -> None:
    context = active_window_context_from_windows_snapshot(
        WindowsForegroundWindowSnapshot(has_foreground_window=False)
    )

    assert context == ActiveWindowContext(
        available=False,
        platform_family="Windows",
        application_name=None,
        window_title=None,
        reason=ActiveWindowUnavailableReason.NO_ACTIVE_WINDOW,
    )


def test_missing_title_maps_to_title_unavailable() -> None:
    context = active_window_context_from_windows_snapshot(
        WindowsForegroundWindowSnapshot(
            has_foreground_window=True,
            application_name="Code",
            window_title=None,
        )
    )

    assert context.available is True
    assert context.application_name == "Code"
    assert context.window_title is None
    assert context.reason is ActiveWindowUnavailableReason.WINDOW_TITLE_UNAVAILABLE


def test_missing_application_name_maps_to_application_name_unavailable() -> None:
    context = active_window_context_from_windows_snapshot(
        WindowsForegroundWindowSnapshot(
            has_foreground_window=True,
            application_name=None,
            window_title="Untitled - Notepad",
        )
    )

    assert context.available is True
    assert context.application_name is None
    assert context.window_title == "Untitled - Notepad"
    assert context.reason is ActiveWindowUnavailableReason.APPLICATION_NAME_UNAVAILABLE


def test_non_windows_behavior_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(active_window_module.platform, "system", lambda: "Linux")

    context = collect_active_window()

    assert context == ActiveWindowContext(
        available=False,
        platform_family="Linux",
        application_name=None,
        window_title=None,
        reason=ActiveWindowUnavailableReason.UNSUPPORTED_PLATFORM,
    )


def test_windows_native_application_name_is_sanitized_and_handle_is_closed() -> None:
    closed_handles: list[object] = []

    class FakeDWORD:
        def __init__(self, value: int = 0) -> None:
            self.value = value

    class FakeCtypes:
        @staticmethod
        def byref(value: object) -> object:
            return value

        @staticmethod
        def create_unicode_buffer(size: int) -> SimpleNamespace:
            return SimpleNamespace(value="")

    class FakeWinTypes:
        DWORD = FakeDWORD

    class FakeUser32:
        @staticmethod
        def GetWindowThreadProcessId(hwnd: object, process_id: FakeDWORD) -> int:
            process_id.value = 4242
            return 1

    class FakeKernel32:
        @staticmethod
        def OpenProcess(access: int, inherit: bool, process_id: int) -> object:
            return "PROCESS_HANDLE"

        @staticmethod
        def QueryFullProcessImageNameW(
            process: object,
            flags: int,
            buffer: SimpleNamespace,
            size: FakeDWORD,
        ) -> bool:
            buffer.value = r"C:\Program Files\Microsoft VS Code\Code.exe"
            return True

        @staticmethod
        def CloseHandle(process: object) -> bool:
            closed_handles.append(process)
            return True

    application_name = active_window_module._read_application_name(
        FakeCtypes,
        FakeWinTypes,
        FakeUser32,
        FakeKernel32,
        "HWND",
    )

    assert application_name == "Code"
    assert closed_handles == ["PROCESS_HANDLE"]


@pytest.mark.anyio
async def test_active_window_collector_failure_becomes_tool_execution_failed() -> None:
    def collector() -> ActiveWindowContext:
        raise RuntimeError("raw native failure with C:\\Users\\person\\secret")

    registry = ToolRegistry()
    registry.register(ActiveWindowTool(collector=collector))
    coordinator = ToolExecutionCoordinator(registry, DefaultSentinelPolicy())

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(
            ToolRequest(
                tool_name="context.active_window",
                arguments={},
                correlation_id="active-window-failure",
            )
        )

    assert exc_info.value.code is ToolErrorCode.EXECUTION_FAILED
    assert exc_info.value.safe_message == "Tool execution failed."
    assert exc_info.value.correlation_id == "active-window-failure"


def test_active_window_api_failure_is_normalized_and_safe(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    def collector() -> ActiveWindowContext:
        raise RuntimeError("C:\\Users\\person\\secret-active-window-detail")

    registry = ToolRegistry()
    registry.register(ActiveWindowTool(collector=collector))

    with TestClient(
        create_app(
            settings,
            tool_registry=registry,
            sentinel=DefaultSentinelPolicy(),
        )
    ) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "context.active_window",
                "arguments": {},
                "correlation_id": "active-window-api-failure",
            },
        )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "tool_execution_failed",
        "message": "Tool execution failed.",
        "correlation_id": "active-window-api-failure",
        "tool_name": "context.active_window",
    }
    assert "secret-active-window-detail" not in response.text
    assert "C:\\Users" not in response.text


@pytest.mark.anyio
async def test_active_window_logs_omit_sensitive_payloads(caplog) -> None:
    active_window = sample_active_window(
        application_name="SecretBrowser",
        window_title="Sensitive Document Title",
    )
    coordinator = ToolExecutionCoordinator(
        registry_with_active_window(active_window),
        DefaultSentinelPolicy(),
    )
    caplog.set_level("INFO", logger="jarvis_core.tools.router")

    await coordinator.execute(
        ToolRequest(
            tool_name="context.active_window",
            arguments={},
            correlation_id="active-window-safe-log",
        )
    )

    assert "SecretBrowser" not in caplog.text
    assert "Sensitive Document Title" not in caplog.text
    assert any(
        record.__dict__.get("tool_name") == "context.active_window"
        for record in caplog.records
    )
    assert any(
        record.__dict__.get("sentinel_decision") == AuthorizationAction.ALLOW.value
        for record in caplog.records
    )


def test_active_window_result_excludes_prohibited_fields(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with active_window_client(settings, sample_active_window()) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "context.active_window", "arguments": {}},
        )

    data = response.json()["result"]["data"]
    assert set(data) == {
        "available",
        "platform_family",
        "application_name",
        "window_title",
        "reason",
    }
    rendered = json.dumps(data).lower()
    prohibited_terms = {
        "pid",
        "handle",
        "path",
        "command",
        "process",
        "username",
        "environment",
        "url",
        "clipboard",
        "screenshot",
        "secret",
    }
    for term in prohibited_terms:
        assert term not in rendered


@pytest.mark.anyio
async def test_collect_active_window_async_uses_to_thread(monkeypatch) -> None:
    active_window = sample_active_window()
    called: dict[str, bool] = {}

    async def to_thread(function):
        called["used"] = True
        return function()

    monkeypatch.setattr(active_window_module.asyncio, "to_thread", to_thread)

    result = await collect_active_window_async(lambda: active_window)

    assert called == {"used": True}
    assert result is active_window
