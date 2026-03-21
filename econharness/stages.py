"""Stage configuration normalization helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _as_list_of_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def normalize_stage_entry(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        name = value.strip()
        return {
            "name": name,
            "match": [],
            "read_roots": [],
            "write_roots": [],
            "slow": False,
            "command": "",
            "inputs": [],
            "outputs": [],
        }

    if not isinstance(value, dict):
        return {
            "name": str(value).strip() or "unnamed_stage",
            "match": [],
            "read_roots": [],
            "write_roots": [],
            "slow": False,
            "command": "",
            "inputs": [],
            "outputs": [],
        }

    name = str(value.get("name", "")).strip() or "unnamed_stage"
    return {
        "name": name,
        "match": _as_list_of_strings(value.get("match", [])),
        "read_roots": _as_list_of_strings(value.get("read_roots", [])),
        "write_roots": _as_list_of_strings(value.get("write_roots", [])),
        "slow": bool(value.get("slow", False)),
        "command": str(value.get("command", "")).strip(),
        "inputs": _as_list_of_strings(value.get("inputs", [])),
        "outputs": _as_list_of_strings(value.get("outputs", [])),
    }


def normalize_stages(config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(config)

    explicit_stages = [
        normalize_stage_entry(item)
        for item in normalized.get("stages", [])
    ]
    by_name = {stage["name"]: stage for stage in explicit_stages}

    pipeline = normalized.get("pipeline", {})
    for item in pipeline.get("heavy_stages", []):
        stage = normalize_stage_entry(item)
        stage["slow"] = True
        existing = by_name.get(stage["name"])
        if existing is None:
            explicit_stages.append(stage)
            by_name[stage["name"]] = stage
            continue
        existing["slow"] = True

    normalized["stages"] = explicit_stages
    return normalized
