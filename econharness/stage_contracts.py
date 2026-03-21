"""Stage contract enforcement."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from econharness.path_usage import PathUse, extract_path_uses


SUPPORTED_CODE_SUFFIXES = {".py", ".r", ".sh", ".do"}


@dataclass(slots=True)
class StageContractIssue:
    kind: str
    path: str
    stage_name: str | None
    referenced_path: str | None
    matched_stages: tuple[str, ...] = ()


def iter_stage_contract_issues(project_root: Path, config: dict, files: Iterable[Path]) -> list[StageContractIssue]:
    stages = [stage for stage in config.get("stages", []) if stage.get("match") or stage.get("read_roots") or stage.get("write_roots")]
    if not stages:
        return []

    issues: list[StageContractIssue] = []
    for path in files:
        if path.suffix.lower() not in SUPPORTED_CODE_SUFFIXES:
            continue
        rel = path.relative_to(project_root).as_posix()
        matched = [
            stage
            for stage in stages
            if any(fnmatch.fnmatch(rel, pattern) for pattern in stage.get("match", []))
        ]
        if not matched:
            issues.append(StageContractIssue(kind="unmatched", path=rel, stage_name=None, referenced_path=None))
            continue
        if len(matched) > 1:
            issues.append(
                StageContractIssue(
                    kind="ambiguous",
                    path=rel,
                    stage_name=None,
                    referenced_path=None,
                    matched_stages=tuple(stage["name"] for stage in matched),
                )
            )
            continue

        stage = matched[0]
        allowed_read_roots = _resolve_roots(stage.get("read_roots", []), config)
        allowed_write_roots = _resolve_roots(stage.get("write_roots", []), config)
        path_uses = extract_path_uses(path, _read_text(path))

        for path_use in path_uses:
            if path_use.kind == "read" and allowed_read_roots and not _path_within_roots(path_use.path, allowed_read_roots):
                issues.append(
                    StageContractIssue(
                        kind="read_violation",
                        path=rel,
                        stage_name=stage["name"],
                        referenced_path=path_use.path,
                    )
                )
            if path_use.kind == "write" and allowed_write_roots and not _path_within_roots(path_use.path, allowed_write_roots):
                issues.append(
                    StageContractIssue(
                        kind="write_violation",
                        path=rel,
                        stage_name=stage["name"],
                        referenced_path=path_use.path,
                    )
                )

    return issues


def _resolve_roots(roots: list[str], config: dict) -> tuple[str, ...]:
    config_paths = config.get("paths", {})
    resolved = []
    for root in roots:
        value = str(root).strip().strip("/")
        if not value:
            continue
        resolved.append(str(config_paths.get(value, value)).strip().strip("/"))
    return tuple(resolved)


def _path_within_roots(path: str, roots: tuple[str, ...]) -> bool:
    normalized = path.strip().strip("/")
    return any(normalized == root or normalized.startswith(f"{root}/") for root in roots)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
