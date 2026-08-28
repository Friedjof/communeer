from functools import lru_cache

from communeer.config import get_settings
from communeer.providers.whatsapp.base import (
    ProviderCommunity,
    ProviderGroup,
    ProviderMember,
    ProviderMembership,
    WhatsAppProvider,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.providers.whatsapp.wppconnect import WppconnectProvider

__all__ = [
    "MockWhatsAppProvider",
    "ProviderCommunity",
    "ProviderGroup",
    "ProviderMember",
    "ProviderMembership",
    "WhatsAppProvider",
    "WppconnectProvider",
    "get_provider",
]


@lru_cache
def get_provider() -> WhatsAppProvider:
    """Provider seam: `WHATSAPP_PROVIDER` env var picks the implementation.

    `mock` (default) or `wppconnect` for a real WPPConnect Server-backed
    session. The provider instance is cached for the process lifetime, so
    `WppconnectProvider`'s in-memory token cache survives across requests.
    """
    provider_name = get_settings().whatsapp_provider
    if provider_name == "mock":
        return MockWhatsAppProvider()
    if provider_name == "wppconnect":
        return WppconnectProvider(get_settings())
    raise ValueError(f"Unknown WHATSAPP_PROVIDER: {provider_name!r}")
