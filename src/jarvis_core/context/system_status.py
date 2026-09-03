"""Safe local system-status collection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import psutil
from pydantic import BaseModel, ConfigDict, Field

CPU_SAMPLE_INTERVAL_SECONDS = 0.1


class SystemStatusCollectionError(Exception):
    """Raised when safe local system-status collection fails."""


class CPUStatus(BaseModel):
    """Safe CPU status fields."""

    model_config = ConfigDict(extra="forbid")

    usage_percent: float = Field(ge=0.0, le=100.0)
    logical_core_count: int = Field(ge=1)
    physical_core_count: int | None = Field(default=None, ge=1)


class MemoryStatus(BaseModel):
    """Safe memory status fields."""

    model_config = ConfigDict(extra="forbid")

    total_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0.0, le=100.0)


class PowerStatus(BaseModel):
    """Safe power status fields."""

    model_config = ConfigDict(extra="forbid")

    battery_present: bool
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    plugged_in: bool | None = None


class SystemRuntimeStatus(BaseModel):
    """Safe runtime status fields."""

    model_config = ConfigDict(extra="forbid")

    uptime_seconds: float = Field(ge=0.0)


class LocalSystemStatus(BaseModel):
    """Safe local machine-health snapshot."""

    model_config = ConfigDict(extra="forbid")

    cpu: CPUStatus
    memory: MemoryStatus
    power: PowerStatus
    system: SystemRuntimeStatus


SystemStatusCollector = Callable[[], LocalSystemStatus]


def collect_system_status(
    sample_interval_seconds: float = CPU_SAMPLE_INTERVAL_SECONDS,
) -> LocalSystemStatus:
    """Collect a small safe snapshot of local machine health."""

    try:
        usage_percent = float(psutil.cpu_percent(interval=sample_interval_seconds))
        logical_core_count = psutil.cpu_count(logical=True)
        physical_core_count = psutil.cpu_count(logical=False)
        memory = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        uptime_seconds = max(0.0, time.time() - float(psutil.boot_time()))

        if logical_core_count is None:
            raise ValueError("logical CPU count is unavailable")

        power = PowerStatus(
            battery_present=battery is not None,
            battery_percent=None if battery is None else float(battery.percent),
            plugged_in=None if battery is None else battery.power_plugged,
        )

        return LocalSystemStatus(
            cpu=CPUStatus(
                usage_percent=usage_percent,
                logical_core_count=int(logical_core_count),
                physical_core_count=(
                    None if physical_core_count is None else int(physical_core_count)
                ),
            ),
            memory=MemoryStatus(
                total_bytes=int(memory.total),
                available_bytes=int(memory.available),
                used_bytes=int(memory.used),
                usage_percent=float(memory.percent),
            ),
            power=power,
            system=SystemRuntimeStatus(uptime_seconds=uptime_seconds),
        )
    except Exception as exc:
        raise SystemStatusCollectionError("System status collection failed.") from exc


async def collect_system_status_async(
    collector: SystemStatusCollector | None = None,
) -> LocalSystemStatus:
    """Collect system status without blocking the async event loop."""

    resolved_collector = collector or collect_system_status
    return await asyncio.to_thread(resolved_collector)
