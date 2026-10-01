from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jarvis_core.api import create_app
from jarvis_core.audit import (
    ToolAuditOutcome,
    ToolAuditPersistenceError,
    ToolAuditRecord,
)
from jarvis_core.config import Settings
from jarvis_core.intelligence import (
    ProviderCapability,
    ProviderRequest,
    ProviderResponse,
    ProviderRegistry,
)
from jarvis_core.persistence import SQLiteToolAuditRepository, initialize_sqlite
from jarvis_core.sentinel import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
    DefaultSentinelPolicy,
)
from jarvis_core.tools import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolDescriptor,
    ToolErrorCode,
    ToolExecutionContext,
    ToolExecutionError,
    ToolRegistry,
    ToolRequest,
    ToolResult,
)
from jarvis_core.tools.router import ToolExecutionCoordinator
from tests.tool_audit_fakes import RecordingToolAuditRepository


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SecretArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1)


class AuditTestTool:
    def __init__(
        self,
        *,
        name: str = "test.audit",
        side_effect_level: SideEffectLevel = SideEffectLevel.READ,
        argument_model: type[BaseModel] = NoArgs,
        result: object | None = None,
        fail: bool = False,
        timeline: list[str] | None = None,
    ) -> None:
        self._descriptor = ToolDescriptor(
            name=name,
            description="Audit test tool.",
            side_effect_level=side_effect_level,
            execution_boundary=ExecutionBoundary.CORE,
            input_schema=argument_model.model_json_schema(),
        )
        self._argument_model = argument_model
        self._result = result or ToolResult(success=True, data={"ok": True})
        self._fail = fail
        self._timeline = timeline
        self.executions = 0

    @property
    def descriptor(self) -> ToolDescriptor:
        return self._descriptor

    @property
    def argument_model(self) -> type[BaseModel]:
        return self._argument_model

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResult:
        self.executions += 1
        if self._timeline is not None:
            self._timeline.append("tool")
        if self._fail:
            raise RuntimeError("raw-secret-tool-error")
        return self._result  # type: ignore[return-value]


class AuditTestSentinel:
    def __init__(
        self,
        *,
        action: AuthorizationAction = AuthorizationAction.ALLOW,
        fail: bool = False,
        timeline: list[str] | None = None,
    ) -> None:
        self.action = action
        self.fail = fail
        self.timeline = timeline
        self.requests: list[AuthorizationRequest] = []

    async def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        self.requests.append(request)
        if self.timeline is not None:
            self.timeline.append("sentinel")
        if self.fail:
            raise RuntimeError("raw-secret-sentinel-error")
        return AuthorizationDecision(
            action=self.action,
            reason="secret-sentinel-reason",
        )


class TimelineAuditRepository(RecordingToolAuditRepository):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self.timeline = timeline

    def create(self, record: ToolAuditRecord) -> None:
        self.timeline.append("audit-create")
        super().create(record)

    def update(self, record: ToolAuditRecord) -> None:
        self.timeline.append("audit-update")
        super().update(record)


class FakeProvider:
    provider_id = "fake"
    capabilities = frozenset({ProviderCapability.TEXT})

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(output="JARVIS is running locally.", model="fake-model")


class FailingReadAuditRepository(RecordingToolAuditRepository):
    def list_for_correlation(self, correlation_id: str) -> list[ToolAuditRecord]:
        try:
            raise sqlite3.OperationalError("raw-secret-database-path")
        except sqlite3.Error as exc:
            raise ToolAuditPersistenceError() from exc


def registry_with(tool: AuditTestTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)
    return registry


def provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    return registry


def final_record(repository: RecordingToolAuditRepository) -> ToolAuditRecord:
    assert len(repository.created) == 1
    assert len(repository.updated) == 1
    assert repository.created[0].audit_id == repository.updated[0].audit_id
    return repository.updated[0]


def test_audit_contract_is_frozen_payload_free_and_requires_aware_timestamps() -> None:
    started_at = datetime.now(UTC)
    record = ToolAuditRecord(
        audit_id=str(uuid4()),
        correlation_id="contract",
        tool_name="test.audit",
        started_at=started_at,
    )

    assert record.model_dump().keys() == {
        "audit_id",
        "correlation_id",
        "tool_name",
        "side_effect_level",
        "execution_boundary",
        "sentinel_decision",
        "outcome",
        "error_code",
        "started_at",
        "completed_at",
    }
    with pytest.raises(ValidationError):
        ToolAuditRecord(
            audit_id=str(uuid4()),
            correlation_id="bad-time",
            tool_name="test.audit",
            started_at=datetime.now(),
        )
    with pytest.raises(ValidationError):
        ToolAuditRecord(
            audit_id="not-a-uuid",
            correlation_id="bad-id",
            tool_name="test.audit",
            started_at=started_at,
        )
    shared_id = str(uuid4())
    with pytest.raises(ValidationError):
        ToolAuditRecord(
            audit_id=shared_id,
            correlation_id=shared_id,
            tool_name="test.audit",
            started_at=started_at,
        )
    with pytest.raises(ValidationError):
        ToolAuditRecord.model_validate({**record.model_dump(), "arguments": {}})
    with pytest.raises(ValidationError):
        record.correlation_id = "changed"


def test_sqlite_audit_repository_is_ordered_and_completion_is_irreversible(tmp_path) -> None:
    database_path = tmp_path / "audit.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    repository = SQLiteToolAuditRepository(database_path)
    started_at = datetime.now(UTC)
    later_id = str(uuid4())
    earlier_id = str(uuid4())

    repository.create(
        ToolAuditRecord(
            audit_id=later_id,
            correlation_id="shared",
            tool_name="test.later",
            started_at=started_at + timedelta(seconds=1),
        )
    )
    repository.create(
        ToolAuditRecord(
            audit_id=earlier_id,
            correlation_id="shared",
            tool_name="test.earlier",
            started_at=started_at,
        )
    )
    completed = ToolAuditRecord(
        audit_id=earlier_id,
        correlation_id="shared",
        tool_name="test.earlier",
        side_effect_level=SideEffectLevel.READ,
        execution_boundary=ExecutionBoundary.CORE,
        sentinel_decision=AuthorizationAction.ALLOW,
        outcome=ToolAuditOutcome.SUCCEEDED,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=1),
    )
    repository.update(completed)

    records = repository.list_for_correlation("shared")
    assert [record.audit_id for record in records] == [earlier_id, later_id]
    assert records[0] == completed
    with pytest.raises(ToolAuditPersistenceError):
        repository.update(completed)
    assert repository.list_for_correlation("missing") == []


def test_sqlite_audit_schema_contains_only_allowlisted_columns(tmp_path) -> None:
    database_path = tmp_path / "schema.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(tool_execution_audits)"
            ).fetchall()
        }

    assert columns == {
        "audit_id",
        "correlation_id",
        "tool_name",
        "side_effect_level",
        "execution_boundary",
        "sentinel_decision",
        "outcome",
        "error_code",
        "started_at",
        "completed_at",
    }


@pytest.mark.anyio
async def test_coordinator_persists_start_before_sentinel_and_tool() -> None:
    timeline: list[str] = []
    repository = TimelineAuditRepository(timeline)
    sentinel = AuditTestSentinel(timeline=timeline)
    tool = AuditTestTool(timeline=timeline)
    coordinator = ToolExecutionCoordinator(registry_with(tool), sentinel, repository)

    await coordinator.execute(
        ToolRequest(
            tool_name="test.audit",
            arguments={},
            correlation_id="ordered",
        )
    )

    assert timeline == ["audit-create", "sentinel", "tool", "audit-update"]
    record = final_record(repository)
    assert UUID(record.audit_id)
    assert record.audit_id != record.correlation_id
    assert record.outcome is ToolAuditOutcome.SUCCEEDED
    assert record.sentinel_decision is AuthorizationAction.ALLOW


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_request", "tool", "sentinel", "expected_outcome", "expected_code"),
    [
        (
            ToolRequest(tool_name="missing.tool", arguments={}),
            AuditTestTool(),
            AuditTestSentinel(),
            ToolAuditOutcome.TOOL_NOT_FOUND,
            ToolErrorCode.TOOL_NOT_FOUND,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(argument_model=SecretArgs),
            AuditTestSentinel(),
            ToolAuditOutcome.INVALID_ARGUMENTS,
            ToolErrorCode.INVALID_ARGUMENTS,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(side_effect_level=SideEffectLevel.WRITE),
            AuditTestSentinel(action=AuthorizationAction.ASK),
            ToolAuditOutcome.APPROVAL_REQUIRED,
            ToolErrorCode.APPROVAL_REQUIRED,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(side_effect_level=SideEffectLevel.DANGEROUS),
            AuditTestSentinel(action=AuthorizationAction.DENY),
            ToolAuditOutcome.DENIED,
            ToolErrorCode.DENIED,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(),
            AuditTestSentinel(fail=True),
            ToolAuditOutcome.AUTHORIZATION_FAILED,
            ToolErrorCode.SENTINEL_AUTHORIZATION_FAILED,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(fail=True),
            AuditTestSentinel(),
            ToolAuditOutcome.TOOL_FAILED,
            ToolErrorCode.EXECUTION_FAILED,
        ),
        (
            ToolRequest(tool_name="test.audit", arguments={}),
            AuditTestTool(result=object()),
            AuditTestSentinel(),
            ToolAuditOutcome.INTERNAL_FAILURE,
            ToolErrorCode.INTERNAL_ERROR,
        ),
    ],
)
async def test_coordinator_records_normalized_failure_outcomes(
    tool_request: ToolRequest,
    tool: AuditTestTool,
    sentinel: AuditTestSentinel,
    expected_outcome: ToolAuditOutcome,
    expected_code: ToolErrorCode,
) -> None:
    repository = RecordingToolAuditRepository()
    registry = (
        ToolRegistry()
        if tool_request.tool_name == "missing.tool"
        else registry_with(tool)
    )
    coordinator = ToolExecutionCoordinator(registry, sentinel, repository)

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(tool_request)

    assert exc_info.value.code is expected_code
    record = final_record(repository)
    assert record.outcome is expected_outcome
    assert record.error_code is expected_code


@pytest.mark.anyio
async def test_initial_audit_failure_blocks_sentinel_and_tool() -> None:
    repository = RecordingToolAuditRepository(fail_create=True)
    sentinel = AuditTestSentinel()
    tool = AuditTestTool()
    coordinator = ToolExecutionCoordinator(registry_with(tool), sentinel, repository)

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.audit", arguments={}))

    assert exc_info.value.code is ToolErrorCode.INTERNAL_ERROR
    assert exc_info.value.safe_message == "Tool audit persistence failed."
    assert sentinel.requests == []
    assert tool.executions == 0


@pytest.mark.anyio
async def test_final_audit_failure_never_returns_unaudited_success() -> None:
    repository = RecordingToolAuditRepository(fail_update=True)
    sentinel = AuditTestSentinel()
    tool = AuditTestTool()
    coordinator = ToolExecutionCoordinator(registry_with(tool), sentinel, repository)

    with pytest.raises(ToolExecutionError) as exc_info:
        await coordinator.execute(ToolRequest(tool_name="test.audit", arguments={}))

    assert exc_info.value.code is ToolErrorCode.INTERNAL_ERROR
    assert exc_info.value.safe_message == "Tool audit persistence failed."
    assert tool.executions == 1
    assert repository.updated == []
    assert repository.created[0].outcome is ToolAuditOutcome.STARTED


def test_direct_and_chat_tool_paths_create_queryable_audits(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "integration.sqlite3",
        intelligence_provider="fake",
    )
    app = create_app(settings, provider_registry=provider_registry())

    with TestClient(app) as client:
        direct = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "system.runtime_info",
                "arguments": {},
                "correlation_id": "audit-direct",
            },
        )
        chat = client.post(
            "/v1/chat",
            json={
                "message": "What version of JARVIS am I running?",
                "correlation_id": "audit-chat",
            },
        )
        direct_audit = client.get("/v1/audit/tool-executions/audit-direct")
        chat_audit = client.get("/v1/audit/tool-executions/audit-chat")
        missing = client.get("/v1/audit/tool-executions/audit-missing")

    assert direct.status_code == 200
    assert chat.status_code == 200, chat.json()
    assert chat.json()["tools_used"] == ["system.runtime_info"]
    assert direct_audit.status_code == 200
    assert chat_audit.status_code == 200
    assert direct_audit.json()["records"][0]["outcome"] == "succeeded"
    assert chat_audit.json()["records"][0]["outcome"] == "succeeded"
    assert missing.json() == {"correlation_id": "audit-missing", "records": []}


def test_audit_persistence_omits_arguments_results_reasons_and_raw_errors(tmp_path) -> None:
    database_path = tmp_path / "privacy.sqlite3"
    settings = Settings(database_path=database_path)
    secret = "audit-secret-sentinel-value"
    tool = AuditTestTool(
        argument_model=SecretArgs,
        result=ToolResult(success=True, data={"secret_result": secret}),
    )

    with TestClient(
        create_app(
            settings,
            tool_registry=registry_with(tool),
            sentinel=AuditTestSentinel(),
        )
    ) as client:
        response = client.post(
            "/v1/tools/execute",
            json={
                "tool_name": "test.audit",
                "arguments": {"secret": secret},
                "correlation_id": "privacy-audit",
            },
        )
        audit = client.get("/v1/audit/tool-executions/privacy-audit")

    with sqlite3.connect(database_path) as connection:
        persisted = connection.execute(
            "SELECT * FROM tool_execution_audits WHERE correlation_id = ?",
            ("privacy-audit",),
        ).fetchone()

    rendered = json.dumps({"api": audit.json(), "database": list(persisted)})
    assert response.status_code == 200
    assert secret not in rendered
    assert "secret-sentinel-reason" not in rendered
    assert "arguments" not in rendered
    assert "result" not in rendered
    assert "exception" not in rendered


def test_audit_read_failure_returns_only_safe_normalized_error(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "read-failure.sqlite3")
    app = create_app(settings)

    with TestClient(app) as client:
        client.app.state.tool_audit_repository = FailingReadAuditRepository()
        response = client.get("/v1/audit/tool-executions/read-failure")

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "tool_audit_persistence_failed",
            "message": "Tool audit persistence failed.",
            "correlation_id": "read-failure",
        },
    }
    assert "raw-secret" not in response.text
