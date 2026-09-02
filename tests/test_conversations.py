from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis_core.config import Settings
from jarvis_core.conversations import ConversationPersistenceError
from jarvis_core.persistence import SQLiteConversationRepository, initialize_sqlite

SESSION_ID = "11111111-1111-4111-8111-111111111111"


def migration_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }


def table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def message_rows(database_path: Path, session_id: str = SESSION_ID) -> list[sqlite3.Row]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT sequence, role, content, correlation_id
            FROM conversation_messages
            WHERE session_id = ?
            ORDER BY sequence
            """,
            (session_id,),
        ).fetchall()


def create_failure_trigger(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_assistant_insert
            BEFORE INSERT ON conversation_messages
            WHEN NEW.role = 'assistant'
            BEGIN
                SELECT RAISE(FAIL, 'assistant insert failed');
            END
            """
        )


def test_initialize_sqlite_creates_fresh_working_memory_schema(tmp_path) -> None:
    database_path = tmp_path / "fresh.sqlite3"

    initialize_sqlite(Settings(database_path=database_path))

    assert migration_names(database_path) == {"bootstrap-v0.1", "working-memory-v0.3"}
    assert {"conversation_sessions", "conversation_messages"}.issubset(
        table_names(database_path)
    )


def test_initialize_sqlite_upgrades_existing_v2_bootstrap_schema_in_place(tmp_path) -> None:
    database_path = tmp_path / "upgrade.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("INSERT INTO schema_migrations (name) VALUES ('bootstrap-v0.1')")
        connection.execute("CREATE TABLE existing_data (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO existing_data (id, value) VALUES ('keep', 'safe')")

    initialize_sqlite(Settings(database_path=database_path))

    assert migration_names(database_path) == {"bootstrap-v0.1", "working-memory-v0.3"}
    with sqlite3.connect(database_path) as connection:
        existing_value = connection.execute(
            "SELECT value FROM existing_data WHERE id = 'keep'"
        ).fetchone()[0]
    assert existing_value == "safe"


def test_repository_appends_successful_turns_with_deterministic_sequences(tmp_path) -> None:
    database_path = tmp_path / "turns.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    repository = SQLiteConversationRepository(database_path)

    repository.append_successful_turn(
        session_id=SESSION_ID,
        user_content="u1",
        assistant_content="a1",
        correlation_id="c1",
        create_session=True,
    )
    repository.append_successful_turn(
        session_id=SESSION_ID,
        user_content="u2",
        assistant_content="a2",
        correlation_id="c2",
        create_session=False,
    )
    repository.append_successful_turn(
        session_id=SESSION_ID,
        user_content="u3",
        assistant_content="a3",
        correlation_id="c3",
        create_session=False,
    )

    rows = message_rows(database_path)
    assert [(row["sequence"], row["role"], row["content"]) for row in rows] == [
        (1, "user", "u1"),
        (2, "assistant", "a1"),
        (3, "user", "u2"),
        (4, "assistant", "a2"),
        (5, "user", "u3"),
        (6, "assistant", "a3"),
    ]


def test_repository_bounded_history_keeps_order_and_drops_orphaned_assistant(
    tmp_path,
) -> None:
    database_path = tmp_path / "history.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    repository = SQLiteConversationRepository(database_path)
    for index in range(1, 4):
        repository.append_successful_turn(
            session_id=SESSION_ID,
            user_content=f"u{index}",
            assistant_content=f"a{index}",
            correlation_id=f"c{index}",
            create_session=index == 1,
        )

    assert [
        (message.sequence, message.role.value, message.content)
        for message in repository.load_recent_messages(SESSION_ID, 4)
    ] == [
        (3, "user", "u2"),
        (4, "assistant", "a2"),
        (5, "user", "u3"),
        (6, "assistant", "a3"),
    ]
    assert [
        (message.sequence, message.role.value, message.content)
        for message in repository.load_recent_messages(SESSION_ID, 3)
    ] == [
        (5, "user", "u3"),
        (6, "assistant", "a3"),
    ]
    assert repository.load_recent_messages(SESSION_ID, 0) == []


def test_new_session_successful_turn_rolls_back_atomically_on_persistence_failure(
    tmp_path,
) -> None:
    database_path = tmp_path / "new-session-rollback.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    create_failure_trigger(database_path)
    repository = SQLiteConversationRepository(database_path)

    with pytest.raises(ConversationPersistenceError):
        repository.append_successful_turn(
            session_id=SESSION_ID,
            user_content="u1",
            assistant_content="a1",
            correlation_id="c1",
            create_session=True,
        )

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0] == 0


def test_existing_session_successful_turn_rolls_back_atomically_on_persistence_failure(
    tmp_path,
) -> None:
    database_path = tmp_path / "existing-session-rollback.sqlite3"
    initialize_sqlite(Settings(database_path=database_path))
    repository = SQLiteConversationRepository(database_path)
    repository.append_successful_turn(
        session_id=SESSION_ID,
        user_content="u1",
        assistant_content="a1",
        correlation_id="c1",
        create_session=True,
    )
    create_failure_trigger(database_path)

    with pytest.raises(ConversationPersistenceError):
        repository.append_successful_turn(
            session_id=SESSION_ID,
            user_content="u2",
            assistant_content="a2",
            correlation_id="c2",
            create_session=False,
        )

    rows = message_rows(database_path)
    assert [(row["sequence"], row["role"], row["content"]) for row in rows] == [
        (1, "user", "u1"),
        (2, "assistant", "a1"),
    ]
