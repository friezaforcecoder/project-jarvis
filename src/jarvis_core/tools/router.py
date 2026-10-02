"""Tool execution coordinator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from jarvis_core.audit import (
    ToolAuditOutcome,
    ToolAuditRecord,
    ToolAuditRepository,
)
from jarvis_core.sentinel.approval import (
    APPROVAL_LIFETIME,
    ToolApprovalAlreadyConsumedError,
    ToolApprovalBindingService,
    ToolApprovalError,
    ToolApprovalExpiredError,
    ToolApprovalMismatchError,
    ToolApprovalNotFoundError,
    ToolApprovalRecord,
    ToolApprovalRepository,
    ToolApprovalStatus,
    ToolApprovalUnavailableError,
)
from jarvis_core.sentinel.contracts import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
    Sentinel,
)
from jarvis_core.tools.contracts import (
    Tool,
    ToolApprovalChallenge,
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

    def __init__(
        self,
        tool_registry: ToolRegistry,
        sentinel: Sentinel,
        audit_repository: ToolAuditRepository,
        approval_repository: ToolApprovalRepository | None = None,
        approval_binding_service: ToolApprovalBindingService | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._sentinel = sentinel
        self._audit_repository = audit_repository
        self._approval_repository = approval_repository
        self._approval_binding_service = approval_binding_service

    async def execute(
        self,
        request: ToolRequest,
        *,
        allow_approval: bool = False,
    ) -> ToolExecutionOutcome:
        """Execute one tool request through the safe Tool Fabric path."""

        correlation_id = request.correlation_id or str(uuid4())
        audit_id = str(uuid4())
        while audit_id == correlation_id:
            audit_id = str(uuid4())
        audit_started_at = datetime.now(UTC)
        started_at = perf_counter()
        descriptor: ToolDescriptor | None = None
        decision: AuthorizationDecision | None = None

        self._create_audit(
            ToolAuditRecord(
                audit_id=audit_id,
                correlation_id=correlation_id,
                tool_name=request.tool_name,
                started_at=audit_started_at,
            )
        )
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
            if decision.action is AuthorizationAction.DENY:
                raise ToolExecutionError(
                    ToolErrorCode.DENIED,
                    "Tool execution was denied by Sentinel.",
                    tool_name=descriptor.name,
                    correlation_id=correlation_id,
                )
            if decision.action is AuthorizationAction.ASK:
                if not allow_approval:
                    raise ToolExecutionError(
                        ToolErrorCode.APPROVAL_REQUIRED,
                        "Tool approval is required.",
                        tool_name=descriptor.name,
                        correlation_id=correlation_id,
                    )
                self._resolve_direct_approval(
                    request=request,
                    descriptor=descriptor,
                    arguments=arguments,
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
        except ToolExecutionError as exc:
            if exc.correlation_id is None:
                exc.correlation_id = correlation_id
            self._complete_audit(
                audit_id=audit_id,
                correlation_id=correlation_id,
                tool_name=request.tool_name,
                started_at=audit_started_at,
                descriptor=descriptor,
                decision=decision,
                outcome=_audit_outcome_for(exc.code),
                error_code=exc.code,
            )
            self._log_failure(
                exc,
                request_tool_name=request.tool_name,
                started_at=started_at,
                descriptor=descriptor,
                decision=decision,
            )
            raise
        except Exception as exc:
            self._complete_audit(
                audit_id=audit_id,
                correlation_id=correlation_id,
                tool_name=request.tool_name,
                started_at=audit_started_at,
                descriptor=descriptor,
                decision=decision,
                outcome=ToolAuditOutcome.INTERNAL_FAILURE,
                error_code=ToolErrorCode.INTERNAL_ERROR,
            )
            normalized = ToolExecutionError(
                ToolErrorCode.INTERNAL_ERROR,
                "Tool execution failed.",
                tool_name=request.tool_name,
                correlation_id=correlation_id,
            )
            self._log_failure(
                normalized,
                request_tool_name=request.tool_name,
                started_at=started_at,
                descriptor=descriptor,
                decision=decision,
            )
            raise normalized from exc

        self._complete_audit(
            audit_id=audit_id,
            correlation_id=correlation_id,
            tool_name=request.tool_name,
            started_at=audit_started_at,
            descriptor=descriptor,
            decision=decision,
            outcome=(
                ToolAuditOutcome.SUCCEEDED
                if result.success
                else ToolAuditOutcome.TOOL_FAILED
            ),
            error_code=None if result.success else ToolErrorCode.EXECUTION_FAILED,
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

    def _resolve_direct_approval(
        self,
        *,
        request: ToolRequest,
        descriptor: ToolDescriptor,
        arguments: BaseModel,
        correlation_id: str,
    ) -> None:
        repository = self._approval_repository
        binding_service = self._approval_binding_service
        if repository is None or binding_service is None:
            raise self._approval_internal_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )

        try:
            request_binding = binding_service.compute_binding(
                correlation_id=correlation_id,
                tool_name=descriptor.name,
                side_effect_level=descriptor.side_effect_level,
                execution_boundary=descriptor.execution_boundary,
                arguments=arguments,
            )
        except ToolApprovalError as exc:
            raise self._approval_internal_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            ) from exc

        now = datetime.now(UTC)
        if request.approval_id is None:
            record = ToolApprovalRecord(
                approval_id=uuid4(),
                request_binding=request_binding,
                status=ToolApprovalStatus.PENDING,
                created_at=now,
                expires_at=now + APPROVAL_LIFETIME,
            )
            try:
                repository.create(record)
            except ToolApprovalError as exc:
                raise self._approval_internal_error(
                    tool_name=descriptor.name,
                    correlation_id=correlation_id,
                ) from exc
            raise self._approval_required_error(
                record,
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )

        try:
            record = repository.get(request.approval_id)
        except ToolApprovalError as exc:
            raise self._approval_internal_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            ) from exc

        if record is None:
            raise self._approval_invalid_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
        if now >= record.expires_at:
            raise self._approval_expired_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
        if not binding_service.compare_bindings(
            record.request_binding,
            request_binding,
        ):
            raise self._approval_invalid_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
        if record.status is ToolApprovalStatus.PENDING:
            raise self._approval_required_error(
                record,
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )
        if record.status is ToolApprovalStatus.CONSUMED:
            raise self._approval_invalid_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )

        try:
            repository.consume(
                record.approval_id,
                request_binding,
                now=now,
            )
        except ToolApprovalExpiredError as exc:
            raise self._approval_expired_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            ) from exc
        except (
            ToolApprovalAlreadyConsumedError,
            ToolApprovalMismatchError,
            ToolApprovalNotFoundError,
            ToolApprovalUnavailableError,
        ) as exc:
            raise self._approval_invalid_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            ) from exc
        except ToolApprovalError as exc:
            raise self._approval_internal_error(
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            ) from exc

    @staticmethod
    def _approval_required_error(
        record: ToolApprovalRecord,
        *,
        tool_name: str,
        correlation_id: str,
    ) -> ToolExecutionError:
        return ToolExecutionError(
            ToolErrorCode.APPROVAL_REQUIRED,
            "Tool approval is required.",
            tool_name=tool_name,
            correlation_id=correlation_id,
            approval_challenge=ToolApprovalChallenge(
                approval_id=record.approval_id,
                expires_at=record.expires_at,
            ),
        )

    @staticmethod
    def _approval_expired_error(
        *,
        tool_name: str,
        correlation_id: str,
    ) -> ToolExecutionError:
        return ToolExecutionError(
            ToolErrorCode.APPROVAL_EXPIRED,
            "Tool approval receipt has expired.",
            tool_name=tool_name,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _approval_invalid_error(
        *,
        tool_name: str,
        correlation_id: str,
    ) -> ToolExecutionError:
        return ToolExecutionError(
            ToolErrorCode.APPROVAL_INVALID,
            "Tool approval receipt is invalid.",
            tool_name=tool_name,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _approval_internal_error(
        *,
        tool_name: str,
        correlation_id: str,
    ) -> ToolExecutionError:
        return ToolExecutionError(
            ToolErrorCode.INTERNAL_ERROR,
            "Tool approval operation failed.",
            tool_name=tool_name,
            correlation_id=correlation_id,
        )

    def _create_audit(self, record: ToolAuditRecord) -> None:
        try:
            self._audit_repository.create(record)
        except Exception as exc:
            raise _audit_persistence_error(
                tool_name=record.tool_name,
                correlation_id=record.correlation_id,
            ) from exc

    def _complete_audit(
        self,
        *,
        audit_id: str,
        correlation_id: str,
        tool_name: str,
        started_at: datetime,
        descriptor: ToolDescriptor | None,
        decision: AuthorizationDecision | None,
        outcome: ToolAuditOutcome,
        error_code: ToolErrorCode | None,
    ) -> None:
        try:
            self._audit_repository.update(
                ToolAuditRecord(
                    audit_id=audit_id,
                    correlation_id=correlation_id,
                    tool_name=tool_name,
                    side_effect_level=(
                        descriptor.side_effect_level if descriptor is not None else None
                    ),
                    execution_boundary=(
                        descriptor.execution_boundary if descriptor is not None else None
                    ),
                    sentinel_decision=decision.action if decision is not None else None,
                    outcome=outcome,
                    error_code=error_code,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )
            )
        except Exception as exc:
            raise _audit_persistence_error(
                tool_name=tool_name,
                correlation_id=correlation_id,
            ) from exc

    def _log_failure(
        self,
        exc: ToolExecutionError,
        *,
        request_tool_name: str,
        started_at: float,
        descriptor: ToolDescriptor | None,
        decision: AuthorizationDecision | None,
    ) -> None:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        extra: dict[str, object] = {
            "correlation_id": exc.correlation_id,
            "tool_name": exc.tool_name or request_tool_name,
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


def _audit_outcome_for(error_code: ToolErrorCode) -> ToolAuditOutcome:
    outcomes = {
        ToolErrorCode.TOOL_NOT_FOUND: ToolAuditOutcome.TOOL_NOT_FOUND,
        ToolErrorCode.INVALID_ARGUMENTS: ToolAuditOutcome.INVALID_ARGUMENTS,
        ToolErrorCode.APPROVAL_REQUIRED: ToolAuditOutcome.APPROVAL_REQUIRED,
        ToolErrorCode.APPROVAL_EXPIRED: ToolAuditOutcome.APPROVAL_EXPIRED,
        ToolErrorCode.APPROVAL_INVALID: ToolAuditOutcome.APPROVAL_INVALID,
        ToolErrorCode.DENIED: ToolAuditOutcome.DENIED,
        ToolErrorCode.SENTINEL_AUTHORIZATION_FAILED: (
            ToolAuditOutcome.AUTHORIZATION_FAILED
        ),
        ToolErrorCode.EXECUTION_FAILED: ToolAuditOutcome.TOOL_FAILED,
    }
    return outcomes.get(error_code, ToolAuditOutcome.INTERNAL_FAILURE)


def _audit_persistence_error(
    *,
    tool_name: str,
    correlation_id: str,
) -> ToolExecutionError:
    return ToolExecutionError(
        ToolErrorCode.INTERNAL_ERROR,
        "Tool audit persistence failed.",
        tool_name=tool_name,
        correlation_id=correlation_id,
    )
