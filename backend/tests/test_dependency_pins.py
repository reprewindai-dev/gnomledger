"""requirements.txt (Docker image) and backend/pyproject.toml (CI) must install the same
library versions, otherwise CI proves a different runtime than the one that is deployed.

Audit (2026-10-06): requirements.txt pinned fastapi==0.110.0 while CI installed the
patched ^0.141 line from backend/pyproject.toml.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Libraries pinned in both files. uvicorn carries extras in both, handled by the regex.
SHARED = ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "pydantic", "pydantic-settings", "httpx", "stripe")


def _requirement_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s;#]+)", line.strip())
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def _pyproject_floors() -> dict[str, str]:
    data = tomllib.loads((REPO / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    floors: dict[str, str] = {}
    for name, spec in data["tool"]["poetry"]["dependencies"].items():
        version = spec["version"] if isinstance(spec, dict) else spec
        if isinstance(version, str) and version.startswith("^"):
            floors[name.lower()] = version[1:]
    return floors


def test_docker_requirements_match_ci_pyproject_versions() -> None:
    pins = _requirement_pins()
    floors = _pyproject_floors()

    drift = {}
    for name in SHARED:
        pinned = tuple(int(p) for p in pins[name].split("."))
        floor = tuple(int(p) for p in floors[name].split("."))
        # Caret keeps the first non-zero component fixed; the pin must sit inside that range.
        same_line = pinned[:1] == floor[:1] if floor[0] else pinned[:2] == floor[:2]
        if not same_line or pinned < floor:
            drift[name] = (pins[name], floors[name])

    assert not drift, f"requirements.txt drifted from backend/pyproject.toml: {drift}"
