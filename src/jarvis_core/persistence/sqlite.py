"""SQLite initialization for JARVIS Core."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis_core.config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_migrations (name)
VALUES ('bootstrap-v0.1');
"""


def initialize_sqlite(settings: Settings) -> Path:
    """Create the configured SQLite database and bootstrap schema."""

    database_path = settings.database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(database_path) as connection:
            connection.executescript(_SCHEMA)
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to initialize SQLite database at {database_path}") from exc

    return database_path
