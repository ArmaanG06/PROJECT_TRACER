"""Settings loading.

Reads ``config/settings.yaml``, then lets ``.env`` / real environment variables
override it. The project root is found by walking up from this file, so paths
resolve the same way from any working directory -- including programs/ROME/.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# TRACER_* env var -> dotted path in settings.yaml
_ENV_OVERRIDES = {
    "TRACER_IBKR_HOST": "providers.ibkr.host",
    "TRACER_IBKR_PORT": "providers.ibkr.port",
    "TRACER_IBKR_CLIENT_ID": "providers.ibkr.client_id",
    "TRACER_WRDS_USERNAME": "providers.wrds.username",
    "TRACER_LOG_LEVEL": "logging.level",
}


def project_root() -> Path:
    """Repository root, found by walking up to the directory with pyproject.toml."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return here.parents[2]


def _coerce(value: str) -> Any:
    low = value.strip().lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"", "none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


class Settings:
    """Dotted-path access to the merged settings tree."""

    def __init__(self, tree: dict[str, Any], root: Path):
        self._tree = tree
        self.root = root

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._tree
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def path(self, name: str) -> Path:
        """A configured path, resolved against the project root."""
        raw = self.get(f"paths.{name}")
        if raw is None:
            raise KeyError(f"paths.{name} is not configured")
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else self.root / candidate

    def provider(self, name: str) -> dict[str, Any]:
        return dict(self.get(f"providers.{name}", {}) or {})

    @property
    def provider_order(self) -> list[str]:
        return list(self.get("providers.order", ["ibkr", "wrds", "yfinance"]))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings for the life of the process."""
    root = project_root()

    env_file = root / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    settings_file = root / "config" / "settings.yaml"
    tree: dict[str, Any] = {}
    if settings_file.exists():
        tree = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}

    for env_key, dotted in _ENV_OVERRIDES.items():
        if env_key in os.environ:
            keys = dotted.split(".")
            node = tree
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = _coerce(os.environ[env_key])

    return Settings(tree, root)
