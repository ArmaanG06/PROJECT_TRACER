"""Command center: the CLI and read-only dashboard for Project Tracer.

This package observes and orchestrates. It reads the data layer's manifest,
triggers pulls, and edits the strategy registry. It contains no signal logic, no
backtesting and nothing that can reach an execution venue.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
