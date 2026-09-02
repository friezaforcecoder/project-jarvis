from __future__ import annotations

import json

import httpx
import pytest

from jarvis_core.intelligence import ProviderError, ProviderErrorCode, ProviderRequest
from jarvis_core.intelligence.providers import OllamaProvider


@pytest.mark.anyio
async def test_ollama_provider_constructs_non_streaming_chat_request() -> None:
    captured_payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        assert str(request.url) == "http://ollama.test/api/chat"
        return httpx.Response(
            200,
            json={
                "model": "llama3.2",
                "message": {"role": "assistant", "content": "Hello from Ollama."},
                "done": True,
            },
        )

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="llama3.2",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    response = await provider.generate(
        ProviderRequest(
            prompt="Hello",
            system_instruction="You are JARVIS.",
            correlation_id="ollama-correlation",
        )
    )

    assert response.output == "Hello from Ollama."
    assert response.model == "llama3.2"
    assert captured_payloads == [
        {
            "model": "llama3.2",
            "stream": False,
            "messages": [
                {"role": "system", "content": "You are JARVIS."},
                {"role": "user", "content": "Hello"},
            ],
        }
    ]


@pytest.mark.anyio
async def test_ollama_provider_normalizes_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="llama3.2",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate(ProviderRequest(prompt="Hello", system_instruction="Identity"))

    assert exc_info.value.code is ProviderErrorCode.TIMEOUT
    assert exc_info.value.provider_id == "ollama"
    assert exc_info.value.model == "llama3.2"


@pytest.mark.anyio
async def test_ollama_provider_normalizes_connection_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("not running", request=request)

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="llama3.2",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate(ProviderRequest(prompt="Hello", system_instruction="Identity"))

    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE
    assert exc_info.value.provider_id == "ollama"


@pytest.mark.anyio
async def test_ollama_provider_normalizes_invalid_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant"}})

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="llama3.2",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate(ProviderRequest(prompt="Hello", system_instruction="Identity"))

    assert exc_info.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.anyio
async def test_ollama_provider_normalizes_non_success_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal"})

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="llama3.2",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate(ProviderRequest(prompt="Hello", system_instruction="Identity"))

    assert exc_info.value.code is ProviderErrorCode.REQUEST_FAILED
    assert exc_info.value.safe_metadata == {"provider_status_code": 500}
