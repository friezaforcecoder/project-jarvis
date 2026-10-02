"""Packaged local assets for the JARVIS Operator HUD."""

from pathlib import Path


def asset_path(filename: str) -> Path:
    """Return one known HUD asset path from the installed package."""

    return Path(__file__).with_name("static") / filename


__all__ = ["asset_path"]
