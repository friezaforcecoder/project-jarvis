"""Persistence tests for Sentinel approval receipts."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import jarvis_core.persistence.tool_approvals as approval_persistence
from jarvis_core.config import Settings
from jarvis_core.persistence import SQLiteToolApprovalRepository, initialize_sqlite
from jarvis_core.sentinel import (
    APPROVAL_LIFETIME,
    ToolApprovalAlreadyConsumedError,
    ToolApprovalExpiredError,
    ToolApprovalMismatchError,
    ToolApprovalNotFoundError,
    ToolApprovalPersistenceError,
    ToolApprovalRecord,
    ToolApprovalStatus,
    ToolApprovalUnavailableError,
)

_BINDING = "0123456789abcdef" * 4
_CREATED_AT = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)


class _OffsetlessTimezone(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        return None

    def dst(self, value: datetime | None) -> None:
        return None

    def tzname(self, value: datetime | None) -> str:
        return "offsetless"


@pytest.fixture
def approval_store(tmp_path: Path) -> tuple[Path, SQLiteToolApprovalRepository]:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    return database_path, SQLiteToolApprovalRepository(database_path)


def _pending_record(
    *,
    approval_id: UUID | None = None,
    request_binding: str = _BINDING,
    created_at: datetime = _CREATED_AT,
    expires_at: datetime | None = None,
) -> ToolApprovalRecord:
    return ToolApprovalRecord(
        approval_id=approval_id or uuid4(),
        request_binding=request_binding,
        status=ToolApprovalStatus.PENDING,
        created_at=created_at,
        expires_at=expires_at or created_at + APPROVAL_LIFETIME,
        approved_at=None,
        consumed_at=None,
    )


def _grant(
    repository: SQLiteToolApprovalRepository,
    record: ToolApprovalRecord,
    *,
    now: datetime | None = None,
) -> ToolApprovalRecord:
    repository.create(record)
    return repository.grant(
        record.approval_id,
        now=now or record.created_at + timedelta(minutes=1),
    )


def test_create_and_get_round_trip_exact_record(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    database_path, repository = approval_store
    record = _pending_record()

    repository.create(record)

    assert repository.get(record.approval_id) == record
    assert repository.get(uuid4()) is None

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT approval_id, request_binding, status, created_at, expires_at,
                   approved_at, consumed_at
            FROM tool_approvals
            WHERE approval_id = ?
            """,
            (str(record.approval_id),),
        ).fetchone()

    assert row == (
        str(record.approval_id),
        record.request_binding,
        ToolApprovalStatus.PENDING.value,
        record.created_at.isoformat(timespec="microseconds"),
        record.expires_at.isoformat(timespec="microseconds"),
        None,
        None,
    )


def test_create_revalidates_and_requires_pending(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record().model_copy(
        update={
            "status": ToolApprovalStatus.APPROVED,
            "approved_at": _CREATED_AT + timedelta(minutes=1),
        }
    )

    with pytest.raises(ToolApprovalPersistenceError):
        repository.create(record)


def test_duplicate_create_uses_safe_persistence_error(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    database_path, repository = approval_store
    record = _pending_record()
    repository.create(record)

    with pytest.raises(ToolApprovalPersistenceError) as exc_info:
        repository.create(record)

    message = str(exc_info.value)
    assert message == ToolApprovalPersistenceError.safe_message
    assert str(database_path) not in message
    assert "UNIQUE" not in message
    assert "sqlite" not in message.lower()


def test_get_missing_database_is_read_only(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite3"
    repository = SQLiteToolApprovalRepository(database_path)

    with pytest.raises(ToolApprovalPersistenceError):
        repository.get(uuid4())

    assert not database_path.exists()


def test_grant_normalizes_aware_timestamp_and_preserves_identity(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record()
    repository.create(record)
    local_timezone = timezone(timedelta(hours=-5))
    local_now = datetime(2026, 1, 1, 7, 1, 0, 654321, tzinfo=local_timezone)
    expected_utc = datetime(2026, 1, 1, 12, 1, 0, 654321, tzinfo=UTC)

    approved = repository.grant(record.approval_id, now=local_now)

    assert approved.status is ToolApprovalStatus.APPROVED
    assert approved.approved_at == expected_utc
    assert approved.approval_id == record.approval_id
    assert approved.request_binding == record.request_binding
    assert approved.created_at == record.created_at
    assert approved.expires_at == record.expires_at
    assert approved.consumed_at is None
    assert repository.get(record.approval_id) == approved

    with pytest.raises(ToolApprovalUnavailableError):
        repository.grant(record.approval_id, now=expected_utc)


def test_grant_unknown_receipt(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store

    with pytest.raises(ToolApprovalNotFoundError):
        repository.grant(uuid4(), now=_CREATED_AT)


@pytest.mark.parametrize(
    "now",
    [
        _CREATED_AT + APPROVAL_LIFETIME,
        _CREATED_AT + APPROVAL_LIFETIME + timedelta(microseconds=1),
    ],
)
def test_grant_rejects_expired_receipt(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
    now: datetime,
) -> None:
    _, repository = approval_store
    record = _pending_record()
    repository.create(record)

    with pytest.raises(ToolApprovalExpiredError):
        repository.grant(record.approval_id, now=now)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 1, 1, 12, 1),
        datetime(2026, 1, 1, 12, 1, tzinfo=_OffsetlessTimezone()),
    ],
)
def test_grant_rejects_invalid_now(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
    now: datetime,
) -> None:
    _, repository = approval_store
    record = _pending_record()
    repository.create(record)

    with pytest.raises(ToolApprovalPersistenceError):
        repository.grant(record.approval_id, now=now)


def test_consume_requires_approved_receipt(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record()
    repository.create(record)

    with pytest.raises(ToolApprovalUnavailableError):
        repository.consume(
            record.approval_id,
            record.request_binding,
            now=record.created_at + timedelta(minutes=1),
        )


@pytest.mark.parametrize(
    "request_binding",
    ["", "a" * 63, "A" * 64, "g" * 64, "-" + "a" * 63],
)
def test_consume_rejects_malformed_binding(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
    request_binding: str,
) -> None:
    _, repository = approval_store
    record = _pending_record()
    _grant(repository, record)

    with pytest.raises(ToolApprovalPersistenceError):
        repository.consume(
            record.approval_id,
            request_binding,
            now=record.created_at + timedelta(minutes=2),
        )


def test_consume_rejects_valid_mismatched_binding(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record()
    _grant(repository, record)

    with pytest.raises(ToolApprovalMismatchError):
        repository.consume(
            record.approval_id,
            "b" * 64,
            now=record.created_at + timedelta(minutes=2),
        )


def test_consume_is_one_time_and_preserves_record(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record()
    approved = _grant(repository, record)
    consumed_at = record.created_at + timedelta(minutes=2)

    consumed = repository.consume(
        record.approval_id,
        record.request_binding,
        now=consumed_at,
    )

    assert consumed.status is ToolApprovalStatus.CONSUMED
    assert consumed.approval_id == approved.approval_id
    assert consumed.request_binding == approved.request_binding
    assert consumed.created_at == approved.created_at
    assert consumed.expires_at == approved.expires_at
    assert consumed.approved_at == approved.approved_at
    assert consumed.consumed_at == consumed_at
    assert repository.get(record.approval_id) == consumed

    with pytest.raises(ToolApprovalAlreadyConsumedError):
        repository.consume(
            record.approval_id,
            record.request_binding,
            now=consumed_at,
        )


def test_consume_rejects_exact_expiry(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    _, repository = approval_store
    record = _pending_record()
    _grant(repository, record)

    with pytest.raises(ToolApprovalExpiredError):
        repository.consume(
            record.approval_id,
            record.request_binding,
            now=record.expires_at,
        )


def test_consume_uses_constant_time_comparison(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, repository = approval_store
    record = _pending_record()
    _grant(repository, record)
    original_compare = approval_persistence.hmac.compare_digest
    calls: list[tuple[bytes, bytes]] = []

    def recording_compare(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return original_compare(left, right)

    monkeypatch.setattr(approval_persistence.hmac, "compare_digest", recording_compare)

    repository.consume(
        record.approval_id,
        record.request_binding,
        now=record.created_at + timedelta(minutes=2),
    )

    expected = record.request_binding.encode("ascii")
    assert calls == [(expected, expected)]


def test_concurrent_consumers_allow_exactly_one_success(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    database_path, repository = approval_store
    record = _pending_record()
    _grant(repository, record)
    barrier = threading.Barrier(2)
    consume_at = record.created_at + timedelta(minutes=2)

    def attempt_consume() -> ToolApprovalStatus | type[Exception]:
        competing_repository = SQLiteToolApprovalRepository(database_path)
        barrier.wait(timeout=5)
        try:
            result = competing_repository.consume(
                record.approval_id,
                record.request_binding,
                now=consume_at,
            )
        except Exception as exc:  # The exact result is asserted below.
            return type(exc)
        return result.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt_consume) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert results.count(ToolApprovalStatus.CONSUMED) == 1
    assert results.count(ToolApprovalAlreadyConsumedError) == 1
    final_record = repository.get(record.approval_id)
    assert final_record is not None
    assert final_record.status is ToolApprovalStatus.CONSUMED


def test_malformed_persisted_row_is_normalized_safely(
    approval_store: tuple[Path, SQLiteToolApprovalRepository],
) -> None:
    database_path, repository = approval_store
    record = _pending_record()
    repository.create(record)

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        setting = connection.execute("PRAGMA ignore_check_constraints").fetchone()
        if setting is None or setting[0] != 1:
            pytest.skip("SQLite does not support ignoring CHECK constraints")
        connection.execute(
            "UPDATE tool_approvals SET status = 'invalid' WHERE approval_id = ?",
            (str(record.approval_id),),
        )

    with pytest.raises(ToolApprovalPersistenceError) as exc_info:
        repository.get(record.approval_id)

    message = str(exc_info.value)
    assert message == ToolApprovalPersistenceError.safe_message
    assert str(database_path) not in message
    assert "invalid" not in message
