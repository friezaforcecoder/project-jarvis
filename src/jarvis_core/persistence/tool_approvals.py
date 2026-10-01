"""Transactional SQLite storage for Sentinel approval receipts."""

from __future__ import annotations

import hmac
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from jarvis_core.sentinel.approval import (
    ToolApprovalAlreadyConsumedError,
    ToolApprovalError,
    ToolApprovalExpiredError,
    ToolApprovalMismatchError,
    ToolApprovalNotFoundError,
    ToolApprovalPersistenceError,
    ToolApprovalRecord,
    ToolApprovalStatus,
    ToolApprovalUnavailableError,
)


class SQLiteToolApprovalRepository:
    """Persist approval receipts in SQLite with transactional guarantees."""

    _COLUMNS = (
        "approval_id, request_binding, status, created_at, expires_at, "
        "approved_at, consumed_at"
    )

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        mode = "ro" if read_only else "rw"
        uri = f"{self._database_path.resolve().as_uri()}?mode={mode}"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, record: ToolApprovalRecord) -> None:
        try:
            validated = ToolApprovalRecord.model_validate(record.model_dump())
            if validated.status is not ToolApprovalStatus.PENDING:
                raise ToolApprovalPersistenceError()
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO tool_approvals "
                        f"({self._COLUMNS}) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(validated.approval_id),
                            validated.request_binding,
                            validated.status.value,
                            self._format_timestamp(validated.created_at),
                            self._format_timestamp(validated.expires_at),
                            self._format_timestamp(validated.approved_at),
                            self._format_timestamp(validated.consumed_at),
                        ),
                    )
        except ToolApprovalError:
            raise
        except Exception as exc:
            raise ToolApprovalPersistenceError() from exc

    def get(self, approval_id: UUID) -> ToolApprovalRecord | None:
        try:
            with closing(self._connect(read_only=True)) as conn:
                row = conn.execute(
                    f"SELECT {self._COLUMNS} FROM tool_approvals WHERE approval_id = ?",
                    (str(approval_id),),
                ).fetchone()
            if row is None:
                return None
            return ToolApprovalRecord.model_validate(dict(row))
        except ToolApprovalError:
            raise
        except Exception as exc:
            raise ToolApprovalPersistenceError() from exc

    def grant(self, approval_id: UUID, *, now: datetime) -> ToolApprovalRecord:
        try:
            now_utc = self._normalize_now(now)
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        f"SELECT {self._COLUMNS} FROM tool_approvals WHERE approval_id = ?",
                        (str(approval_id),),
                    ).fetchone()
                    if row is None:
                        raise ToolApprovalNotFoundError()
                    status = ToolApprovalStatus(row["status"])
                    expires_at = datetime.fromisoformat(row["expires_at"])
                    if now_utc >= expires_at:
                        raise ToolApprovalExpiredError()
                    if status is not ToolApprovalStatus.PENDING:
                        raise ToolApprovalUnavailableError()
                    approved_at_iso = now_utc.isoformat(timespec="microseconds")
                    cursor = conn.execute(
                        "UPDATE tool_approvals SET status = ?, approved_at = ? "
                        "WHERE approval_id = ? AND status = ?",
                        (
                            ToolApprovalStatus.APPROVED.value,
                            approved_at_iso,
                            str(approval_id),
                            ToolApprovalStatus.PENDING.value,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ToolApprovalPersistenceError()
                    row = conn.execute(
                        f"SELECT {self._COLUMNS} FROM tool_approvals WHERE approval_id = ?",
                        (str(approval_id),),
                    ).fetchone()
                    return ToolApprovalRecord.model_validate(dict(row))
        except ToolApprovalError:
            raise
        except Exception as exc:
            raise ToolApprovalPersistenceError() from exc

    def consume(
        self,
        approval_id: UUID,
        request_binding: str,
        *,
        now: datetime,
    ) -> ToolApprovalRecord:
        try:
            now_utc = self._normalize_now(now)
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        f"SELECT {self._COLUMNS} FROM tool_approvals WHERE approval_id = ?",
                        (str(approval_id),),
                    ).fetchone()
                    if row is None:
                        raise ToolApprovalNotFoundError()
                    status = ToolApprovalStatus(row["status"])
                    expires_at = datetime.fromisoformat(row["expires_at"])
                    if now_utc >= expires_at:
                        raise ToolApprovalExpiredError()
                    if status is ToolApprovalStatus.CONSUMED:
                        raise ToolApprovalAlreadyConsumedError()
                    if status is not ToolApprovalStatus.APPROVED:
                        raise ToolApprovalUnavailableError()
                    stored_binding = row["request_binding"]
                    if not self._is_valid_binding(stored_binding):
                        raise ToolApprovalPersistenceError()
                    if not self._is_valid_binding(request_binding):
                        raise ToolApprovalPersistenceError()
                    if not hmac.compare_digest(
                        stored_binding.encode("ascii"),
                        request_binding.encode("ascii"),
                    ):
                        raise ToolApprovalMismatchError()
                    consumed_at_iso = now_utc.isoformat(timespec="microseconds")
                    cursor = conn.execute(
                        "UPDATE tool_approvals SET status = ?, consumed_at = ? "
                        "WHERE approval_id = ? AND status = ?",
                        (
                            ToolApprovalStatus.CONSUMED.value,
                            consumed_at_iso,
                            str(approval_id),
                            ToolApprovalStatus.APPROVED.value,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ToolApprovalPersistenceError()
                    row = conn.execute(
                        f"SELECT {self._COLUMNS} FROM tool_approvals WHERE approval_id = ?",
                        (str(approval_id),),
                    ).fetchone()
                    return ToolApprovalRecord.model_validate(dict(row))
        except ToolApprovalError:
            raise
        except Exception as exc:
            raise ToolApprovalPersistenceError() from exc

    @staticmethod
    def _normalize_now(now: datetime) -> datetime:
        if now.tzinfo is None:
            raise ToolApprovalPersistenceError()
        if now.utcoffset() is None:
            raise ToolApprovalPersistenceError()
        return now.astimezone(UTC)

    @staticmethod
    def _format_timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    @staticmethod
    def _is_valid_binding(value: object) -> bool:
        if not isinstance(value, str):
            return False
        if len(value) != 64:
            return False
        return all(character in "0123456789abcdef" for character in value)
