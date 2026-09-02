"""FastAPI application construction."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from jarvis_core.config import Settings, load_settings
from jarvis_core.logging import configure_logging
from jarvis_core.persistence import initialize_sqlite

from .routes.health import router as health_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the JARVIS Core API application."""

    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        database_path = initialize_sqlite(resolved_settings)
        fastapi_app.state.database_path = database_path
        logger.info(
            "jarvis_core_started",
            extra={
                "service": resolved_settings.service_name,
                "database_path": str(database_path),
            },
        )
        try:
            yield
        finally:
            logger.info(
                "jarvis_core_stopped",
                extra={"service": resolved_settings.service_name},
            )

    fastapi_app = FastAPI(
        title="JARVIS Core",
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    fastapi_app.state.settings = resolved_settings
    fastapi_app.include_router(health_router, prefix="/v1")
    return fastapi_app


app = create_app()
