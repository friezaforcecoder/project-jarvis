"""Test doubles for tool execution audit persistence."""

from __future__ import annotations

from jarvis_core.audit import (
    ToolAuditOutcome,
    ToolAuditPersistenceError,
    ToolAuditRecord,
)


class RecordingToolAuditRepository:
    """Record audit lifecycle calls while supporting deterministic failures."""

    def __init__(self, *, fail_create: bool = False, fail_update: bool = False) -> None:
        self.fail_create = fail_create
        self.fail_update = fail_update
        self.created: list[ToolAuditRecord] = []
        self.updated: list[ToolAuditRecord] = []
        self._records: dict[str, ToolAuditRecord] = {}

    def create(self, record: ToolAuditRecord) -> None:
        if self.fail_create or record.outcome is not ToolAuditOutcome.STARTED:
            raise ToolAuditPersistenceError()
        if record.audit_id in self._records:
            raise ToolAuditPersistenceError()
        self.created.append(record)
        self._records[record.audit_id] = record

    def update(self, record: ToolAuditRecord) -> None:
        previous = self._records.get(record.audit_id)
        if self.fail_update or previous is None:
            raise ToolAuditPersistenceError()
        if previous.outcome is not ToolAuditOutcome.STARTED:
            raise ToolAuditPersistenceError()
        self.updated.append(record)
        self._records[record.audit_id] = record

    def list_for_correlation(self, correlation_id: str) -> list[ToolAuditRecord]:
        return sorted(
            (
                record
                for record in self._records.values()
                if record.correlation_id == correlation_id
            ),
            key=lambda record: (record.started_at, record.audit_id),
        )
