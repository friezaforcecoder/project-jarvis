"""Tool execution coordinator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from jarvis_core.sentinel.contracts import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
    Sentinel,
)
from jarvis_core.tools.contracts import (
    Tool,
    ToolDescriptor,
    ToolExecutionContext,
    ToolRequest,
    ToolResult,
)
from jarvis_core.tools.errors import ToolErrorCode, ToolExecutionError
from jarvis_core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolExecutionOutcome:
    """Normalized successful tool execution outcome."""

    tool_name: str
    correlation_id: str
    sentinel_decision: AuthorizationDecision
    result: ToolResult


class ToolExecutionCoordinator:
    """Coordinate registry lookup, validation, Sentinel, and tool execution."""

    def __init__(self, tool_registry: ToolRegistry, sentinel: Sentinel) -> None:
        self._tool_registry = tool_registry
        self._sentinel = sentinel

    async def execute(self, request: ToolRequest) -> ToolExecutionOutcome:
        """Execute one tool request through the safe Tool Fabric path."""

        correlation_id = request.correlation_id or str(uuid4())
        started_at = perf_counter()
        descriptor: ToolDescriptor | None = None
        decision: AuthorizationDecision | None = None
        logger.info(
            "tool_request_started",
            extra={
                "correlation_id": correlation_id,
                "tool_name": request.tool_name,
            },
        )

        try:
            registered = self._tool_registry.resolve(request.tool_name)
            descriptor = registered.descriptor
            arguments = self._validate_arguments(
                registered.tool.argument_model,
                request.arguments,
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
            authorization_request = AuthorizationRequest(
                action=descriptor.name,
                resource=descriptor.name,
                side_effect_level=descriptor.side_effect_level,
                execution_boundary=descriptor.execution_boundary,
                context={"tool_name": descriptor.name},
                correlation_id=correlation_id,
            )
            decision = await self._authorize(
                authorization_request,
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
            if decision.action is AuthorizationAction.ASK:
                raise ToolExecutionError(
                    ToolErrorCode.APPROVAL_REQUIRED,
                    "Tool approval is required.",
                    tool_name=descriptor.name,
                    correlation_id=correlation_id,
                )
            if decision.action is AuthorizationAction.DENY:
                raise ToolExecutionError(
                    ToolErrorCode.DENIED,
                    "Tool execution was denied by Sentinel.",
                    tool_name=descriptor.name,
                    correlation_id=correlation_id,
                )

            context = ToolExecutionContext(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
            result = await self._execute_tool(
                registered.tool,
                arguments,
                context,
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.info(
                "tool_request_succeeded",
                extra={
                    "correlation_id": correlation_id,
                    "tool_name": descriptor.name,
                    "sentinel_decision": decision.action.value,
                    "side_effect_level": descriptor.side_effect_level.value,
                    "execution_boundary": descriptor.execution_boundary.value,
                    "elapsed_ms": elapsed_ms,
                    "success": result.success,
                },
            )
            return ToolExecutionOutcome(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
                sentinel_decision=decision,
                result=result,
            )
        except ToolExecutionError as exc:
            if exc.correlation_id is None:
                exc.correlation_id = correlation_id
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            extra: dict[str, object] = {
                "correlation_id": exc.correlation_id,
                "tool_name": exc.tool_name or request.tool_name,
                "elapsed_ms": elapsed_ms,
                "error_code": exc.code.value,
                **exc.safe_metadata,
            }
            if descriptor is not None:
                extra["side_effect_level"] = descriptor.side_effect_level.value
                extra["execution_boundary"] = descriptor.execution_boundary.value
            if decision is not None:
                extra["sentinel_decision"] = decision.action.value
            logger.warning("tool_request_failed", extra=extra)
            raise

    def _validate_arguments(
        self,
        argument_model: type[BaseModel],
        arguments: dict[str, object],
        *,
        tool_name: str,
        correlation_id: str,
    ) -> BaseModel:
        try:
            return argument_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolExecutionError(
                ToolErrorCode.INVALID_ARGUMENTS,
                "Tool arguments are invalid.",
                tool_name=tool_name,
                correlation_id=correlation_id,
                safe_metadata={
                    "validation_error_count": len(exc.errors(include_input=False)),
                },
            ) from exc

    async def _authorize(
        self,
        request: AuthorizationRequest,
        *,
        tool_name: str,
        correlation_id: str,
    ) -> AuthorizationDecision:
        try:
            return await self._sentinel.authorize(request)
        except Exception as exc:
            raise ToolExecutionError(
                ToolErrorCode.SENTINEL_AUTHORIZATION_FAILED,
                "Sentinel authorization failed.",
                tool_name=tool_name,
                correlation_id=correlation_id,
            ) from exc

    async def _execute_tool(
        self,
        tool: Tool,
        arguments: BaseModel,
        context: ToolExecutionContext,
        *,
        tool_name: str,
        correlation_id: str,
    ) -> ToolResult:
        try:
            result = await tool.execute(arguments, context)
        except Exception as exc:
            raise ToolExecutionError(
                ToolErrorCode.EXECUTION_FAILED,
                "Tool execution failed.",
                tool_name=tool_name,
                correlation_id=correlation_id,
            ) from exc

        if not isinstance(result, ToolResult):
            raise ToolExecutionError(
                ToolErrorCode.INTERNAL_ERROR,
                "Tool execution returned an invalid result.",
                tool_name=tool_name,
                correlation_id=correlation_id,
            )
        return result
