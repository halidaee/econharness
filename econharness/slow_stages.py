"""Slow-stage configuration checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from econharness.stages import normalize_stages


@dataclass(slots=True)
class SlowStageIssue:
    kind: str
    stage_name: str | None = None
    stage_names: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


def iter_slow_stage_issues(config: dict) -> list[SlowStageIssue]:
    normalized = normalize_stages(config)
    slow_stages = [
        stage
        for stage in normalized.get("stages", [])
        if bool(stage.get("slow"))
    ]
    if not slow_stages:
        return []

    issues: list[SlowStageIssue] = []
    commands = normalized.get("pipeline", {}).get("command", {})
    fast = str(commands.get("fast", "")).strip()
    full = str(commands.get("full", "")).strip()
    stage_names = tuple(sorted(str(stage.get("name", "")).strip() for stage in slow_stages if str(stage.get("name", "")).strip()))

    if not fast:
        issues.append(SlowStageIssue(kind="missing_fast", stage_names=stage_names))
    elif full and _normalize_command(fast) == _normalize_command(full):
        issues.append(SlowStageIssue(kind="fast_matches_full", stage_names=stage_names))

    for stage in slow_stages:
        name = str(stage.get("name", "")).strip() or "unnamed_stage"
        outputs = tuple(str(item).strip().strip("/") for item in stage.get("outputs", []) if str(item).strip())
        if not outputs:
            issues.append(SlowStageIssue(kind="missing_outputs", stage_name=name))
            continue
        if str(stage.get("command", "")).strip() and not any(_is_reusable_output(path, normalized) for path in outputs):
            issues.append(SlowStageIssue(kind="no_reusable_outputs", stage_name=name, outputs=outputs))

    return issues


def _normalize_command(command: str) -> str:
    return " ".join(command.split())


def _is_reusable_output(output_path: str, config: dict) -> bool:
    paths = config.get("paths", {})
    derived_root = str(paths.get("derived", "")).strip().strip("/")
    output_root = str(paths.get("output", "")).strip().strip("/")
    temp_root = str(paths.get("temp", "")).strip().strip("/")

    in_reusable_root = False
    if derived_root and _is_within(output_path, derived_root):
        in_reusable_root = True
    if output_root and _is_within(output_path, output_root):
        in_reusable_root = True
    if not in_reusable_root:
        return False
    if temp_root and _is_within(output_path, temp_root):
        return False
    return True


def _is_within(path_text: str, root_text: str) -> bool:
    try:
        PurePosixPath(path_text).relative_to(PurePosixPath(root_text))
        return True
    except ValueError:
        return False
