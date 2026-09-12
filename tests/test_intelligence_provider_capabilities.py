from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from jarvis_core.intelligence import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderInfo,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
)
from jarvis_core.intelligence.providers import OllamaProvider


class ConfiguredProvider:
    """An existing-protocol adapter whose private settings are not metadata."""

    __slots__ = ("provider_id", "capabilities", "api_key", "settings")

    def __init__(self) -> None:
        self.provider_id = "configured-test"
        self.capabilities = frozenset({ProviderCapability.TEXT, ProviderCapability.VISION})
        self.api_key = "FAKE_API_KEY_SENTINEL"
        self.settings = {
            "endpoint": "https://fake-endpoint-sentinel.invalid",
            "credential_file": "C:/fake-credential-path-sentinel/key.txt",
            "environment": "FAKE_ENVIRONMENT_VALUE_SENTINEL",
            "prompt": "FAKE_PROMPT_SENTINEL",
        }

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("Metadata and resolution must not generate.")


def test_provider_capability_labels_match_the_provider_neutral_contract() -> None:
    assert {capability.name: capability.value for capability in ProviderCapability} == {
        "TEXT": "text",
        "TOOL_USE": "tool_use",
        "VISION": "vision",
        "REALTIME": "realtime",
        "STREAMING": "streaming",
    }


def test_provider_info_copies_input_into_an_immutable_capability_collection() -> None:
    capabilities = {"text", "vision"}
    info = ProviderInfo.model_validate({"provider_id": "fake", "capabilities": capabilities})
    capabilities.add("streaming")

    assert info.capabilities == frozenset({ProviderCapability.TEXT, ProviderCapability.VISION})
    assert isinstance(info.capabilities, frozenset)
    assert all(isinstance(capability, ProviderCapability) for capability in info.capabilities)
    with pytest.raises(AttributeError):
        info.capabilities.add(ProviderCapability.STREAMING)


@pytest.mark.parametrize(
    ("field", "value"),
    [("provider_id", "replacement"), ("capabilities", frozenset())],
)
def test_provider_info_fields_are_frozen(field: str, value: object) -> None:
    info = ProviderInfo(provider_id="fake", capabilities=frozenset({ProviderCapability.TEXT}))

    with pytest.raises(ValidationError) as exc_info:
        setattr(info, field, value)

    assert exc_info.value.errors()[0]["type"] == "frozen_instance"
    assert info.provider_id == "fake"
    assert info.capabilities == frozenset({ProviderCapability.TEXT})


@pytest.mark.parametrize(
    "extra_field",
    ["api_key", "environment", "endpoint", "credential_file", "health", "local", "fallback_family"],
)
def test_provider_info_rejects_secret_and_unimplemented_fields(extra_field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProviderInfo.model_validate(
            {"provider_id": "fake", "capabilities": ["text"], extra_field: "FAKE_SENTINEL"}
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    "data",
    [
        {"provider_id": "", "capabilities": ["text"]},
        {"provider_id": "fake", "capabilities": ["not-a-capability"]},
    ],
)
def test_provider_info_rejects_invalid_identifiers_and_capabilities(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProviderInfo.model_validate(data)


def test_registry_preserves_snapshot_until_explicit_reregistration() -> None:
    provider = ConfiguredProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    original_info = registry.info(provider.provider_id)
    original_capabilities = frozenset({ProviderCapability.TEXT, ProviderCapability.VISION})

    assert original_info.capabilities == original_capabilities
    provider.capabilities = frozenset({ProviderCapability.STREAMING})

    assert registry.info(provider.provider_id).capabilities == original_capabilities
    assert registry.resolve(original_capabilities) is provider
    with pytest.raises(ProviderError) as exc_info:
        registry.resolve(frozenset({ProviderCapability.STREAMING}))
    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE

    with pytest.raises(ValidationError):
        registry.info(provider.provider_id).capabilities = provider.capabilities
    assert registry.resolve(original_capabilities) is provider

    registry.register(provider)
    assert registry.info(provider.provider_id).capabilities == provider.capabilities
    assert registry.resolve(frozenset({ProviderCapability.STREAMING})) is provider
    assert original_info.capabilities == original_capabilities
    with pytest.raises(ProviderError):
        registry.resolve(original_capabilities)


def test_metadata_and_capability_errors_do_not_expose_adapter_configuration(caplog) -> None:
    provider = ConfiguredProvider()
    registry = ProviderRegistry()
    caplog.set_level(logging.DEBUG, logger="jarvis_core.intelligence.registry")
    registry.register(provider)
    info = registry.info(provider.provider_id)

    serialized = info.model_dump_json()
    payload = json.loads(serialized)
    assert set(payload) == {"provider_id", "capabilities"}
    assert payload["provider_id"] == provider.provider_id
    assert set(payload["capabilities"]) == {"text", "vision"}
    assert registry.resolve(frozenset({ProviderCapability.VISION})) is provider
    with pytest.raises(ProviderError) as exc_info:
        registry.resolve(frozenset({ProviderCapability.REALTIME}))

    error = exc_info.value
    assert error.safe_message == (
        "No registered intelligence provider satisfies the required capabilities."
    )
    assert error.provider_id is None
    assert error.model is None
    assert error.safe_metadata == {}
    observable = serialized + str(error) + repr(error.__dict__) + caplog.text
    observable += repr([record.__dict__ for record in caplog.records])
    for sentinel in [provider.api_key, *provider.settings.values()]:
        assert sentinel not in observable


def test_ollama_metadata_is_text_only_and_does_not_probe_the_provider() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("Registry must not contact Ollama.")

    endpoint = "http://fake-ollama-endpoint-sentinel.invalid"
    model = "fake-tool-vision-realtime-streaming-model-sentinel"
    provider = OllamaProvider(
        base_url=endpoint,
        model=model,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    registry = ProviderRegistry()
    registry.register(provider)
    info = registry.info("ollama")

    assert provider.capabilities == frozenset({ProviderCapability.TEXT})
    assert info.capabilities == frozenset({ProviderCapability.TEXT})
    assert json.loads(info.model_dump_json()) == {"provider_id": "ollama", "capabilities": ["text"]}
    assert endpoint not in info.model_dump_json()
    assert model not in info.model_dump_json()
    assert registry.resolve(frozenset({ProviderCapability.TEXT})) is provider
    assert registry.resolve_default("ollama") is provider
    for unsupported in ProviderCapability:
        if unsupported is not ProviderCapability.TEXT:
            with pytest.raises(ProviderError) as exc_info:
                registry.resolve(frozenset({unsupported}))
            assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE
    assert requests == []
