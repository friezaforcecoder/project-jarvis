"""Registry for trusted JARVIS tool implementations."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_core.tools.contracts import Tool, ToolDescriptor
from jarvis_core.tools.errors import ToolErrorCode, ToolExecutionError


@dataclass(frozen=True)
class RegisteredTool:
    """A registered tool with trusted descriptor metadata."""

    tool: Tool
    descriptor: ToolDescriptor


class ToolRegistry:
    """Register and resolve tools by exact stable name."""

    def __init__(self) -> None:
        self._entries: dict[str, RegisteredTool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool implementation by its descriptor name."""

        descriptor = tool.descriptor.model_copy(deep=True)
        if descriptor.name in self._entries:
            raise ToolExecutionError(
                ToolErrorCode.DUPLICATE_TOOL,
                "Tool is already registered.",
                tool_name=descriptor.name,
            )

        self._entries[descriptor.name] = RegisteredTool(
            tool=tool,
            descriptor=descriptor,
        )

    def resolve(self, tool_name: str) -> RegisteredTool:
        """Resolve one registered tool by exact name."""

        entry = self._entries.get(tool_name)
        if entry is None:
            raise ToolExecutionError(
                ToolErrorCode.TOOL_NOT_FOUND,
                "Tool was not found.",
                tool_name=tool_name,
            )

        return RegisteredTool(
            tool=entry.tool,
            descriptor=entry.descriptor.model_copy(deep=True),
        )

    def descriptor(self, tool_name: str) -> ToolDescriptor:
        """Return the trusted descriptor for one registered tool."""

        return self.resolve(tool_name).descriptor

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        """Return all trusted descriptors in deterministic order."""

        return tuple(
            self._entries[name].descriptor.model_copy(deep=True)
            for name in sorted(self._entries)
        )
