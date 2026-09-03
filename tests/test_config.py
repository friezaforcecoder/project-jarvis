from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis_core import __version__
from jarvis_core.config import Settings, load_settings
from jarvis_core.identity import DEFAULT_SYSTEM_INSTRUCTION


def test_default_settings_use_bootstrap_values() -> None:
    settings = Settings()

    assert __version__ == "0.6.0"
    assert settings.service_name == "jarvis-core"
    assert settings.version == __version__
    assert settings.environment == "local"
    assert settings.database_path == Path("data/jarvis-core.sqlite3")
    assert settings.log_level == "INFO"
    assert settings.intelligence_provider == "ollama"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.provider_timeout_seconds == 60.0
    assert settings.chat_history_limit == 10
    assert settings.system_instruction == DEFAULT_SYSTEM_INSTRUCTION


def test_load_settings_reads_environment_mapping() -> None:
    settings = load_settings(
        {
            "JARVIS_ENVIRONMENT": "test",
            "JARVIS_DATABASE_PATH": "runtime/test.sqlite3",
            "JARVIS_LOG_LEVEL": "debug",
            "JARVIS_HOST": "0.0.0.0",
            "JARVIS_PORT": "8123",
            "JARVIS_INTELLIGENCE_PROVIDER": "fake",
            "JARVIS_OLLAMA_BASE_URL": "http://ollama.test:11434",
            "JARVIS_OLLAMA_MODEL": "jarvis-test",
            "JARVIS_PROVIDER_TIMEOUT_SECONDS": "4.5",
            "JARVIS_CHAT_HISTORY_LIMIT": "7",
            "JARVIS_SYSTEM_INSTRUCTION": "Custom identity.",
        }
    )

    assert settings.environment == "test"
    assert settings.database_path == Path("runtime/test.sqlite3")
    assert settings.log_level == "DEBUG"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8123
    assert settings.intelligence_provider == "fake"
    assert settings.ollama_base_url == "http://ollama.test:11434"
    assert settings.ollama_model == "jarvis-test"
    assert settings.provider_timeout_seconds == 4.5
    assert settings.chat_history_limit == 7
    assert settings.system_instruction == "Custom identity."


def test_settings_reject_invalid_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="loud")


def test_settings_reject_invalid_provider_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(provider_timeout_seconds=0)


def test_settings_reject_invalid_chat_history_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(chat_history_limit=-1)
