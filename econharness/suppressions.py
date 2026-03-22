"""Finding suppression management."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def suppressions_path(project_root: Path) -> Path:
    return project_root / ".econharness" / "suppressions.json"


def load_suppressions(project_root: Path) -> dict[str, Any]:
    path = suppressions_path(project_root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_suppressions(project_root: Path, suppressions: dict[str, Any]) -> None:
    path = suppressions_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suppressions, indent=2) + "\n", encoding="utf-8")


def is_active(entry: dict[str, Any]) -> bool:
    """Return True if the suppression is not expired."""
    expires = entry.get("expires")
    if expires is None:
        return True
    try:
        return date.fromisoformat(expires) >= date.today()
    except ValueError:
        return True


def parse_duration(duration: str) -> date:
    """Parse a duration string like '90d' or '1y' and return the expiry date."""
    duration = duration.strip().lower()
    if duration.endswith("y"):
        days = int(duration[:-1]) * 365
    elif duration.endswith("d"):
        days = int(duration[:-1])
    else:
        raise ValueError(f"Unsupported duration format: {duration!r}. Use e.g. '90d' or '1y'.")
    return date.today() + timedelta(days=days)


def active_suppressed_ids(project_root: Path) -> set[str]:
    """Return the set of finding IDs with active (non-expired) suppressions."""
    suppressions = load_suppressions(project_root)
    return {fid for fid, entry in suppressions.items() if is_active(entry)}
