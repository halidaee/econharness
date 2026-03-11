"""State persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from econharness.models import Finding, ScanResult


def state_dir(project_root: Path) -> Path:
    return project_root / ".econharness"


def state_path(project_root: Path) -> Path:
    return state_dir(project_root) / "state.json"


def save_scan_result(project_root: Path, result: ScanResult) -> None:
    payload = {
        "project_root": result.project_root,
        "overall_score": result.overall_score,
        "dimension_scores": result.dimension_scores,
        "summary": result.summary,
        "findings": [asdict(finding) for finding in result.findings],
    }
    directory = state_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    state_path(project_root).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_state(project_root: Path) -> dict[str, Any] | None:
    path = state_path(project_root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def findings_from_state(project_root: Path) -> list[Finding]:
    state = load_state(project_root)
    if not state:
        return []
    findings: list[Finding] = []
    for item in state.get("findings", []):
        findings.append(Finding(**item))
    return findings
