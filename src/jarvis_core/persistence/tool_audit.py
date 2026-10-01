"""Transactional SQLite storage for allowlisted tool execution audit metadata."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from jarvis_core.audit import ToolAuditOutcome, ToolAuditPersistenceError, ToolAuditRecord

_COLUMNS = (
    "audit_id, correlation_id, tool_name, side_effect_level, execution_boundary, "
    "sentinel_decision, outcome, error_code, started_at, completed_at"
)
_IDENTITY_FIELDS = ("audit_id", "correlation_id", "tool_name", "started_at")
_OBSERVATION_FIELDS = ("side_effect_level", "execution_boundary", "sentinel_decision")


class SQLiteToolAuditRepository:
    """Persist each lifecycle snapshot atomically, leaving completed records unchanged."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = Path(database_path)

    def create(self, record: ToolAuditRecord) -> None:
        """Insert only an initial started record; never replace an existing audit ID."""

        try:
            validated = _validate_snapshot(record)
            if validated.outcome is not ToolAuditOutcome.STARTED:
                raise ToolAuditPersistenceError()
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        f"""
                        INSERT INTO tool_execution_audits ({_COLUMNS})
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _database_values(validated),
                    )
        except ToolAuditPersistenceError:
            raise
        except Exception as exc:
            raise ToolAuditPersistenceError() from exc

    def update(self, record: ToolAuditRecord) -> None:
        """Update a started record under one transaction; completion is irreversible."""

        try:
            validated = _validate_snapshot(record)
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    row = connection.execute(
                        f"SELECT {_COLUMNS} FROM tool_execution_audits WHERE audit_id = ?",
                        (validated.audit_id,),
                    ).fetchone()
                    if row is None:
                        raise ToolAuditPersistenceError()
                    previous = ToolAuditRecord.model_validate(dict(row))
                    _validate_transition(previous, validated)
                    values = _database_values(validated)
                    changed = connection.execute(
                        """
                        UPDATE tool_execution_audits
                        SET side_effect_level = ?, execution_boundary = ?, sentinel_decision = ?,
                            outcome = ?, error_code = ?, completed_at = ?
                        WHERE audit_id = ? AND outcome = 'started'
                        """,
                        (*values[3:8], values[9], validated.audit_id),
                    )
                    if changed.rowcount != 1:
                        raise ToolAuditPersistenceError()
        except ToolAuditPersistenceError:
            raise
        except Exception as exc:
            raise ToolAuditPersistenceError() from exc

    def list_for_correlation(self, correlation_id: str) -> list[ToolAuditRecord]:
        """Query through a read-only connection, without creating or migrating schema."""

        try:
            with closing(self._connect(read_only=True)) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {_COLUMNS} FROM tool_execution_audits
                    WHERE correlation_id = ?
                    ORDER BY started_at, audit_id
                    """,
                    (correlation_id,),
                ).fetchall()
            return [ToolAuditRecord.model_validate(dict(row)) for row in rows]
        except Exception as exc:
            raise ToolAuditPersistenceError() from exc

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        mode = "ro" if read_only else "rw"
        uri = self._database_path.resolve().as_uri() + f"?mode={mode}"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection


def _validate_snapshot(record: ToolAuditRecord) -> ToolAuditRecord:
    # Revalidate the public fields: Pydantic model_copy(update=...) skips validation.
    return ToolAuditRecord.model_validate(record.model_dump())


def _validate_transition(previous: ToolAuditRecord, candidate: ToolAuditRecord) -> None:
    if previous.outcome is not ToolAuditOutcome.STARTED:
        raise ToolAuditPersistenceError()
    if candidate.outcome is ToolAuditOutcome.STARTED:
        raise ToolAuditPersistenceError()
    if any(getattr(previous, field) != getattr(candidate, field) for field in _IDENTITY_FIELDS):
        raise ToolAuditPersistenceError()
    for field in _OBSERVATION_FIELDS:
        observed = getattr(previous, field)
        if observed is not None and getattr(candidate, field) != observed:
            raise ToolAuditPersistenceError()


def _database_values(record: ToolAuditRecord) -> tuple[object, ...]:
    return (
        record.audit_id,
        record.correlation_id,
        record.tool_name,
        record.side_effect_level.value if record.side_effect_level is not None else None,
        record.execution_boundary.value if record.execution_boundary is not None else None,
        record.sentinel_decision.value if record.sentinel_decision is not None else None,
        record.outcome.value,
        record.error_code.value if record.error_code is not None else None,
        record.started_at.isoformat(timespec="microseconds"),
        (
            record.completed_at.isoformat(timespec="microseconds")
            if record.completed_at is not None
            else None
        ),
    )
