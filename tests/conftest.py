from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from jarvis_core.api import create_app
from jarvis_core.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_path=tmp_path / "jarvis-core.sqlite3", log_level="WARNING")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
