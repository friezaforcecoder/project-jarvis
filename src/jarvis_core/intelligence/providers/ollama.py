"""Ollama intelligence provider adapter."""

from __future__ import annotations

from typing import Any

import httpx

from jarvis_core.intelligence.contracts import (
    ProviderCapability,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
)
from jarvis_core.intelligence.errors import ProviderError, ProviderErrorCode


class OllamaProvider:
    """Translate normalized provider requests to Ollama's local HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def provider_id(self) -> str:
        """Return the stable provider identifier."""

        return "ollama"

    @property
    def capabilities(self) -> frozenset[ProviderCapability]:
        """Return the provider capabilities available to the core."""

        return frozenset({ProviderCapability.TEXT})

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a non-streaming text response from Ollama."""

        payload = {
            "model": self._model,
            "stream": False,
            "messages": [self._to_ollama_message(message) for message in request.messages],
        }

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ProviderErrorCode.TIMEOUT,
                "Intelligence provider timed out.",
                provider_id=self.provider_id,
                model=self._model,
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                ProviderErrorCode.UNAVAILABLE,
                "Intelligence provider is unavailable.",
                provider_id=self.provider_id,
                model=self._model,
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderError(
                ProviderErrorCode.UNAVAILABLE,
                "Intelligence provider is unavailable.",
                provider_id=self.provider_id,
                model=self._model,
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Intelligence provider returned an error.",
                provider_id=self.provider_id,
                model=self._model,
                safe_metadata={"provider_status_code": response.status_code},
            )

        data = self._decode_response(response)
        message = data.get("message")
        if not isinstance(message, dict):
            raise self._invalid_response()

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise self._invalid_response()

        model = data.get("model", self._model)
        return ProviderResponse(
            output=content,
            model=model if isinstance(model, str) and model else self._model,
        )

    def _decode_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise self._invalid_response() from exc

        if not isinstance(data, dict):
            raise self._invalid_response()
        return data

    def _invalid_response(self) -> ProviderError:
        return ProviderError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Intelligence provider returned an invalid response.",
            provider_id=self.provider_id,
            model=self._model,
        )

    def _to_ollama_message(self, message: ProviderMessage) -> dict[str, str]:
        return {"role": message.role.value, "content": message.content}
