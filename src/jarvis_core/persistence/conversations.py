"""SQLite conversation working-memory repository."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jarvis_core.conversations import (
    ConversationMessage,
    ConversationMessageRole,
    ConversationPersistenceError,
    ConversationSessionNotFoundError,
)


class SQLiteConversationRepository:
    """Persist conversation sessions and messages in SQLite."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def session_exists(self, session_id: str) -> bool:
        """Return whether a durable session exists."""

        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT 1 FROM conversation_sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise ConversationPersistenceError() from exc
        return row is not None

    def load_recent_messages(self, session_id: str, limit: int) -> list[ConversationMessage]:
        """Load recent messages in conversational order, dropping orphaned assistant context."""

        if limit <= 0:
            return []

        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT id, session_id, sequence, role, content, correlation_id, created_at
                    FROM conversation_messages
                    WHERE session_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise ConversationPersistenceError() from exc

        messages = [self._message_from_row(row) for row in reversed(rows)]
        if messages and messages[0].role is ConversationMessageRole.ASSISTANT:
            messages = messages[1:]
        return messages

    def append_successful_turn(
        self,
        *,
        session_id: str,
        user_content: str,
        assistant_content: str,
        correlation_id: str,
        create_session: bool,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Atomically persist a successful user/assistant exchange."""

        now = _utc_now()
        user_message = ConversationMessage(
            id=str(uuid4()),
            session_id=session_id,
            sequence=1,
            role=ConversationMessageRole.USER,
            content=user_content,
            correlation_id=correlation_id,
            created_at=now,
        )
        assistant_message = ConversationMessage(
            id=str(uuid4()),
            session_id=session_id,
            sequence=2,
            role=ConversationMessageRole.ASSISTANT,
            content=assistant_content,
            correlation_id=correlation_id,
            created_at=now,
        )

        try:
            with closing(self._connect()) as connection:
                with connection:
                    if create_session:
                        connection.execute(
                            """
                            INSERT INTO conversation_sessions (id, created_at, updated_at)
                            VALUES (?, ?, ?)
                            """,
                            (session_id, _to_database_timestamp(now), _to_database_timestamp(now)),
                        )
                    else:
                        updated = connection.execute(
                            """
                            UPDATE conversation_sessions
                            SET updated_at = ?
                            WHERE id = ?
                            """,
                            (_to_database_timestamp(now), session_id),
                        )
                        if updated.rowcount != 1:
                            raise ConversationSessionNotFoundError(session_id)

                    next_sequence = self._next_sequence(connection, session_id)
                    user_message = user_message.model_copy(update={"sequence": next_sequence})
                    assistant_message = assistant_message.model_copy(
                        update={"sequence": next_sequence + 1}
                    )
                    self._insert_message(connection, user_message)
                    self._insert_message(connection, assistant_message)
        except ConversationSessionNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise ConversationPersistenceError() from exc

        return user_message, assistant_message

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _next_sequence(self, connection: sqlite3.Connection, session_id: str) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM conversation_messages
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return int(row[0])

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        message: ConversationMessage,
    ) -> None:
        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, session_id, sequence, role, content, correlation_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.session_id,
                message.sequence,
                message.role.value,
                message.content,
                message.correlation_id,
                _to_database_timestamp(message.created_at),
            ),
        )

    def _message_from_row(self, row: sqlite3.Row) -> ConversationMessage:
        return ConversationMessage(
            id=row["id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            role=ConversationMessageRole(row["role"]),
            content=row["content"],
            correlation_id=row["correlation_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _to_database_timestamp(value: datetime) -> str:
    return value.isoformat()
