"""Safe errors from the tool audit persistence boundary."""

from __future__ import annotations


class ToolAuditPersistenceError(Exception):
    """Raised when durable audit evidence cannot be safely read or written."""

    def __init__(self) -> None:
        self.safe_message = "Tool audit persistence failed."
        super().__init__(self.safe_message)
