"""Data providers, one module per source.

Built lazily so importing data_pulling never opens a socket or requires every
vendor library to be installed.
"""

from __future__ import annotations

from .base import COLUMNS, Provider

#: Failover order. get_prices(source=...) starts here and works down the list.
PROVIDER_ORDER = ("ibkr", "wrds", "yfinance")

_CACHE: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    """Return (and cache) the provider registered under ``name``."""
    key = name.lower()
    if key not in _CACHE:
        if key == "ibkr":
            from .ibkr import IbkrProvider as cls
        elif key == "wrds":
            from .wrds import WrdsProvider as cls
        elif key == "yfinance":
            from .yfinance import YfinanceProvider as cls
        else:
            raise KeyError(f"Unknown provider {name!r}; expected one of {list(PROVIDER_ORDER)}")
        _CACHE[key] = cls()
    return _CACHE[key]


def reset_providers() -> None:
    """Close and drop every cached provider."""
    for provider in _CACHE.values():
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    _CACHE.clear()


def failover_chain(source: str) -> list[str]:
    """Sources to try, starting at ``source``, never repeating one."""
    key = source.lower()
    if key not in PROVIDER_ORDER:
        raise KeyError(f"Unknown source {source!r}; expected one of {list(PROVIDER_ORDER)}")
    return [key] + [name for name in PROVIDER_ORDER if name != key]


__all__ = ["COLUMNS", "PROVIDER_ORDER", "Provider", "failover_chain", "get_provider", "reset_providers"]
