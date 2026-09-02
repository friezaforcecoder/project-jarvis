"""Provider-neutral chat routing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from jarvis_core.config import Settings
from jarvis_core.identity import resolve_system_instruction
from jarvis_core.intelligence.contracts import ProviderRequest
from jarvis_core.intelligence.errors import ProviderError
from jarvis_core.intelligence.registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatResult:
    """Provider-normalized chat result returned to the API layer."""

    message: str
    provider: str
    model: str
    correlation_id: str


class ChatService:
    """Route chat messages through the configured intelligence provider."""

    def __init__(self, settings: Settings, provider_registry: ProviderRegistry) -> None:
        self._settings = settings
        self._provider_registry = provider_registry

    async def chat(self, message: str, correlation_id: str) -> ChatResult:
        """Send a single text message through the configured default provider."""

        provider = self._provider_registry.resolve_default(self._settings.intelligence_provider)
        provider_request = ProviderRequest(
            prompt=message,
            system_instruction=resolve_system_instruction(self._settings.system_instruction),
            correlation_id=correlation_id,
        )
        started_at = perf_counter()
        logger.info(
            "chat_request_started",
            extra={
                "correlation_id": correlation_id,
                "provider": provider.provider_id,
            },
        )

        try:
            provider_response = await provider.generate(provider_request)
        except ProviderError as exc:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.warning(
                "chat_request_failed",
                extra={
                    "correlation_id": correlation_id,
                    "provider": exc.provider_id or provider.provider_id,
                    "model": exc.model,
                    "elapsed_ms": elapsed_ms,
                    "error_code": exc.code.value,
                    **exc.safe_metadata,
                },
            )
            raise

        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        logger.info(
            "chat_request_succeeded",
            extra={
                "correlation_id": correlation_id,
                "provider": provider.provider_id,
                "model": provider_response.model,
                "elapsed_ms": elapsed_ms,
            },
        )
        return ChatResult(
            message=provider_response.output,
            provider=provider.provider_id,
            model=provider_response.model,
            correlation_id=correlation_id,
        )
