"""Config loading and defaults."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "pipeline": {
        "command": {
            "fast": "",
            "full": "",
        },
        "entrypoints": [],
        "heavy_stages": [],
    },
    "paths": {
        "raw": "raw",
        "derived": "derived",
        "analysis": "analysis",
        "output": "output",
        "paper": "paper",
        "temp": "temp",
    },
    "datasets": [],
    "artifacts": {
        "tables": [],
        "figures": [],
        "paper_files": [],
    },
    "environment": {
        "r": {"manager": "renv", "lockfiles": ["renv.lock"]},
        "python": {"manager": "pixi", "lockfiles": ["pixi.lock"]},
    },
    "scorecard": {
        "generate": True,
        "svg_path": ".econharness/scorecard.svg",
        "html_path": ".econharness/scorecard.html",
    },
    "conventions": {
        "authoritative_pipeline": True,
        "allow_notebooks": True,
    },
    "exclude": [
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".Rproj.user",
        "renv/library",
        "node_modules",
    ],
    "ignore": [],
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def config_path_for(project_root: Path) -> Path:
    return project_root / ".econharness.yml"


def load_config(project_root: Path) -> dict[str, Any]:
    config_path = config_path_for(project_root)
    if not config_path.exists():
        return default_config()

    text = config_path.read_text(encoding="utf-8").strip()
    if not text:
        return default_config()
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        try:
            import yaml  # type: ignore
        except ImportError as import_exc:
            raise ValueError(
                f"Unable to parse {config_path}. Install PyYAML or keep the file JSON-compatible."
            ) from import_exc
        loaded = yaml.safe_load(text)  # type: ignore[no-untyped-call]
    if not isinstance(loaded, dict):
        raise ValueError(f"Config {config_path} must decode to an object.")
    return _merge(default_config(), loaded)


def render_default_config() -> str:
    return json.dumps(default_config(), indent=2) + "\n"
