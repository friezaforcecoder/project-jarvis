from __future__ import annotations

import sqlite3

import pytest

from jarvis_core.config import Settings
from jarvis_core.persistence import initialize_sqlite
import jarvis_core.persistence.sqlite as sqlite_persistence


def test_initialize_sqlite_creates_database_and_schema(tmp_path) -> None:
    database_path = tmp_path / "nested" / "jarvis.sqlite3"
    settings = Settings(database_path=database_path)

    returned_path = initialize_sqlite(settings)

    assert returned_path == database_path
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        migration_names = {
            row[0]
            for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }

    assert migration_names == {
        "bootstrap-v0.1",
        "working-memory-v0.3",
        "tool-audit-v0.9",
        "sentinel-approval-v0.10",
    }


def test_initialize_sqlite_rolls_back_failed_migration(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "jarvis.sqlite3"

    def failing_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE partial_migration_schema (id TEXT PRIMARY KEY)")
        raise sqlite3.OperationalError("migration failed")

    monkeypatch.setattr(
        sqlite_persistence,
        "_MIGRATIONS",
        (
            (
                sqlite_persistence._BOOTSTRAP_MIGRATION,
                sqlite_persistence._apply_bootstrap_migration,
            ),
            ("failing-v-test", failing_migration),
        ),
    )

    with pytest.raises(RuntimeError):
        initialize_sqlite(Settings(database_path=database_path))

    with sqlite3.connect(database_path) as connection:
        migration_names = {
            row[0]
            for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "bootstrap-v0.1" in migration_names
    assert "failing-v-test" not in migration_names
    assert "partial_migration_schema" not in table_names


def _insert_tool_approval(
    connection: sqlite3.Connection,
    *,
    approval_id: str,
    request_binding: str,
    status: str,
    created_at: str,
    expires_at: str,
    approved_at: str | None,
    consumed_at: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO tool_approvals (
            approval_id,
            request_binding,
            status,
            created_at,
            expires_at,
            approved_at,
            consumed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            approval_id,
            request_binding,
            status,
            created_at,
            expires_at,
            approved_at,
            consumed_at,
        ),
    )


def test_tool_approvals_has_exact_columns(tmp_path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))

    with sqlite3.connect(database_path) as connection:
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(tool_approvals)").fetchall()
        ]

    assert columns == [
        "approval_id",
        "request_binding",
        "status",
        "created_at",
        "expires_at",
        "approved_at",
        "consumed_at",
    ]


def test_tool_approvals_rejects_malformed_rows(tmp_path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))

    valid_binding = "0123456789abcdef" * 4
    created_at = "2026-01-01T00:00:00+00:00"
    expires_at = "2026-01-01T01:00:00+00:00"

    invalid_rows = [
        {
            "approval_id": "",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-short-binding",
            "request_binding": valid_binding[:63],
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-long-binding",
            "request_binding": valid_binding + "a",
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-uppercase-binding",
            "request_binding": valid_binding.upper(),
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-non-hex-binding",
            "request_binding": "g" + "a" * 63,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-invalid-status",
            "request_binding": valid_binding,
            "status": "expired",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-expiration-equal",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": created_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-expiration-less",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": "2025-12-31T23:00:00+00:00",
            "approved_at": None,
            "consumed_at": None,
        },
    ]

    for row in invalid_rows:
        with pytest.raises(sqlite3.IntegrityError):
            with sqlite3.connect(database_path) as connection:
                _insert_tool_approval(connection, **row)
                connection.commit()


def test_tool_approvals_rejects_invalid_lifecycle_states(tmp_path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))

    valid_binding = "0123456789abcdef" * 4
    created_at = "2026-01-01T00:00:00+00:00"
    expires_at = "2026-01-01T01:00:00+00:00"
    approved_at = "2026-01-01T00:30:00+00:00"
    consumed_at = "2026-01-01T00:45:00+00:00"

    invalid_rows = [
        {
            "approval_id": "approval-pending-approved",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-pending-consumed",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": consumed_at,
        },
        {
            "approval_id": "approval-approved-missing-approved",
            "request_binding": valid_binding,
            "status": "approved",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-approved-consumed",
            "request_binding": valid_binding,
            "status": "approved",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": consumed_at,
        },
        {
            "approval_id": "approval-approved-before-created",
            "request_binding": valid_binding,
            "status": "approved",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": "2025-12-31T23:00:00+00:00",
            "consumed_at": None,
        },
        {
            "approval_id": "approval-approved-after-expires",
            "request_binding": valid_binding,
            "status": "approved",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": "2026-01-01T02:00:00+00:00",
            "consumed_at": None,
        },
        {
            "approval_id": "approval-consumed-missing-approved",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": consumed_at,
        },
        {
            "approval_id": "approval-consumed-missing-consumed",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-consumed-approved-before-created",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": "2025-12-31T23:00:00+00:00",
            "consumed_at": consumed_at,
        },
        {
            "approval_id": "approval-consumed-before-approved",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": "2026-01-01T00:20:00+00:00",
        },
        {
            "approval_id": "approval-consumed-after-expires",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": "2026-01-01T02:00:00+00:00",
        },
    ]

    for row in invalid_rows:
        with pytest.raises(sqlite3.IntegrityError):
            with sqlite3.connect(database_path) as connection:
                _insert_tool_approval(connection, **row)
                connection.commit()


def test_tool_approvals_accepts_valid_lifecycle_states(tmp_path) -> None:
    database_path = tmp_path / "jarvis.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))

    valid_binding = "0123456789abcdef" * 4
    created_at = "2026-01-01T00:00:00+00:00"
    expires_at = "2026-01-01T01:00:00+00:00"
    approved_at = "2026-01-01T00:30:00+00:00"
    consumed_at = "2026-01-01T00:45:00+00:00"

    valid_rows = [
        {
            "approval_id": "approval-pending",
            "request_binding": valid_binding,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": None,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-approved",
            "request_binding": valid_binding,
            "status": "approved",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": None,
        },
        {
            "approval_id": "approval-consumed",
            "request_binding": valid_binding,
            "status": "consumed",
            "created_at": created_at,
            "expires_at": expires_at,
            "approved_at": approved_at,
            "consumed_at": consumed_at,
        },
    ]

    with sqlite3.connect(database_path) as connection:
        for row in valid_rows:
            _insert_tool_approval(connection, **row)
        connection.commit()

    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT count(*) FROM tool_approvals").fetchone()[0]

    assert count == 3


def test_sentinel_approval_migration_preserves_existing_tool_audits(tmp_path) -> None:
    database_path = tmp_path / "upgrade.sqlite3"
    with sqlite3.connect(database_path, isolation_level=None) as connection:
        sqlite_persistence._ensure_migration_table(connection)
        for migration_name, migration in sqlite_persistence._MIGRATIONS[:3]:
            sqlite_persistence._apply_migration(
                connection,
                migration_name,
                migration,
            )
        connection.execute(
            """
            INSERT INTO tool_execution_audits (
                audit_id, correlation_id, tool_name, side_effect_level,
                execution_boundary, sentinel_decision, outcome, error_code,
                started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "7dc38f4f-0ef4-47a8-92fe-2830413a43c1",
                "preserved-correlation",
                "test.read",
                "read",
                "core",
                "allow",
                "succeeded",
                None,
                "2026-01-01T00:00:00.000000+00:00",
                "2026-01-01T00:00:01.000000+00:00",
            ),
        )

    initialize_sqlite(Settings(database_path=database_path))

    with sqlite3.connect(database_path) as connection:
        migration_names = {
            row[0]
            for row in connection.execute("SELECT name FROM schema_migrations")
        }
        audit = connection.execute(
            """
            SELECT audit_id, correlation_id, tool_name, side_effect_level,
                   execution_boundary, sentinel_decision, outcome, error_code,
                   started_at, completed_at
            FROM tool_execution_audits
            """
        ).fetchone()
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("tool_execution_audits",),
        ).fetchone()[0]

    assert "sentinel-approval-v0.10" in migration_names
    assert audit == (
        "7dc38f4f-0ef4-47a8-92fe-2830413a43c1",
        "preserved-correlation",
        "test.read",
        "read",
        "core",
        "allow",
        "succeeded",
        None,
        "2026-01-01T00:00:00.000000+00:00",
        "2026-01-01T00:00:01.000000+00:00",
    )
    assert "approval_expired" in table_sql
    assert "approval_invalid" in table_sql
    assert "tool_approval_expired" in table_sql
    assert "tool_approval_invalid" in table_sql
