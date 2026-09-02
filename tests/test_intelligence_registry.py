from __future__ import annotations

import pytest

from jarvis_core.intelligence import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
)


class FakeProvider:
    provider_id = "fake"
    capabilities = frozenset({ProviderCapability.TEXT})

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(output=request.prompt, model="fake-model")


def test_registry_registers_and_resolves_default_provider() -> None:
    provider = FakeProvider()
    registry = ProviderRegistry()

    registry.register(provider)

    assert registry.resolve_default("fake") is provider


def test_registry_raises_normalized_unknown_provider_error() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ProviderError) as exc_info:
        registry.resolve_default("missing")

    assert exc_info.value.code is ProviderErrorCode.UNKNOWN_PROVIDER
    assert exc_info.value.provider_id == "missing"
