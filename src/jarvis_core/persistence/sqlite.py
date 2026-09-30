"""SQLite initialization for JARVIS Core."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from jarvis_core.config import Settings

_BOOTSTRAP_MIGRATION = "bootstrap-v0.1"
_WORKING_MEMORY_MIGRATION = "working-memory-v0.3"
_TOOL_AUDIT_MIGRATION = "tool-audit-v0.9"


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _apply_bootstrap_migration(connection: sqlite3.Connection) -> None:
    _ensure_migration_table(connection)


def _apply_working_memory_migration(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            correlation_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id)
                REFERENCES conversation_sessions(id)
                ON DELETE CASCADE,
            UNIQUE (session_id, sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_sequence
        ON conversation_messages (session_id, sequence)
        """
    )


def _apply_tool_audit_migration(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_execution_audits (
            audit_id TEXT PRIMARY KEY NOT NULL CHECK (length(audit_id) > 0),
            correlation_id TEXT NOT NULL CHECK (length(correlation_id) > 0),
            tool_name TEXT NOT NULL CHECK (length(tool_name) > 0),
            side_effect_level TEXT CHECK (side_effect_level IN ('none', 'read', 'write', 'dangerous')),
            execution_boundary TEXT CHECK (execution_boundary IN ('core', 'user_space', 'external_service')),
            sentinel_decision TEXT CHECK (sentinel_decision IN ('allow', 'ask', 'deny')),
            outcome TEXT NOT NULL CHECK (outcome IN (
                'started', 'tool_not_found', 'invalid_arguments', 'approval_required',
                'denied', 'authorization_failed', 'succeeded', 'tool_failed',
                'internal_failure'
            )),
            error_code TEXT CHECK (error_code IN (
                'tool_duplicate', 'tool_not_found', 'tool_invalid_arguments',
                'tool_approval_required', 'tool_denied', 'tool_execution_failed',
                'sentinel_authorization_failed', 'tool_internal_error'
            )),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            CHECK (
                (outcome = 'started' AND completed_at IS NULL AND error_code IS NULL)
                OR (outcome != 'started' AND completed_at IS NOT NULL)
            ),
            CHECK (outcome != 'succeeded' OR error_code IS NULL),
            CHECK (outcome IN ('started', 'succeeded') OR error_code IS NOT NULL),
            CHECK (audit_id != correlation_id),
            CHECK (completed_at IS NULL OR completed_at >= started_at)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tool_execution_audits_correlation_started_audit
        ON tool_execution_audits (correlation_id, started_at, audit_id)
        """
    )


_MIGRATIONS: tuple[tuple[str, Callable[[sqlite3.Connection], None]], ...] = (
    (_BOOTSTRAP_MIGRATION, _apply_bootstrap_migration),
    (_WORKING_MEMORY_MIGRATION, _apply_working_memory_migration),
    (_TOOL_AUDIT_MIGRATION, _apply_tool_audit_migration),
)


def _apply_migration(
    connection: sqlite3.Connection,
    migration_name: str,
    migration: Callable[[sqlite3.Connection], None],
) -> None:
    """Apply and record one migration in an explicit transaction."""

    try:
        connection.execute("BEGIN")
        migration(connection)
        connection.execute(
            "INSERT INTO schema_migrations (name) VALUES (?)",
            (migration_name,),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def initialize_sqlite(settings: Settings) -> Path:
    """Create the configured SQLite database and bootstrap schema."""

    database_path = settings.database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(database_path, isolation_level=None) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _ensure_migration_table(connection)
            for migration_name, migration in _MIGRATIONS:
                already_applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE name = ?",
                    (migration_name,),
                ).fetchone()
                if already_applied:
                    continue

                _apply_migration(connection, migration_name, migration)
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to initialize SQLite database at {database_path}") from exc

    return database_path
