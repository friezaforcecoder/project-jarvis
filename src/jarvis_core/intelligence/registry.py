"""Provider-neutral intelligence provider registry."""

from __future__ import annotations

from jarvis_core.intelligence.contracts import (
    IntelligenceProvider,
    ProviderCapability,
    ProviderInfo,
)
from jarvis_core.intelligence.errors import ProviderError, ProviderErrorCode


class ProviderRegistry:
    """Resolve providers by stable identifier or advertised capabilities."""

    def __init__(self) -> None:
        self._providers: dict[str, IntelligenceProvider] = {}
        self._provider_infos: dict[str, ProviderInfo] = {}

    def register(self, provider: IntelligenceProvider) -> None:
        """Snapshot public capabilities and register or replace a provider in place."""

        info = ProviderInfo(
            provider_id=provider.provider_id,
            capabilities=provider.capabilities,
        )
        self._providers[info.provider_id] = provider
        self._provider_infos[info.provider_id] = info

    def get(self, provider_id: str) -> IntelligenceProvider:
        """Return a provider by identifier or raise a normalized error."""

        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderError(
                ProviderErrorCode.UNKNOWN_PROVIDER,
                "Configured intelligence provider is not registered.",
                provider_id=provider_id,
            ) from exc

    def resolve_default(self, provider_id: str) -> IntelligenceProvider:
        """Resolve the configured default provider deterministically."""

        return self.get(provider_id)

    def info(self, provider_id: str) -> ProviderInfo:
        """Return immutable registration metadata, using the normal ID lookup error."""

        self.get(provider_id)
        return self._provider_infos[provider_id]

    def resolve(
        self, required_capabilities: frozenset[ProviderCapability]
    ) -> IntelligenceProvider:
        """Return the first registration supporting all requirements, without probing."""

        for provider_id, info in self._provider_infos.items():
            if required_capabilities.issubset(info.capabilities):
                return self._providers[provider_id]

        raise ProviderError(
            ProviderErrorCode.UNAVAILABLE,
            "No registered intelligence provider satisfies the required capabilities.",
        )
