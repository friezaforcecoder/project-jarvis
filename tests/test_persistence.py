from __future__ import annotations

import sqlite3

from jarvis_core.config import Settings
from jarvis_core.persistence import initialize_sqlite


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

    assert migration_names == {"bootstrap-v0.1"}
