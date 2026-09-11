"""Harmless built-in tools for JARVIS Core."""

from __future__ import annotations

import platform

from pydantic import BaseModel, ConfigDict

from jarvis_core import __version__
from jarvis_core.context import (
    ActiveWindowCollector,
    SystemStatusCollector,
    collect_active_window_async,
    collect_system_status_async,
)
from jarvis_core.tools.contracts import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolDescriptor,
    ToolExecutionContext,
    ToolResult,
)
from jarvis_core.tools.registry import ToolRegistry


class RuntimeInfoArguments(BaseModel):
    """Arguments for system.runtime_info."""

    model_config = ConfigDict(extra="forbid")


class SystemStatusArguments(BaseModel):
    """Arguments for system.status."""

    model_config = ConfigDict(extra="forbid")


class ActiveWindowArguments(BaseModel):
    """Arguments for context.active_window."""

    model_config = ConfigDict(extra="forbid")


class RuntimeInfoTool:
    """Return safe, broad JARVIS runtime metadata."""

    @property
    def descriptor(self) -> ToolDescriptor:
        """Return trusted runtime-info tool metadata."""

        return ToolDescriptor(
            name="system.runtime_info",
            description="Return safe JARVIS Core runtime metadata.",
            side_effect_level=SideEffectLevel.READ,
            execution_boundary=ExecutionBoundary.CORE,
            input_schema=RuntimeInfoArguments.model_json_schema(),
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        """Return the typed argument model."""

        return RuntimeInfoArguments

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Return safe runtime metadata."""

        return ToolResult(
            success=True,
            data={
                "platform_family": platform.system() or "Unknown",
                "python_version": platform.python_version(),
                "jarvis_version": __version__,
            },
        )


class SystemStatusTool:
    """Return a safe local machine-health snapshot."""

    def __init__(self, collector: SystemStatusCollector | None = None) -> None:
        self._collector = collector

    @property
    def descriptor(self) -> ToolDescriptor:
        """Return trusted system-status tool metadata."""

        return ToolDescriptor(
            name="system.status",
            description="Return safe local CPU, memory, power, and uptime status.",
            side_effect_level=SideEffectLevel.READ,
            execution_boundary=ExecutionBoundary.CORE,
            input_schema=SystemStatusArguments.model_json_schema(),
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        """Return the typed argument model."""

        return SystemStatusArguments

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Return safe local system-status metadata."""

        status = await collect_system_status_async(self._collector)
        return ToolResult(success=True, data=status.model_dump(mode="json"))


class ActiveWindowTool:
    """Return safe current foreground-window context."""

    def __init__(self, collector: ActiveWindowCollector | None = None) -> None:
        self._collector = collector

    @property
    def descriptor(self) -> ToolDescriptor:
        """Return trusted active-window tool metadata."""

        return ToolDescriptor(
            name="context.active_window",
            description="Return safe current foreground-window context.",
            side_effect_level=SideEffectLevel.READ,
            execution_boundary=ExecutionBoundary.CORE,
            input_schema=ActiveWindowArguments.model_json_schema(),
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        """Return the typed argument model."""

        return ActiveWindowArguments

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Return safe active-window context."""

        active_window = await collect_active_window_async(self._collector)
        return ToolResult(success=True, data=active_window.model_dump(mode="json"))


def create_builtin_tool_registry() -> ToolRegistry:
    """Build the default registry of harmless built-in tools."""

    registry = ToolRegistry()
    registry.register(RuntimeInfoTool())
    registry.register(SystemStatusTool())
    registry.register(ActiveWindowTool())
    return registry
