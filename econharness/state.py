"""State persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from econharness.models import Finding, ScanResult
from econharness.scoring import compute_scores
from econharness.suppressions import active_suppressed_ids


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
    suppressed = active_suppressed_ids(project_root)
    findings: list[Finding] = []
    for item in state.get("findings", []):
        finding = Finding(**item)
        if finding.id not in suppressed:
            findings.append(finding)
    return findings


def scan_result_from_state(state: dict[str, Any]) -> ScanResult:
    # Determine project_root from state for suppression filtering
    project_root = Path(state["project_root"])
    suppressed = active_suppressed_ids(project_root)
    all_findings = [Finding(**item) for item in state.get("findings", [])]
    findings = [f for f in all_findings if f.id not in suppressed]
    suppressed_count = len(all_findings) - len(findings)
    # Recompute scores from filtered findings
    dimension_scores, overall_score = compute_scores(findings)
    summary = dict(state.get("summary", {}))
    summary["findings"] = len(findings)
    summary["high_severity"] = sum(1 for f in findings if f.severity == "high")
    if suppressed_count:
        summary["suppressed"] = suppressed_count
    return ScanResult(
        project_root=state["project_root"],
        findings=findings,
        dimension_scores=dimension_scores,
        overall_score=overall_score,
        summary=summary,
    )
