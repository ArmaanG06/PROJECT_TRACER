"""The algo registry, backed by config/strategies.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from data_pulling.config import project_root

VALID_STATUSES = ("dev", "paper", "live", "off")

# YAML 1.1 (what PyYAML implements) reads a bare `off` as the boolean False, so
# `status: off` would load as "False". Write those values quoted.
_BOOLISH = {"off", "on", "yes", "no", "true", "false"}


@dataclass(frozen=True)
class Strategy:
    """One algo's registry entry."""

    name: str
    universe: str
    status: str
    enabled: bool
    description: str


def registry_path() -> Path:
    """Path to config/strategies.yaml."""
    return project_root() / "config" / "strategies.yaml"


def _status(raw: Any) -> str:
    if isinstance(raw, bool):  # see _BOOLISH above
        return "off" if raw is False else "on"
    return str(raw)


def load_registry() -> dict[str, Strategy]:
    """Read every strategy from the registry."""
    path = registry_path()
    if not path.exists():
        raise FileNotFoundError(f"No strategy registry at {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(name): Strategy(
            name=str(name),
            universe=str((body or {}).get("universe", name)),
            status=_status((body or {}).get("status", "off")),
            enabled=bool((body or {}).get("enabled", False)),
            description=str((body or {}).get("description", "")),
        )
        for name, body in (payload.get("strategies") or {}).items()
    }


def set_status(name: str, status: str) -> Strategy:
    """Change one strategy's status. Touches strategies.yaml and nothing else.

    Edits the single status line in place rather than round-tripping the YAML,
    so comments and key order survive.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    if name not in load_registry():
        raise KeyError(f"No strategy named {name!r}")

    path = registry_path()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    header = re.compile(rf"^(\s*){re.escape(name)}\s*:\s*(#.*)?$")
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        raise ValueError(f"Could not find the {name!r} block in {path}")

    indent = len(header.match(lines[start]).group(1))
    status_line = re.compile(r"^(\s*)status\s*:\s*(\"[^\"]*\"|'[^']*'|[^\s#]+)(\s*#.*)?$")
    written = f'"{status}"' if status in _BOOLISH else status

    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(lines[i]) - len(lines[i].lstrip()) <= indent:
            break  # left this strategy's block
        match = status_line.match(lines[i])
        if match:
            newline = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"{match.group(1)}status: {written}{match.group(3) or ''}{newline}"
            path.write_text("".join(lines), encoding="utf-8")
            return load_registry()[name]

    raise ValueError(f"The {name!r} block has no 'status:' key")
