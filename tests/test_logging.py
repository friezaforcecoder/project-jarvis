from __future__ import annotations

import json
import logging

from jarvis_core.logging import ApprovalCapabilityLogFilter, JsonLogFormatter


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


def test_approval_capability_filter_redacts_access_log_path() -> None:
    approval_id = "8f54eb4c-0df1-4707-aefa-85a54409394a"
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:50000",
            "POST",
            f"/v1/tool-approvals/{approval_id}/grant",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert ApprovalCapabilityLogFilter().filter(record) is True
    rendered = JsonLogFormatter().format(record)

    assert approval_id not in rendered
    assert "/v1/tool-approvals/[redacted]/grant" in rendered
