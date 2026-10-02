"""Structured JSON logging for the bootstrap service."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)
_APPROVAL_PATH_PATTERN = re.compile(
    r"(/v1/tool-approvals/)[^/?\s]+(/grant\b)",
    re.IGNORECASE,
)


def _redact_approval_path(value: object) -> object:
    if not isinstance(value, str):
        return value
    return _APPROVAL_PATH_PATTERN.sub(r"\1[redacted]\2", value)


class ApprovalCapabilityLogFilter(logging.Filter):
    """Redact approval capabilities from request paths before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_approval_path(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_approval_path(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_approval_path(value)
                for key, value in record.args.items()
            }
        return True


class JsonLogFormatter(logging.Formatter):
    """Format log records as compact JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logging with the bootstrap JSON formatter."""

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler()
    handler.addFilter(ApprovalCapabilityLogFilter())
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
