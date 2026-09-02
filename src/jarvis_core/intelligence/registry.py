"""Provider-neutral intelligence provider registry."""

from __future__ import annotations

from jarvis_core.intelligence.contracts import IntelligenceProvider
from jarvis_core.intelligence.errors import ProviderError, ProviderErrorCode


class ProviderRegistry:
    """Register and resolve intelligence providers by stable identifier."""

    def __init__(self) -> None:
        self._providers: dict[str, IntelligenceProvider] = {}

    def register(self, provider: IntelligenceProvider) -> None:
        """Register or replace a provider instance."""

        self._providers[provider.provider_id] = provider

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
