"""Verification command support."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from econharness.config import load_config


@dataclass(slots=True)
class VerifyResult:
    profile: str
    command: str
    returncode: int
    stdout: str
    stderr: str


def _resolve_command(config: dict, profile: str) -> str:
    pipeline = config.get("pipeline", {})
    commands = pipeline.get("command", {})
    if profile == "fast":
        return str(commands.get("fast", "")).strip()
    return str(commands.get("full", "")).strip()


def verify_project(project_root: Path, profile: str) -> VerifyResult:
    config = load_config(project_root)
    command = _resolve_command(config, profile)
    if not command:
        raise ValueError(f"No `{profile}` verification command is configured.")
    completed = subprocess.run(
        command,
        shell=True,
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return VerifyResult(
        profile=profile,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
