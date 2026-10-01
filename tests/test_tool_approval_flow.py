from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from jarvis_core.api import create_app
from jarvis_core.config import Settings
from jarvis_core.persistence import SQLiteToolApprovalRepository, initialize_sqlite
from jarvis_core.sentinel import (
    DefaultSentinelPolicy,
    ToolApprovalBindingService,
    ToolApprovalPersistenceError,
    ToolApprovalRecord,
    ToolApprovalStatus,
)
from jarvis_core.tools import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolDescriptor,
    ToolErrorCode,
    ToolExecutionError,
    ToolExecutionContext,
    ToolRegistry,
    ToolRequest,
    ToolResult,
)
from jarvis_core.tools.router import ToolExecutionCoordinator
from tests.tool_audit_fakes import RecordingToolAuditRepository


class ApprovalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class ApprovalTestTool:
    def __init__(
        self,
        name: str,
        side_effect_level: SideEffectLevel,
    ) -> None:
        self._descriptor = ToolDescriptor(
            name=name,
            description=f"{name} approval test tool.",
            side_effect_level=side_effect_level,
            execution_boundary=ExecutionBoundary.CORE,
            input_schema=ApprovalArgs.model_json_schema(),
        )
        self.executions = 0
        self.last_arguments: ApprovalArgs | None = None
        self.on_execute: Callable[[], None] | None = None

    @property
    def descriptor(self) -> ToolDescriptor:
        return self._descriptor

    @property
    def argument_model(self) -> type[ApprovalArgs]:
        return ApprovalArgs

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if self.on_execute is not None:
            self.on_execute()
        self.executions += 1
        self.last_arguments = ApprovalArgs.model_validate(arguments.model_dump())
        return ToolResult(success=True, data={"executed": True})


def _registry(*tools: ApprovalTestTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _execute_payload(
    *,
    tool_name: str = "test.write",
    value: str = "synthetic-secret",
    correlation_id: str = "approval-flow",
    approval_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "tool_name": tool_name,
        "arguments": {"value": value},
        "correlation_id": correlation_id,
    }
    if approval_id is not None:
        payload["approval_id"] = approval_id
    return payload


def _approval_row(database_path: Path, approval_id: str) -> sqlite3.Row:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM tool_approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    assert row is not None
    return row


def test_direct_approval_flow_executes_once_and_audits_without_capabilities(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    settings = Settings(database_path=database_path, log_level="INFO")
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    caplog.set_level(logging.INFO)

    with TestClient(create_app(settings, tool_registry=_registry(tool))) as client:
        first = client.post("/v1/tools/execute", json=_execute_payload())
        assert first.status_code == 409
        first_body = first.json()
        assert first_body["error"] == {
            "code": "tool_approval_required",
            "message": "Tool approval is required.",
            "correlation_id": "approval-flow",
            "tool_name": "test.write",
        }
        assert set(first_body["approval"]) == {"approval_id", "expires_at"}
        approval_id = first_body["approval"]["approval_id"]
        UUID(approval_id)

        pending = client.post(
            "/v1/tools/execute",
            json=_execute_payload(approval_id=approval_id),
        )
        assert pending.status_code == 409
        assert pending.json()["approval"] == first_body["approval"]

        with sqlite3.connect(database_path) as connection:
            approval_count = connection.execute(
                "SELECT count(*) FROM tool_approvals"
            ).fetchone()[0]
        assert approval_count == 1

        grant = client.post(f"/v1/tool-approvals/{approval_id}/grant")
        assert grant.status_code == 200
        assert set(grant.json()) == {"approval_id", "status", "expires_at"}
        assert grant.json()["approval_id"] == approval_id
        assert grant.json()["status"] == "approved"
        assert tool.executions == 0

        def assert_consumed_before_execution() -> None:
            record = client.app.state.tool_approval_repository.get(UUID(approval_id))
            assert record is not None
            assert record.status is ToolApprovalStatus.CONSUMED

        tool.on_execute = assert_consumed_before_execution

        executed = client.post(
            "/v1/tools/execute",
            json=_execute_payload(approval_id=approval_id),
        )
        assert executed.status_code == 200
        assert executed.json()["result"] == {
            "success": True,
            "data": {"executed": True},
            "error": None,
        }
        assert tool.executions == 1

        replay = client.post(
            "/v1/tools/execute",
            json=_execute_payload(approval_id=approval_id),
        )
        assert replay.status_code == 409
        assert replay.json()["error"]["code"] == "tool_approval_invalid"
        assert "approval" not in replay.json()
        assert tool.executions == 1

        audit = client.get("/v1/audit/tool-executions/approval-flow")
        assert audit.status_code == 200

    persisted = dict(_approval_row(database_path, approval_id))
    assert persisted["status"] == "consumed"
    assert set(persisted) == {
        "approval_id",
        "request_binding",
        "status",
        "created_at",
        "expires_at",
        "approved_at",
        "consumed_at",
    }
    assert "synthetic-secret" not in str(persisted)

    audit_text = audit.text
    assert approval_id not in audit_text
    assert persisted["request_binding"] not in audit_text
    assert "synthetic-secret" not in audit_text
    records = audit.json()["records"]
    assert [record["outcome"] for record in records].count("approval_required") == 2
    assert [record["outcome"] for record in records].count("succeeded") == 1
    assert [record["outcome"] for record in records].count("approval_invalid") == 1
    assert all(record["sentinel_decision"] == "ask" for record in records)
    assert approval_id not in caplog.text
    assert persisted["request_binding"] not in caplog.text
    assert "synthetic-secret" not in caplog.text


@pytest.mark.parametrize(
    "retry_payload",
    [
        _execute_payload(value="changed-value"),
        _execute_payload(correlation_id="changed-correlation"),
    ],
)
def test_changed_bound_request_is_invalid(
    tmp_path: Path,
    retry_payload: dict[str, object],
) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)

    with TestClient(create_app(settings, tool_registry=_registry(tool))) as client:
        challenge = client.post("/v1/tools/execute", json=_execute_payload()).json()
        approval_id = challenge["approval"]["approval_id"]
        assert client.post(
            f"/v1/tool-approvals/{approval_id}/grant"
        ).status_code == 200
        retry_payload = {**retry_payload, "approval_id": approval_id}
        response = client.post("/v1/tools/execute", json=retry_payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tool_approval_invalid"
    assert "approval" not in response.json()
    assert tool.executions == 0


def test_process_restart_invalidates_approved_receipt(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    first_tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)

    with TestClient(create_app(settings, tool_registry=_registry(first_tool))) as client:
        challenge = client.post("/v1/tools/execute", json=_execute_payload()).json()
        approval_id = challenge["approval"]["approval_id"]
        assert client.post(
            f"/v1/tool-approvals/{approval_id}/grant"
        ).status_code == 200

    restarted_tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    with TestClient(
        create_app(settings, tool_registry=_registry(restarted_tool))
    ) as restarted_client:
        response = restarted_client.post(
            "/v1/tools/execute",
            json=_execute_payload(approval_id=approval_id),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tool_approval_invalid"
    assert restarted_tool.executions == 0
    assert _approval_row(settings.database_path, approval_id)["status"] == "approved"


def test_deny_cannot_be_overridden_and_allow_does_not_consume(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    write_tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    read_tool = ApprovalTestTool("test.read", SideEffectLevel.READ)
    dangerous_tool = ApprovalTestTool("test.dangerous", SideEffectLevel.DANGEROUS)
    app = create_app(
        settings,
        tool_registry=_registry(write_tool, read_tool, dangerous_tool),
    )

    with TestClient(app) as client:
        challenge = client.post("/v1/tools/execute", json=_execute_payload()).json()
        approval_id = challenge["approval"]["approval_id"]
        assert client.post(
            f"/v1/tool-approvals/{approval_id}/grant"
        ).status_code == 200

        allowed = client.post(
            "/v1/tools/execute",
            json=_execute_payload(
                tool_name="test.read",
                value="read-value",
                approval_id=approval_id,
            ),
        )
        denied = client.post(
            "/v1/tools/execute",
            json=_execute_payload(
                tool_name="test.dangerous",
                value="danger-value",
                approval_id=approval_id,
            ),
        )

    assert allowed.status_code == 200
    assert read_tool.executions == 1
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "tool_denied"
    assert dangerous_tool.executions == 0
    assert write_tool.executions == 0
    assert _approval_row(settings.database_path, approval_id)["status"] == "approved"


def test_grant_endpoint_normalizes_lifecycle_errors(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    app = create_app(settings, tool_registry=_registry(tool))

    with TestClient(app) as client:
        unknown = client.post(f"/v1/tool-approvals/{uuid4()}/grant")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "tool_approval_invalid"

        challenge = client.post("/v1/tools/execute", json=_execute_payload()).json()
        approval_id = challenge["approval"]["approval_id"]
        first_grant = client.post(f"/v1/tool-approvals/{approval_id}/grant")
        duplicate = client.post(f"/v1/tool-approvals/{approval_id}/grant")

        expired_record = ToolApprovalRecord(
            approval_id=uuid4(),
            request_binding="a" * 64,
            status=ToolApprovalStatus.PENDING,
            created_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        app.state.tool_approval_repository.create(expired_record)
        expired = client.post(
            f"/v1/tool-approvals/{expired_record.approval_id}/grant"
        )

    assert first_grant.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "tool_approval_invalid"
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "tool_approval_expired"
    assert tool.executions == 0


def test_approval_persistence_failure_blocks_execution_and_returns_no_challenge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    app = create_app(settings, tool_registry=_registry(tool))

    def fail_create(record: ToolApprovalRecord) -> None:
        raise ToolApprovalPersistenceError()

    monkeypatch.setattr(app.state.tool_approval_repository, "create", fail_create)

    with TestClient(app) as client:
        response = client.post("/v1/tools/execute", json=_execute_payload())
        audit = client.get("/v1/audit/tool-executions/approval-flow")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "tool_internal_error"
    assert "approval" not in response.json()
    assert tool.executions == 0
    assert audit.json()["records"][0]["outcome"] == "internal_failure"


def test_expired_and_unknown_direct_receipts_are_terminal_audit_outcomes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    settings = Settings(database_path=database_path)
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)

    with TestClient(create_app(settings, tool_registry=_registry(tool))) as client:
        challenge = client.post("/v1/tools/execute", json=_execute_payload()).json()
        approval_id = challenge["approval"]["approval_id"]
        assert client.post(
            f"/v1/tool-approvals/{approval_id}/grant"
        ).status_code == 200

        now = datetime.now(UTC)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                UPDATE tool_approvals
                SET created_at = ?, expires_at = ?, approved_at = ?
                WHERE approval_id = ?
                """,
                (
                    (now - timedelta(minutes=10)).isoformat(timespec="microseconds"),
                    (now - timedelta(minutes=5)).isoformat(timespec="microseconds"),
                    (now - timedelta(minutes=9)).isoformat(timespec="microseconds"),
                    approval_id,
                ),
            )

        expired = client.post(
            "/v1/tools/execute",
            json=_execute_payload(approval_id=approval_id),
        )
        unknown = client.post(
            "/v1/tools/execute",
            json=_execute_payload(
                correlation_id="approval-unknown",
                approval_id=str(uuid4()),
            ),
        )
        expired_audit = client.get("/v1/audit/tool-executions/approval-flow")
        unknown_audit = client.get("/v1/audit/tool-executions/approval-unknown")

    assert expired.status_code == 410
    assert expired.json()["error"] == {
        "code": "tool_approval_expired",
        "message": "Tool approval receipt has expired.",
        "correlation_id": "approval-flow",
        "tool_name": "test.write",
    }
    assert unknown.status_code == 409
    assert unknown.json()["error"] == {
        "code": "tool_approval_invalid",
        "message": "Tool approval receipt is invalid.",
        "correlation_id": "approval-unknown",
        "tool_name": "test.write",
    }
    assert expired_audit.json()["records"][-1]["outcome"] == "approval_expired"
    assert unknown_audit.json()["records"][-1]["outcome"] == "approval_invalid"
    assert tool.executions == 0


@pytest.mark.anyio
async def test_final_audit_failure_leaves_receipt_spent_after_execution(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    approval_repository = SQLiteToolApprovalRepository(database_path)
    audit_repository = RecordingToolAuditRepository()
    coordinator = ToolExecutionCoordinator(
        _registry(tool),
        DefaultSentinelPolicy(),
        audit_repository,
        approval_repository,
        ToolApprovalBindingService(key=b"k" * 32),
    )
    request = ToolRequest(
        tool_name="test.write",
        arguments={"value": "audit-failure"},
        correlation_id="approval-audit-failure",
    )

    with pytest.raises(ToolExecutionError) as challenge_info:
        await coordinator.execute(request, allow_approval=True)
    assert challenge_info.value.code is ToolErrorCode.APPROVAL_REQUIRED
    challenge = challenge_info.value.approval_challenge
    assert challenge is not None
    approval_repository.grant(challenge.approval_id, now=datetime.now(UTC))

    def assert_consumed_before_execution() -> None:
        record = approval_repository.get(challenge.approval_id)
        assert record is not None
        assert record.status is ToolApprovalStatus.CONSUMED

    tool.on_execute = assert_consumed_before_execution
    audit_repository.fail_update = True
    approved_request = request.model_copy(
        update={"approval_id": challenge.approval_id}
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(approved_request, allow_approval=True)

    assert exc_info.value.code is ToolErrorCode.INTERNAL_ERROR
    assert exc_info.value.safe_message == "Tool audit persistence failed."
    assert tool.executions == 1
    spent = approval_repository.get(challenge.approval_id)
    assert spent is not None
    assert spent.status is ToolApprovalStatus.CONSUMED


@pytest.mark.anyio
async def test_initial_audit_failure_creates_no_approval_receipt(tmp_path: Path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    tool = ApprovalTestTool("test.write", SideEffectLevel.WRITE)
    coordinator = ToolExecutionCoordinator(
        _registry(tool),
        DefaultSentinelPolicy(),
        RecordingToolAuditRepository(fail_create=True),
        SQLiteToolApprovalRepository(database_path),
        ToolApprovalBindingService(key=b"k" * 32),
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(
            ToolRequest(tool_name="test.write", arguments={"value": "blocked"}),
            allow_approval=True,
        )

    assert exc_info.value.code is ToolErrorCode.INTERNAL_ERROR
    assert exc_info.value.safe_message == "Tool audit persistence failed."
    assert tool.executions == 0
    with sqlite3.connect(database_path) as connection:
        approval_count = connection.execute(
            "SELECT count(*) FROM tool_approvals"
        ).fetchone()[0]
    assert approval_count == 0


def test_grant_persistence_failure_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(database_path=tmp_path / "jarvis.sqlite3")
    app = create_app(settings)

    def fail_grant(approval_id: UUID, *, now: datetime) -> ToolApprovalRecord:
        raise ToolApprovalPersistenceError()

    monkeypatch.setattr(app.state.tool_approval_repository, "grant", fail_grant)

    with TestClient(app) as client:
        response = client.post(f"/v1/tool-approvals/{uuid4()}/grant")

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "tool_internal_error",
            "message": "Tool approval operation failed.",
        },
    }
