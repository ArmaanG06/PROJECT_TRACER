"""Typed errors. The failover logic keys off these, so providers raise them."""

from __future__ import annotations


class TracerDataError(Exception):
    """Base class for data-layer errors."""


class ProviderUnavailable(TracerDataError):
    """The source is unreachable or rejected our credentials."""


class SymbolNotFound(TracerDataError):
    """The source is up but does not know this symbol."""


class CoverageError(TracerDataError):
    """The source cannot cover the requested date range."""


class DataUnavailableError(TracerDataError):
    """No source could satisfy the request.

    ``failures`` maps source -> {symbol: reason} so you can see what was tried.
    """

    def __init__(self, failures: dict[str, dict[str, str]]):
        self.failures = failures
        lines = ["No source could satisfy the request."]
        for source, per_symbol in failures.items():
            for symbol, reason in per_symbol.items():
                lines.append(f"  {source} / {symbol}: {reason}")
        super().__init__("\n".join(lines))
