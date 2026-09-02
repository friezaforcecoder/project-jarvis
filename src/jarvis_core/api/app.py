"""FastAPI application construction."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from jarvis_core.config import Settings, load_settings
from jarvis_core.intelligence import ChatService, ProviderRegistry
from jarvis_core.intelligence.providers import OllamaProvider
from jarvis_core.logging import configure_logging
from jarvis_core.persistence import SQLiteConversationRepository, initialize_sqlite
from jarvis_core.sentinel import DefaultSentinelPolicy, Sentinel
from jarvis_core.tools import ToolRegistry
from jarvis_core.tools.builtins import create_builtin_tool_registry
from jarvis_core.tools.router import ToolExecutionCoordinator

from .routes.chat import router as chat_router
from .routes.health import router as health_router
from .routes.tools import router as tools_router

logger = logging.getLogger(__name__)


def create_provider_registry(settings: Settings) -> ProviderRegistry:
    """Build the configured provider registry without provider network calls."""

    registry = ProviderRegistry()
    registry.register(
        OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    )
    return registry


def create_app(
    settings: Settings | None = None,
    provider_registry: ProviderRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    sentinel: Sentinel | None = None,
) -> FastAPI:
    """Build the JARVIS Core API application."""

    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.log_level)
    resolved_registry = provider_registry or create_provider_registry(resolved_settings)
    resolved_tool_registry = tool_registry or create_builtin_tool_registry()
    resolved_sentinel = sentinel or DefaultSentinelPolicy()

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
    fastapi_app.state.provider_registry = resolved_registry
    fastapi_app.state.tool_registry = resolved_tool_registry
    fastapi_app.state.sentinel = resolved_sentinel
    fastapi_app.state.tool_execution_coordinator = ToolExecutionCoordinator(
        resolved_tool_registry,
        resolved_sentinel,
    )
    fastapi_app.state.conversation_repository = SQLiteConversationRepository(
        resolved_settings.database_path
    )
    fastapi_app.state.chat_service = ChatService(
        resolved_settings,
        resolved_registry,
        fastapi_app.state.conversation_repository,
    )
    fastapi_app.include_router(chat_router, prefix="/v1")
    fastapi_app.include_router(health_router, prefix="/v1")
    fastapi_app.include_router(tools_router, prefix="/v1")
    return fastapi_app


app = create_app()
