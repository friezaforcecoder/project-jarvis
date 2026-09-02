"""Safe conversation working-memory errors."""

from __future__ import annotations

from enum import StrEnum


class ConversationErrorCode(StrEnum):
    """Stable conversation error codes exposed at the API boundary."""

    SESSION_NOT_FOUND = "session_not_found"
    PERSISTENCE_FAILED = "conversation_persistence_failed"


class ConversationSessionNotFoundError(Exception):
    """Raised when a caller references a well-formed but unknown session."""

    def __init__(self, session_id: str) -> None:
        super().__init__("Conversation session was not found.")
        self.code = ConversationErrorCode.SESSION_NOT_FOUND
        self.safe_message = "Conversation session was not found."
        self.session_id = session_id


class ConversationPersistenceError(Exception):
    """Raised when conversation persistence cannot safely complete."""

    def __init__(self, safe_message: str = "Conversation persistence failed.") -> None:
        super().__init__(safe_message)
        self.code = ConversationErrorCode.PERSISTENCE_FAILED
        self.safe_message = safe_message
