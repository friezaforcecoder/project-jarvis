from __future__ import annotations

import getpass
import json
import re
import socket
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.context import (
    CPUStatus,
    LocalSystemStatus,
    MemoryStatus,
    PowerStatus,
    SystemRuntimeStatus,
    SystemStatusCollectionError,
    collect_system_status,
    collect_system_status_async,
)
from jarvis_core.context import system_status as system_status_module
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
    RuntimeInfoTool,
    SystemStatusTool,
    create_builtin_tool_registry,
)
from jarvis_core.tools.router import ToolExecutionCoordinator


def sample_status(
    *,
    battery_present: bool = True,
    physical_core_count: int | None = 8,
) -> LocalSystemStatus:
    return LocalSystemStatus(
        cpu=CPUStatus(
            usage_percent=12.5,
            logical_core_count=16,
            physical_core_count=physical_core_count,
        ),
        memory=MemoryStatus(
            total_bytes=34_359_738_368,
            available_bytes=20_000_000_000,
            used_bytes=14_359_738_368,
            usage_percent=41.8,
        ),
        power=PowerStatus(
            battery_present=battery_present,
            battery_percent=88.0 if battery_present else None,
            plugged_in=True if battery_present else None,
        ),
        system=SystemRuntimeStatus(uptime_seconds=123_456.0),
    )


def registry_with_system_status(status: LocalSystemStatus) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RuntimeInfoTool())
    registry.register(SystemStatusTool(collector=lambda: status))
    return registry


def status_client(settings: Settings, status: LocalSystemStatus) -> TestClient:
    return TestClient(
        create_app(
            settings,
            tool_registry=registry_with_system_status(status),
            sentinel=DefaultSentinelPolicy(),
        )
    )


def test_default_registry_registers_system_status() -> None:
    registry = create_builtin_tool_registry()

    descriptor = registry.descriptor("system.status")

    assert descriptor.name == "system.status"
    assert descriptor.side_effect_level is SideEffectLevel.READ
    assert descriptor.execution_boundary is ExecutionBoundary.CORE
    assert registry.descriptor("system.runtime_info").name == "system.runtime_info"


def test_system_status_argument_model_rejects_unexpected_arguments() -> None:
    with pytest.raises(ValidationError):
        SystemStatusTool().argument_model.model_validate({"unexpected": "value"})


@pytest.mark.anyio
async def test_system_status_sentinel_allows_read_core_tool() -> None:
    coordinator = ToolExecutionCoordinator(
        registry_with_system_status(sample_status()),
        DefaultSentinelPolicy(),
    )

    outcome = await coordinator.execute(
        ToolRequest(
            tool_name="system.status",
            arguments={},
            correlation_id="status-read",
        )
    )

    assert outcome.tool_name == "system.status"
    assert outcome.correlation_id == "status-read"
    assert outcome.sentinel_decision.action is AuthorizationAction.ALLOW
    assert outcome.result.success is True


def test_system_status_api_returns_cpu_memory_power_and_system_sections(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")
    expected = sample_status()

    with status_client(settings, expected) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "system.status",
                "arguments": {},
                "correlation_id": "manual-system-status",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["tool_name"] == "system.status"
    assert body["correlation_id"] == "manual-system-status"
    assert body["sentinel"]["decision"] == "allow"
    assert body["result"] == {
        "success": True,
        "data": expected.model_dump(mode="json"),
        "error": None,
    }


def test_system_status_api_generates_correlation_id_when_omitted(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with status_client(settings, sample_status()) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "system.status", "arguments": {}},
        )

    assert response.status_code == 200
    UUID(response.json()["correlation_id"])


def test_system_status_rejects_unexpected_arguments_before_collection(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    def collector() -> LocalSystemStatus:
        raise AssertionError("collector should not run")

    registry = ToolRegistry()
    registry.register(SystemStatusTool(collector=collector))

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
                "tool_name": "system.status",
                "arguments": {"unexpected": "value"},
                "correlation_id": "bad-status-args",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "tool_invalid_arguments",
        "message": "Tool arguments are invalid.",
        "correlation_id": "bad-status-args",
        "tool_name": "system.status",
    }


def test_system_status_power_section_handles_no_battery(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with status_client(settings, sample_status(battery_present=False)) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "system.status", "arguments": {}},
        )

    power = response.json()["result"]["data"]["power"]
    assert power == {
        "battery_present": False,
        "battery_percent": None,
        "plugged_in": None,
    }


def test_system_status_physical_core_count_can_be_null(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with status_client(settings, sample_status(physical_core_count=None)) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "system.status", "arguments": {}},
        )

    assert response.json()["result"]["data"]["cpu"]["physical_core_count"] is None


def test_system_status_result_has_only_approved_fields(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with status_client(settings, sample_status()) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "system.status", "arguments": {}},
        )

    data = response.json()["result"]["data"]
    assert set(data) == {"cpu", "memory", "power", "system"}
    assert set(data["cpu"]) == {
        "usage_percent",
        "logical_core_count",
        "physical_core_count",
    }
    assert set(data["memory"]) == {
        "total_bytes",
        "available_bytes",
        "used_bytes",
        "usage_percent",
    }
    assert set(data["power"]) == {
        "battery_present",
        "battery_percent",
        "plugged_in",
    }
    assert set(data["system"]) == {"uptime_seconds"}


def test_system_status_result_excludes_sensitive_information(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    with status_client(settings, sample_status()) as client:
        response = client.post(
            "/v1/tools/execute",
            json={"tool_name": "system.status", "arguments": {}},
        )

    rendered = json.dumps(response.json()["result"]["data"]).lower()
    username = getpass.getuser().lower()
    hostname = socket.gethostname().lower()
    prohibited_terms = {
        "username",
        "hostname",
        "ip",
        "mac",
        "network",
        "interface",
        "environment",
        "env",
        "process",
        "command",
        "cmdline",
        "file",
        "path",
        "drive",
        "mount",
        "serial",
        "device",
        "motherboard",
        "account",
        "secret",
        "clipboard",
        "window",
        "screenshot",
        "application",
    }

    assert username not in rendered
    assert hostname not in rendered
    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", rendered)
    assert not re.search(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", rendered)
    for term in prohibited_terms:
        assert term not in rendered


@pytest.mark.anyio
async def test_system_status_collector_failure_becomes_tool_execution_failed() -> None:
    def collector() -> LocalSystemStatus:
        raise RuntimeError("raw psutil failure with local detail")

    registry = ToolRegistry()
    registry.register(SystemStatusTool(collector=collector))
    coordinator = ToolExecutionCoordinator(registry, DefaultSentinelPolicy())

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(
            ToolRequest(
                tool_name="system.status",
                arguments={},
                correlation_id="status-failure",
            )
        )

    assert exc_info.value.code is ToolErrorCode.EXECUTION_FAILED
    assert exc_info.value.safe_message == "Tool execution failed."
    assert exc_info.value.correlation_id == "status-failure"


def test_system_status_api_failure_is_normalized_and_safe(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3", log_level="WARNING")

    def collector() -> LocalSystemStatus:
        raise RuntimeError("C:\\Users\\person\\secret-device-detail")

    registry = ToolRegistry()
    registry.register(SystemStatusTool(collector=collector))

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
                "tool_name": "system.status",
                "arguments": {},
                "correlation_id": "status-api-failure",
            },
        )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "tool_execution_failed",
        "message": "Tool execution failed.",
        "correlation_id": "status-api-failure",
        "tool_name": "system.status",
    }
    assert "secret-device-detail" not in response.text
    assert "C:\\Users" not in response.text


@pytest.mark.anyio
async def test_system_status_logs_omit_raw_metric_payloads(caplog) -> None:
    status = sample_status()
    coordinator = ToolExecutionCoordinator(
        registry_with_system_status(status),
        DefaultSentinelPolicy(),
    )
    caplog.set_level("INFO", logger="jarvis_core.tools.router")

    await coordinator.execute(
        ToolRequest(
            tool_name="system.status",
            arguments={},
            correlation_id="status-safe-log",
        )
    )

    assert "34359738368" not in caplog.text
    assert "123456" not in caplog.text
    assert any(
        record.__dict__.get("tool_name") == "system.status"
        for record in caplog.records
    )
    assert any(
        record.__dict__.get("sentinel_decision") == AuthorizationAction.ALLOW.value
        for record in caplog.records
    )


def test_collect_system_status_maps_psutil_values(monkeypatch) -> None:
    captured: dict[str, float] = {}

    def cpu_percent(interval: float) -> float:
        captured["interval"] = interval
        return 22.5

    def cpu_count(*, logical: bool) -> int:
        return 16 if logical else 8

    monkeypatch.setattr(system_status_module.psutil, "cpu_percent", cpu_percent)
    monkeypatch.setattr(system_status_module.psutil, "cpu_count", cpu_count)
    monkeypatch.setattr(
        system_status_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            total=1000,
            available=400,
            used=600,
            percent=60.0,
        ),
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "sensors_battery",
        lambda: SimpleNamespace(percent=70.0, power_plugged=True),
    )
    monkeypatch.setattr(system_status_module.psutil, "boot_time", lambda: 900.0)
    monkeypatch.setattr(system_status_module.time, "time", lambda: 1025.0)

    status = collect_system_status()

    assert captured["interval"] == system_status_module.CPU_SAMPLE_INTERVAL_SECONDS
    assert status.cpu.usage_percent == 22.5
    assert status.cpu.logical_core_count == 16
    assert status.cpu.physical_core_count == 8
    assert status.memory.total_bytes == 1000
    assert status.memory.available_bytes == 400
    assert status.memory.used_bytes == 600
    assert status.memory.usage_percent == 60.0
    assert status.power.battery_present is True
    assert status.power.battery_percent == 70.0
    assert status.power.plugged_in is True
    assert status.system.uptime_seconds == 125.0


def test_collect_system_status_handles_no_battery_and_no_physical_core_count(
    monkeypatch,
) -> None:
    monkeypatch.setattr(system_status_module.psutil, "cpu_percent", lambda interval: 5.0)
    monkeypatch.setattr(
        system_status_module.psutil,
        "cpu_count",
        lambda *, logical: 4 if logical else None,
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            total=1000,
            available=500,
            used=500,
            percent=50.0,
        ),
    )
    monkeypatch.setattr(system_status_module.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(system_status_module.psutil, "boot_time", lambda: 950.0)
    monkeypatch.setattr(system_status_module.time, "time", lambda: 1000.0)

    status = collect_system_status()

    assert status.cpu.physical_core_count is None
    assert status.power.battery_present is False
    assert status.power.battery_percent is None
    assert status.power.plugged_in is None
    assert status.system.uptime_seconds == 50.0


def test_collect_system_status_normalizes_psutil_failures(monkeypatch) -> None:
    def cpu_percent(interval: float) -> float:
        raise RuntimeError("raw psutil failure")

    monkeypatch.setattr(system_status_module.psutil, "cpu_percent", cpu_percent)

    with pytest.raises(SystemStatusCollectionError) as exc_info:
        collect_system_status()

    assert str(exc_info.value) == "System status collection failed."


@pytest.mark.anyio
async def test_collect_system_status_async_uses_to_thread(monkeypatch) -> None:
    status = sample_status()
    called: dict[str, bool] = {}

    async def to_thread(function):
        called["used"] = True
        return function()

    monkeypatch.setattr(system_status_module.asyncio, "to_thread", to_thread)

    result = await collect_system_status_async(lambda: status)

    assert called == {"used": True}
    assert result is status
