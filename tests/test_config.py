from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis_core import __version__
from jarvis_core.config import Settings, load_settings


def test_default_settings_use_bootstrap_values() -> None:
    settings = Settings()

    assert settings.service_name == "jarvis-core"
    assert settings.version == __version__
    assert settings.environment == "local"
    assert settings.database_path == Path("data/jarvis-core.sqlite3")
    assert settings.log_level == "INFO"


def test_load_settings_reads_environment_mapping() -> None:
    settings = load_settings(
        {
            "JARVIS_ENVIRONMENT": "test",
            "JARVIS_DATABASE_PATH": "runtime/test.sqlite3",
            "JARVIS_LOG_LEVEL": "debug",
            "JARVIS_HOST": "0.0.0.0",
            "JARVIS_PORT": "8123",
        }
    )

    assert settings.environment == "test"
    assert settings.database_path == Path("runtime/test.sqlite3")
    assert settings.log_level == "DEBUG"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8123


def test_settings_reject_invalid_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="loud")
