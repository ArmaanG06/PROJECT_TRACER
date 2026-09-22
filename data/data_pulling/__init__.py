"""Project Tracer data layer.

All data CODE lives here; all data FILES live under data/store/. Programs in
programs/<CITY>/ import this package by name:

    from data_pulling import get_prices, to_wide, load_universe

That works from any directory because pyproject.toml maps the import name onto
data/data_pulling/ and the package is installed editable (pip install -e .).
No sys.path hacks anywhere.

The contract: get_prices returns a tidy long frame of daily bars where
adj_close is total-return adjusted and every symbol's series comes from exactly
one source, recorded in the `source` column.
"""

from __future__ import annotations

import logging
from logging import NullHandler

from . import store
from .api import get_prices, to_wide
from .config import get_settings, project_root
from .errors import (
    CoverageError,
    DataUnavailableError,
    ProviderUnavailable,
    SymbolNotFound,
    TracerDataError,
)
from .providers import PROVIDER_ORDER, failover_chain, get_provider, reset_providers
from .universe import list_universes, load_symbols, load_universe

__version__ = "0.1.0"

# A library must not configure logging for its host; the CLI calls
# configure_logging().
logging.getLogger(__name__).addHandler(NullHandler())


def configure_logging(level: str | int | None = None) -> None:
    """Attach a terminal handler to the data_pulling logger."""
    resolved = level or get_settings().get("logging.level", "INFO")
    logger = logging.getLogger(__name__)
    logger.setLevel(resolved)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False


__all__ = [
    "CoverageError",
    "DataUnavailableError",
    "PROVIDER_ORDER",
    "ProviderUnavailable",
    "SymbolNotFound",
    "TracerDataError",
    "configure_logging",
    "failover_chain",
    "get_prices",
    "get_provider",
    "get_settings",
    "list_universes",
    "load_symbols",
    "load_universe",
    "project_root",
    "reset_providers",
    "store",
    "to_wide",
]
