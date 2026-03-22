"""Config loading and defaults."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from econharness.stages import normalize_stages


DEFAULT_CONFIG: dict[str, Any] = {
    "pipeline": {
        "command": {
            "fast": "",
            "full": "",
            "tests": "",
        },
        "entrypoints": [],
    },
    "stages": [],
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
        ".pixi",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".Rproj.user",
        "renv",
        ".pytest_cache",
        ".mypy_cache",
        ".quarto",
        ".ipynb_checkpoints",
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
    return normalize_stages(deepcopy(DEFAULT_CONFIG))


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
    return normalize_stages(_merge(default_config(), loaded))


def render_default_config() -> str:
    return json.dumps(default_config(), indent=2) + "\n"


ENTRY_POINT_COMMANDS: dict[str, dict[str, str]] = {
    "Makefile":    {"fast": "make fast", "full": "make", "tests": "make test"},
    "run_all.sh":  {"fast": "bash run_all.sh", "full": "bash run_all.sh", "tests": ""},
    "run_all.R":   {"fast": "Rscript run_all.R", "full": "Rscript run_all.R", "tests": ""},
    "run_all.py":  {"fast": "python run_all.py", "full": "python run_all.py", "tests": ""},
    "Snakefile":   {"fast": "snakemake", "full": "snakemake", "tests": ""},
    "dodo.py":     {"fast": "doit", "full": "doit", "tests": ""},
}

_STAGE_DIRS = ["raw", "derived", "analysis", "output", "paper", "temp"]


def bootstrap_config(project_root: Path) -> str:
    """Introspect project_root and return an annotated YAML config string."""
    found_eps = [ep for ep in ENTRY_POINT_COMMANDS if (project_root / ep).exists()]

    # Pipeline commands
    if len(found_eps) == 0:
        fast_cmd = full_cmd = tests_cmd = ""
        pipeline_comment = "  # no pipeline entry point detected — set manually"
    elif len(found_eps) == 1:
        ep = found_eps[0]
        cmds = ENTRY_POINT_COMMANDS[ep]
        fast_cmd = cmds["fast"]
        full_cmd = cmds["full"]
        tests_cmd = cmds["tests"]
        if ep == "Makefile":
            pipeline_comment = f"  # detected: {ep} — verify 'make fast' and 'make test' targets exist"
        else:
            pipeline_comment = f"  # detected: {ep}"
    else:
        fast_cmd = full_cmd = tests_cmd = ""
        ep_list = ", ".join(found_eps)
        pipeline_comment = f"  # WARNING: multiple pipeline entry points detected ({ep_list}) — resolve ambiguity"

    # Environment detection
    has_pixi = (project_root / "pixi.toml").exists() or (project_root / "pixi.lock").exists()
    has_renv = (project_root / "renv.lock").exists()
    if has_pixi:
        py_manager = "pixi"
        py_lockfiles = "[pixi.lock]"
        py_comment = "  # detected: pixi.toml/pixi.lock"
    else:
        py_manager = "pixi"
        py_lockfiles = "[pixi.lock]"
        py_comment = "  # no Python lock file detected"
    if has_renv:
        r_manager = "renv"
        r_lockfiles = "[renv.lock]"
        r_comment = "  # detected: renv.lock"
    else:
        r_manager = "renv"
        r_lockfiles = "[renv.lock]"
        r_comment = "  # no R lock file detected"

    # Stage directory detection
    path_lines = []
    for stage in _STAGE_DIRS:
        if (project_root / stage).exists():
            path_lines.append(f"  {stage}: {stage}  # directory exists")
        elif (project_root / "data" / stage).exists():
            path_lines.append(f"  {stage}: data/{stage}  # directory exists")
        else:
            path_lines.append(f"  {stage}: {stage}  # directory not found — create or update this path")

    paths_block = "\n".join(path_lines)
    fast_line = f'    fast: "{fast_cmd}"' if fast_cmd else '    fast: ""'
    full_line = f'    full: "{full_cmd}"' if full_cmd else '    full: ""'
    tests_line = f'    tests: "{tests_cmd}"' if tests_cmd else '    tests: ""'

    lines = [
        "# econharness configuration",
        "# Generated by econharness init — edit as needed",
        pipeline_comment,
        "",
        "pipeline:",
        "  command:",
        fast_line,
        full_line,
        tests_line,
        "  entrypoints: []",
        "",
        "stages: []",
        "",
        "environment:",
        "  python:",
        f"    manager: {py_manager}{py_comment}",
        f"    lockfiles: {py_lockfiles}",
        "  r:",
        f"    manager: {r_manager}{r_comment}",
        f"    lockfiles: {r_lockfiles}",
        "",
        "paths:",
        paths_block,
        "",
        "datasets: []",
        "artifacts:",
        "  tables: []",
        "  figures: []",
        "  paper_files: []",
        "",
        "exclude:",
        '  - ".git"',
        '  - ".pixi"',
        '  - ".venv"',
        '  - "venv"',
        '  - "env"',
        '  - "__pycache__"',
        '  - ".Rproj.user"',
        '  - "renv"',
        '  - ".pytest_cache"',
        '  - ".mypy_cache"',
        '  - ".quarto"',
        '  - ".ipynb_checkpoints"',
        '  - "node_modules"',
        "",
        "ignore: []",
        "",
        "scorecard:",
        "  generate: true",
        "  svg_path: .econharness/scorecard.svg",
        "  html_path: .econharness/scorecard.html",
        "",
        "conventions:",
        "  authoritative_pipeline: true",
        "  allow_notebooks: true",
    ]
    return "\n".join(lines) + "\n"
