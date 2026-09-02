"""Command-line startup entry point for JARVIS Core."""

from __future__ import annotations

import uvicorn

from jarvis_core.config import load_settings
from jarvis_core.logging import configure_logging


def main() -> None:
    """Start the local JARVIS Core API server."""

    settings = load_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "jarvis_core.api:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
