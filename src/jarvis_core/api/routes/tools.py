"""Direct Tool Fabric execution endpoint."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from jarvis_core.sentinel import AuthorizationAction
from jarvis_core.tools import (
    ToolErrorCode,
    ToolExecutionError,
    ToolRequest,
    ToolResult,
)
from jarvis_core.tools.router import ToolExecutionCoordinator

router = APIRouter(tags=["tools"])

_TOOL_ERROR_STATUS = {
    ToolErrorCode.DUPLICATE_TOOL: 500,
    ToolErrorCode.TOOL_NOT_FOUND: 404,
    ToolErrorCode.INVALID_ARGUMENTS: 422,
    ToolErrorCode.APPROVAL_REQUIRED: 409,
    ToolErrorCode.DENIED: 403,
    ToolErrorCode.EXECUTION_FAILED: 500,
    ToolErrorCode.SENTINEL_AUTHORIZATION_FAILED: 500,
    ToolErrorCode.INTERNAL_ERROR: 500,
}


class SentinelDecisionResponse(BaseModel):
    """Safe Sentinel decision details."""

    model_config = ConfigDict(extra="forbid")

    decision: AuthorizationAction
    reason: str = Field(min_length=1)


class ToolExecuteResponse(BaseModel):
    """Stable successful tool execution response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    tool_name: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    sentinel: SentinelDecisionResponse
    result: ToolResult


class ToolError(BaseModel):
    """Safe API error details for Tool Fabric failures."""

    model_config = ConfigDict(extra="forbid")

    code: ToolErrorCode
    message: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    tool_name: str | None = Field(default=None, min_length=1)


class ToolErrorResponse(BaseModel):
    """Stable error envelope for tool execution failures."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error: ToolError


@router.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    responses={
        403: {"model": ToolErrorResponse},
        404: {"model": ToolErrorResponse},
        409: {"model": ToolErrorResponse},
        422: {"model": ToolErrorResponse},
        500: {"model": ToolErrorResponse},
    },
)
async def execute_tool(
    tool_request: ToolRequest,
    request: Request,
) -> ToolExecuteResponse | JSONResponse:
    """Execute one deterministic tool through Tool Fabric and Sentinel."""

    coordinator: ToolExecutionCoordinator = request.app.state.tool_execution_coordinator
    try:
        outcome = await coordinator.execute(tool_request)
    except ToolExecutionError as exc:
        correlation_id = exc.correlation_id or tool_request.correlation_id or str(uuid4())
        error = ToolErrorResponse(
            error=ToolError(
                code=exc.code,
                message=exc.safe_message,
                correlation_id=correlation_id,
                tool_name=exc.tool_name or tool_request.tool_name,
            )
        )
        return JSONResponse(
            status_code=_TOOL_ERROR_STATUS[exc.code],
            content=error.model_dump(mode="json"),
        )

    return ToolExecuteResponse(
        tool_name=outcome.tool_name,
        correlation_id=outcome.correlation_id,
        sentinel=SentinelDecisionResponse(
            decision=outcome.sentinel_decision.action,
            reason=outcome.sentinel_decision.reason,
        ),
        result=outcome.result,
    )
