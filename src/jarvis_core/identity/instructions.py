"""Minimal JARVIS identity instructions for provider requests."""

from __future__ import annotations

DEFAULT_SYSTEM_INSTRUCTION = (
    "You are JARVIS, a local-first personal AI assistant. "
    "Be concise, helpful, and honest."
)


def resolve_system_instruction(configured_instruction: str | None) -> str:
    """Return the configured system instruction or the default JARVIS identity."""

    if configured_instruction and configured_instruction.strip():
        return configured_instruction.strip()
    return DEFAULT_SYSTEM_INSTRUCTION
