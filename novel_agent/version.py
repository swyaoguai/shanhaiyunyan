"""Application version helpers."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


DEFAULT_APP_VERSION = "1.0.0"
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def normalize_app_version(value: str | None) -> str | None:
    """Return a valid semantic version string, or None when the value is invalid."""
    version = str(value or "").strip()
    if not SEMVER_PATTERN.fullmatch(version):
        return None
    return version


def read_app_version_file(path: Path) -> str | None:
    """Read a semantic app version from path if it exists and is valid."""
    try:
        if not path.exists() or not path.is_file():
            return None
        return normalize_app_version(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _candidate_version_files() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "VERSION")
        candidates.append(Path(sys.executable).parent / "VERSION")

    candidates.append(Path(__file__).resolve().parents[1] / "VERSION")
    candidates.append(Path.cwd() / "VERSION")
    return candidates


def get_app_version() -> str:
    """Return the current product version from env, bundled VERSION, or fallback."""
    env_version = normalize_app_version(os.environ.get("SHANHAI_APP_VERSION"))
    if env_version:
        return env_version

    seen: set[Path] = set()
    for path in _candidate_version_files():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)

        version = read_app_version_file(path)
        if version:
            return version

    return DEFAULT_APP_VERSION
