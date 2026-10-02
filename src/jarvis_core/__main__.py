"""Command-line startup entry point for JARVIS Core."""

from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Sequence

import uvicorn

from jarvis_core.config import load_settings
from jarvis_core.logging import configure_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Start JARVIS Core.")
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_hud",
        help="Open the local Operator HUD when Core is healthy.",
    )
    return parser


def _hud_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}"


def _open_hud_when_ready(
    hud_url: str,
    *,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.2,
) -> bool:
    """Open the HUD only after the local health endpoint responds successfully."""

    deadline = time.monotonic() + timeout_seconds
    health_url = f"{hud_url}/v1/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    return webbrowser.open(hud_url)
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(poll_seconds)
    return False


def main(argv: Sequence[str] | None = None) -> None:
    """Start the local JARVIS Core API server."""

    args = _build_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(settings.log_level)
    if args.open_hud:
        threading.Thread(
            target=_open_hud_when_ready,
            args=(_hud_url(settings.host, settings.port),),
            name="jarvis-hud-opener",
            daemon=True,
        ).start()
    uvicorn.run(
        "jarvis_core.api:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
