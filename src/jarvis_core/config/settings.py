"""Typed configuration for JARVIS Core."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis_core import __version__
from jarvis_core.identity import DEFAULT_SYSTEM_INSTRUCTION

_ENVIRONMENT_VARIABLES = {
    "environment": "JARVIS_ENVIRONMENT",
    "database_path": "JARVIS_DATABASE_PATH",
    "log_level": "JARVIS_LOG_LEVEL",
    "host": "JARVIS_HOST",
    "port": "JARVIS_PORT",
    "intelligence_provider": "JARVIS_INTELLIGENCE_PROVIDER",
    "ollama_base_url": "JARVIS_OLLAMA_BASE_URL",
    "ollama_model": "JARVIS_OLLAMA_MODEL",
    "provider_timeout_seconds": "JARVIS_PROVIDER_TIMEOUT_SECONDS",
    "system_instruction": "JARVIS_SYSTEM_INSTRUCTION",
}

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(default="jarvis-core", min_length=1)
    version: str = Field(default=__version__, min_length=1)
    environment: str = Field(default="local", min_length=1)
    database_path: Path = Field(default=Path("data/jarvis-core.sqlite3"))
    log_level: str = Field(default="INFO")
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    intelligence_provider: str = Field(default="ollama", min_length=1)
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", min_length=1)
    ollama_model: str = Field(default="llama3.2", min_length=1)
    provider_timeout_seconds: float = Field(default=30.0, gt=0)
    system_instruction: str = Field(default=DEFAULT_SYSTEM_INSTRUCTION, min_length=1)

    @field_validator("database_path", mode="before")
    @classmethod
    def coerce_database_path(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value)
        raise TypeError("database_path must be a filesystem path")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_LOG_LEVELS)}")
        return normalized

    @field_validator(
        "intelligence_provider",
        "ollama_base_url",
        "ollama_model",
        "system_instruction",
    )
    @classmethod
    def strip_non_empty_string(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Load settings from the process environment or a supplied mapping."""

    source = os.environ if env is None else env
    values = {
        field_name: source[environment_variable]
        for field_name, environment_variable in _ENVIRONMENT_VARIABLES.items()
        if environment_variable in source
    }
    return Settings(**values)
