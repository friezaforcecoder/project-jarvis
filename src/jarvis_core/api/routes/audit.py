"""Read-only tool execution audit endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from jarvis_core.audit import (
    ToolAuditPersistenceError,
    ToolAuditRecord,
    ToolAuditRepository,
)

router = APIRouter(tags=["audit"])


class ToolExecutionAuditListResponse(BaseModel):
    """Payload-free audit records for one request correlation."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str = Field(min_length=1)
    records: list[ToolAuditRecord] = Field(default_factory=list)


class AuditReadError(BaseModel):
    """Safe audit persistence error details."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["tool_audit_persistence_failed"]
    message: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


class AuditReadErrorResponse(BaseModel):
    """Stable error envelope for audit read failures."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error: AuditReadError


@router.get(
    "/audit/tool-executions/{correlation_id}",
    response_model=ToolExecutionAuditListResponse,
    responses={500: {"model": AuditReadErrorResponse}},
)
def list_tool_execution_audits(
    correlation_id: str,
    request: Request,
) -> ToolExecutionAuditListResponse | JSONResponse:
    """Return deterministic, allowlisted audit metadata for one correlation."""

    repository: ToolAuditRepository = request.app.state.tool_audit_repository
    try:
        records = repository.list_for_correlation(correlation_id)
    except ToolAuditPersistenceError as exc:
        error = AuditReadErrorResponse(
            error=AuditReadError(
                code="tool_audit_persistence_failed",
                message=exc.safe_message,
                correlation_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=500,
            content=error.model_dump(mode="json"),
        )

    return ToolExecutionAuditListResponse(
        correlation_id=correlation_id,
        records=records,
    )
