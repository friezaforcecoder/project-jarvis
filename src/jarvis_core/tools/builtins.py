"""Harmless built-in tools for JARVIS Core."""

from __future__ import annotations

import platform

from pydantic import BaseModel, ConfigDict

from jarvis_core import __version__
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


def create_builtin_tool_registry() -> ToolRegistry:
    """Build the default registry of harmless built-in tools."""

    registry = ToolRegistry()
    registry.register(RuntimeInfoTool())
    return registry
