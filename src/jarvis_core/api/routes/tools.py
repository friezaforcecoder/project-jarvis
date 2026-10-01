"""Direct Tool Fabric execution endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from jarvis_core.sentinel import (
    AuthorizationAction,
    ToolApprovalAlreadyConsumedError,
    ToolApprovalError,
    ToolApprovalExpiredError,
    ToolApprovalNotFoundError,
    ToolApprovalRepository,
    ToolApprovalStatus,
    ToolApprovalUnavailableError,
)
from jarvis_core.tools import (
    ToolApprovalChallenge,
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
    ToolErrorCode.APPROVAL_EXPIRED: 410,
    ToolErrorCode.APPROVAL_INVALID: 409,
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
    approval: ToolApprovalChallenge | None = None


class ToolApprovalGrantResponse(BaseModel):
    """Successful approval grant response with no execution details."""

    model_config = ConfigDict(extra="forbid")

    approval_id: UUID
    status: ToolApprovalStatus
    expires_at: datetime


class ToolApprovalEndpointError(BaseModel):
    """Safe grant-endpoint error details."""

    model_config = ConfigDict(extra="forbid")

    code: ToolErrorCode
    message: str = Field(min_length=1)


class ToolApprovalEndpointErrorResponse(BaseModel):
    """Stable grant-endpoint error envelope."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error: ToolApprovalEndpointError


@router.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    responses={
        403: {"model": ToolErrorResponse},
        404: {"model": ToolErrorResponse},
        409: {"model": ToolErrorResponse},
        410: {"model": ToolErrorResponse},
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
        outcome = await coordinator.execute(tool_request, allow_approval=True)
    except ToolExecutionError as exc:
        correlation_id = exc.correlation_id or tool_request.correlation_id or str(uuid4())
        error = ToolErrorResponse(
            error=ToolError(
                code=exc.code,
                message=exc.safe_message,
                correlation_id=correlation_id,
                tool_name=exc.tool_name or tool_request.tool_name,
            ),
            approval=exc.approval_challenge,
        )
        return JSONResponse(
            status_code=_TOOL_ERROR_STATUS[exc.code],
            content=error.model_dump(mode="json", exclude_none=True),
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


@router.post(
    "/tool-approvals/{approval_id}/grant",
    response_model=ToolApprovalGrantResponse,
    responses={
        404: {"model": ToolApprovalEndpointErrorResponse},
        409: {"model": ToolApprovalEndpointErrorResponse},
        410: {"model": ToolApprovalEndpointErrorResponse},
        500: {"model": ToolApprovalEndpointErrorResponse},
    },
)
async def grant_tool_approval(
    approval_id: UUID,
    request: Request,
) -> ToolApprovalGrantResponse | JSONResponse:
    """Grant one pending receipt without executing its bound tool request."""

    repository: ToolApprovalRepository = request.app.state.tool_approval_repository
    try:
        record = repository.grant(approval_id, now=datetime.now(UTC))
    except ToolApprovalNotFoundError:
        return _approval_endpoint_error(
            status_code=404,
            code=ToolErrorCode.APPROVAL_INVALID,
            message="Tool approval receipt was not found.",
        )
    except (ToolApprovalUnavailableError, ToolApprovalAlreadyConsumedError):
        return _approval_endpoint_error(
            status_code=409,
            code=ToolErrorCode.APPROVAL_INVALID,
            message="Tool approval receipt is unavailable.",
        )
    except ToolApprovalExpiredError:
        return _approval_endpoint_error(
            status_code=410,
            code=ToolErrorCode.APPROVAL_EXPIRED,
            message="Tool approval receipt has expired.",
        )
    except ToolApprovalError:
        return _approval_endpoint_error(
            status_code=500,
            code=ToolErrorCode.INTERNAL_ERROR,
            message="Tool approval operation failed.",
        )

    return ToolApprovalGrantResponse(
        approval_id=record.approval_id,
        status=record.status,
        expires_at=record.expires_at,
    )


def _approval_endpoint_error(
    *,
    status_code: int,
    code: ToolErrorCode,
    message: str,
) -> JSONResponse:
    response = ToolApprovalEndpointErrorResponse(
        error=ToolApprovalEndpointError(code=code, message=message)
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )
