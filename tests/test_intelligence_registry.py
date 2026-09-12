from __future__ import annotations

from unittest.mock import AsyncMock

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
    def __init__(
        self,
        provider_id: str = "fake",
        capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.TEXT}),
    ) -> None:
        self.provider_id = provider_id
        self.capabilities = capabilities

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(output=request.messages[-1].content, model="fake-model")


def test_registry_registers_and_resolves_default_provider() -> None:
    provider = FakeProvider()
    registry = ProviderRegistry()

    registry.register(provider)

    assert registry.get("fake") is provider
    assert registry.resolve_default("fake") is provider


@pytest.mark.parametrize("lookup", ["get", "resolve_default", "info"])
def test_registry_raises_normalized_unknown_provider_error(lookup: str) -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    with pytest.raises(ProviderError) as exc_info:
        getattr(registry, lookup)("missing")

    assert exc_info.value.code is ProviderErrorCode.UNKNOWN_PROVIDER
    assert exc_info.value.safe_message == "Configured intelligence provider is not registered."
    assert exc_info.value.provider_id == "missing"
    assert exc_info.value.model is None


@pytest.mark.parametrize(
    ("required", "expected_id"),
    [
        (frozenset({ProviderCapability.TEXT}), "text-only"),
        (frozenset({ProviderCapability.VISION}), "multimodal"),
        (frozenset({ProviderCapability.TEXT, ProviderCapability.VISION}), "multimodal"),
    ],
)
def test_registry_resolves_all_required_capabilities(
    required: frozenset[ProviderCapability],
    expected_id: str,
) -> None:
    registry = ProviderRegistry()
    providers = [
        FakeProvider("realtime-only", frozenset({ProviderCapability.REALTIME})),
        FakeProvider("text-only", frozenset({ProviderCapability.TEXT})),
        FakeProvider("multimodal", frozenset({ProviderCapability.TEXT, ProviderCapability.VISION})),
    ]
    for provider in providers:
        registry.register(provider)

    assert registry.resolve(required) is registry.get(expected_id)


@pytest.mark.parametrize(
    ("advertised", "required"),
    [
        ([], frozenset()),
        ([], frozenset({ProviderCapability.TEXT})),
        ([frozenset({ProviderCapability.TEXT})], frozenset({ProviderCapability.VISION})),
        (
            [frozenset({ProviderCapability.TEXT}), frozenset({ProviderCapability.VISION})],
            frozenset({ProviderCapability.TEXT, ProviderCapability.VISION}),
        ),
    ],
)
def test_registry_capability_miss_is_normalized(
    advertised: list[frozenset[ProviderCapability]],
    required: frozenset[ProviderCapability],
) -> None:
    registry = ProviderRegistry()
    for index, capabilities in enumerate(advertised):
        registry.register(FakeProvider(f"provider-{index}", capabilities))

    with pytest.raises(ProviderError) as exc_info:
        registry.resolve(required)

    error = exc_info.value
    assert error.code is ProviderErrorCode.UNAVAILABLE
    assert error.safe_message == (
        "No registered intelligence provider satisfies the required capabilities."
    )
    assert error.provider_id is None
    assert error.model is None
    assert error.safe_metadata == {}


def test_registry_empty_requirement_returns_first_even_without_capabilities() -> None:
    registry = ProviderRegistry()
    first = FakeProvider("z-first", frozenset())
    registry.register(first)
    registry.register(FakeProvider("a-second"))

    assert registry.resolve(frozenset()) is first
    assert registry.resolve_default("z-first") is first


def test_registry_replacement_refreshes_provider_and_preserves_selection_position() -> None:
    registry = ProviderRegistry()
    first = FakeProvider("z-first")
    second = FakeProvider("a-second")
    registry.register(first)
    registry.register(second)
    required = frozenset({ProviderCapability.TEXT})

    for _ in range(3):
        assert registry.resolve(required) is first

    replacement = FakeProvider("z-first", frozenset({ProviderCapability.VISION}))
    registry.register(replacement)
    assert registry.get("z-first") is replacement
    assert registry.resolve_default("z-first") is replacement
    assert registry.info("z-first").capabilities == frozenset({ProviderCapability.VISION})
    assert registry.resolve(required) is second
    assert registry.resolve(frozenset()) is replacement

    replacement.capabilities = required
    registry.register(replacement)
    for _ in range(3):
        assert registry.resolve(required) is replacement


def test_registry_capability_selection_ignores_provider_brand_or_name() -> None:
    registry = ProviderRegistry()
    named_ollama = FakeProvider("ollama", frozenset({ProviderCapability.VISION}))
    named_vision = FakeProvider("vision-provider", frozenset({ProviderCapability.TEXT}))
    registry.register(named_ollama)
    registry.register(named_vision)

    assert registry.resolve(frozenset({ProviderCapability.VISION})) is named_ollama
    assert registry.resolve(frozenset({ProviderCapability.TEXT})) is named_vision
    assert registry.resolve_default("ollama") is named_ollama


def test_registry_lookups_do_not_generate_or_execute_tools(monkeypatch) -> None:
    from jarvis_core.tools.router import ToolExecutionCoordinator

    provider = FakeProvider()
    generate = AsyncMock(side_effect=AssertionError("Lookup must not generate."))
    execute_tool = AsyncMock(side_effect=AssertionError("Lookup must not execute tools."))
    monkeypatch.setattr(provider, "generate", generate)
    monkeypatch.setattr(ToolExecutionCoordinator, "execute", execute_tool)
    registry = ProviderRegistry()

    registry.register(provider)
    assert registry.info("fake").provider_id == "fake"
    assert registry.get("fake") is provider
    assert registry.resolve_default("fake") is provider
    assert registry.resolve(frozenset({ProviderCapability.TEXT})) is provider
    assert registry.resolve(frozenset()) is provider
    with pytest.raises(ProviderError):
        registry.resolve(frozenset({ProviderCapability.STREAMING}))

    generate.assert_not_called()
    execute_tool.assert_not_called()
