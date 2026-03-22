"""Config schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KNOWN_TOP_LEVEL_KEYS = {
    "pipeline", "stages", "paths", "datasets", "artifacts",
    "environment", "scorecard", "conventions", "exclude", "ignore",
}


def validate_config_path(project_root: Path) -> tuple[list[str], list[str]]:
    """Parse and validate .econharness.yml. Returns (errors, warnings)."""
    config_path = project_root / ".econharness.yml"
    if not config_path.exists():
        return (["No config file found. Run econharness init to create one."], [])

    text = config_path.read_text(encoding="utf-8").strip()
    if not text:
        return (["Config file is empty."], [])

    raw: Any
    try:
        raw = _parse_raw(text, config_path)
    except ValueError as exc:
        return ([f"Parse error: {exc}"], [])

    if not isinstance(raw, dict):
        return (["Config must be a YAML/JSON object at the top level."], [])

    return _validate_dict(raw)


def _parse_raw(text: str, config_path: Path) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ValueError(
            f"Unable to parse {config_path}. Install PyYAML or keep the file JSON-compatible."
        ) from exc
    try:
        return yaml.safe_load(text)  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _check_type(errors: list[str], value: Any, expected_type: type, path: str) -> bool:
    if not isinstance(value, expected_type):
        errors.append(f"{path} — expected {expected_type.__name__}, got {type(value).__name__}")
        return False
    return True


def _validate_dict(raw: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in raw:
        if key not in KNOWN_TOP_LEVEL_KEYS:
            warnings.append(f"unknown top-level key '{key}' — may be a typo")

    _validate_pipeline(errors, raw.get("pipeline"))
    _validate_stages(errors, raw.get("stages"))
    _validate_paths(errors, raw.get("paths"))
    _validate_artifacts(errors, raw.get("artifacts"))
    _validate_environment(errors, raw.get("environment"))
    _validate_scorecard(errors, raw.get("scorecard"))
    _validate_conventions(errors, raw.get("conventions"))
    _validate_list_of_str(errors, raw.get("exclude"), "exclude")
    _validate_list_of_str(errors, raw.get("ignore"), "ignore")
    datasets = raw.get("datasets")
    if datasets is not None:
        _check_type(errors, datasets, list, "datasets")

    return errors, warnings


def _validate_pipeline(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "pipeline"):
        return
    cmd = value.get("command")
    if cmd is not None:
        if _check_type(errors, cmd, dict, "pipeline.command"):
            for field in ("fast", "full", "tests"):
                v = cmd.get(field)
                if v is not None:
                    _check_type(errors, v, str, f"pipeline.command.{field}")
    ep = value.get("entrypoints")
    if ep is not None:
        _check_type(errors, ep, list, "pipeline.entrypoints")


def _validate_stages(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, list, "stages"):
        return
    for i, entry in enumerate(value):
        if isinstance(entry, str):
            continue
        if not isinstance(entry, dict):
            errors.append(f"stages[{i}] — expected str or dict, got {type(entry).__name__}")
            continue
        for field in ("name", "command"):
            v = entry.get(field)
            if v is not None:
                _check_type(errors, v, str, f"stages[{i}].{field}")
        for list_field in ("read_roots", "write_roots", "inputs", "outputs"):
            v = entry.get(list_field)
            if v is not None:
                _validate_list_of_str(errors, v, f"stages[{i}].{list_field}")
        slow = entry.get("slow")
        if slow is not None:
            _check_type(errors, slow, bool, f"stages[{i}].slow")
        match = entry.get("match")
        if match is not None:
            if _check_type(errors, match, list, f"stages[{i}].match"):
                for j, pattern in enumerate(match):
                    if not isinstance(pattern, str):
                        errors.append(f"stages[{i}].match[{j}] — expected str, got {type(pattern).__name__}")


def _validate_paths(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "paths"):
        return
    for field in ("raw", "derived", "analysis", "output", "paper", "temp"):
        v = value.get(field)
        if v is not None:
            _check_type(errors, v, str, f"paths.{field}")


def _validate_artifacts(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "artifacts"):
        return
    for field in ("tables", "figures", "paper_files"):
        v = value.get(field)
        if v is not None:
            _check_type(errors, v, list, f"artifacts.{field}")


def _validate_environment(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "environment"):
        return
    for lang in ("r", "python"):
        v = value.get(lang)
        if v is None:
            continue
        if not _check_type(errors, v, dict, f"environment.{lang}"):
            continue
        mgr = v.get("manager")
        if mgr is not None:
            _check_type(errors, mgr, str, f"environment.{lang}.manager")
        lf = v.get("lockfiles")
        if lf is not None:
            _validate_list_of_str(errors, lf, f"environment.{lang}.lockfiles")


def _validate_scorecard(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "scorecard"):
        return
    gen = value.get("generate")
    if gen is not None:
        _check_type(errors, gen, bool, "scorecard.generate")
    for field in ("svg_path", "html_path"):
        v = value.get(field)
        if v is not None:
            _check_type(errors, v, str, f"scorecard.{field}")


def _validate_conventions(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not _check_type(errors, value, dict, "conventions"):
        return
    for field in ("authoritative_pipeline", "allow_notebooks"):
        v = value.get(field)
        if v is not None:
            _check_type(errors, v, bool, f"conventions.{field}")


def _validate_list_of_str(errors: list[str], value: Any, path: str) -> None:
    if value is None:
        return
    if not _check_type(errors, value, list, path):
        return
    for i, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{path}[{i}] — expected str, got {type(item).__name__}")
