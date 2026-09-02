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

    assert migration_names == {"bootstrap-v0.1", "working-memory-v0.3"}


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
