from __future__ import annotations

import json
import logging

from jarvis_core.logging import JsonLogFormatter


def test_json_log_formatter_emits_structured_record() -> None:
    record = logging.LogRecord(
        name="jarvis.tests",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="core_started",
        args=(),
        exc_info=None,
    )
    record.service = "jarvis-core"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "jarvis.tests"
    assert payload["message"] == "core_started"
    assert payload["service"] == "jarvis-core"
    assert "timestamp" in payload
