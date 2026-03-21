"""Verification command support."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from econharness.config import load_config
from econharness.quarantine import quarantine_generated_artifacts


@dataclass(slots=True)
class VerifyResult:
    profile: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    from_scratch: bool = False
    quarantine_dir: str | None = None
    moved_paths: tuple[str, ...] = ()
    regenerated_paths: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    clean_tree_before: bool | None = None
    clean_tree_after: bool | None = None
    git_status_before: tuple[str, ...] = ()
    git_status_after: tuple[str, ...] = ()


def _resolve_command(config: dict, profile: str) -> str:
    pipeline = config.get("pipeline", {})
    commands = pipeline.get("command", {})
    if profile == "fast":
        return str(commands.get("fast", "")).strip()
    return str(commands.get("full", "")).strip()


def verify_project(
    project_root: Path,
    profile: str,
    *,
    from_scratch: bool = False,
    check_clean_tree: bool = False,
) -> VerifyResult:
    config = load_config(project_root)
    command = _resolve_command(config, profile)
    if not command:
        raise ValueError(f"No `{profile}` verification command is configured.")

    git_status_before = _git_status(project_root) if check_clean_tree else None
    quarantine_dir: str | None = None
    moved_paths: tuple[str, ...] = ()
    if from_scratch:
        quarantine_result = quarantine_generated_artifacts(project_root, config)
        quarantine_dir = str(quarantine_result.quarantine_dir)
        moved_paths = quarantine_result.moved_paths

    completed = subprocess.run(
        command,
        shell=True,
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    regenerated_paths = tuple(
        path
        for path in moved_paths
        if (project_root / path).exists()
    )
    missing_paths = tuple(path for path in moved_paths if path not in regenerated_paths)
    git_status_after = _git_status(project_root) if check_clean_tree else None

    return VerifyResult(
        profile=profile,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        from_scratch=from_scratch,
        quarantine_dir=quarantine_dir,
        moved_paths=moved_paths,
        regenerated_paths=regenerated_paths,
        missing_paths=missing_paths,
        clean_tree_before=(not git_status_before) if isinstance(git_status_before, tuple) else None,
        clean_tree_after=(not git_status_after) if isinstance(git_status_after, tuple) else None,
        git_status_before=git_status_before or (),
        git_status_after=git_status_after or (),
    )


def _git_status(project_root: Path) -> tuple[str, ...] | None:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return None
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return tuple(line for line in completed.stdout.splitlines() if line.strip())
