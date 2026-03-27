"""Scan history tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MAX_HISTORY = 10


def history_path(project_root: Path) -> Path:
    return project_root / ".econharness" / "history.jsonl"


def append_history(project_root: Path, snapshot: dict) -> None:
    """Append a snapshot to history.jsonl and prune to last _MAX_HISTORY entries."""
    path = history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(snapshot)
    # Read existing lines
    existing: list[str] = []
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if raw_line:
                existing.append(raw_line)
    existing.append(line)
    # Prune to last _MAX_HISTORY
    if len(existing) > _MAX_HISTORY:
        existing = existing[-_MAX_HISTORY:]
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")


def load_history(project_root: Path) -> list[dict]:
    """Load history entries, skipping malformed lines. Returns list newest-last."""
    path = history_path(project_root)
    if not path.exists():
        return []
    entries: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entries.append(json.loads(raw_line))
        except json.JSONDecodeError:
            continue
    return entries


def compute_delta(previous: dict, current: dict) -> dict:
    """Compute delta between two history snapshots."""
    prev_score = float(previous.get("overall_score", 0.0))
    curr_score = float(current.get("overall_score", 0.0))
    score_delta = round(curr_score - prev_score, 1)

    prev_dim = previous.get("dimension_scores", {})
    curr_dim = current.get("dimension_scores", {})
    dimension_deltas: dict[str, float] = {}
    all_dims = set(prev_dim) | set(curr_dim)
    for dim in all_dims:
        delta = round(float(curr_dim.get(dim, 0.0)) - float(prev_dim.get(dim, 0.0)), 1)
        if delta != 0.0:
            dimension_deltas[dim] = delta

    prev_ids = {f["id"] for f in previous.get("findings", [])}
    curr_ids = {f["id"] for f in current.get("findings", [])}

    curr_by_id = {f["id"]: f for f in current.get("findings", [])}
    prev_by_id = {f["id"]: f for f in previous.get("findings", [])}

    new_findings = [curr_by_id[fid] for fid in curr_ids - prev_ids]
    resolved_findings = [prev_by_id[fid] for fid in prev_ids - curr_ids]

    return {
        "score_delta": score_delta,
        "dimension_deltas": dimension_deltas,
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
    }


def make_snapshot(result: Any, scanned_at: str | None = None) -> dict:
    """Build a history snapshot dict from a ScanResult."""
    from dataclasses import asdict
    if scanned_at is None:
        scanned_at = datetime.now(tz=timezone.utc).isoformat()
    return {
        "scanned_at": scanned_at,
        "project_root": result.project_root,
        "overall_score": result.overall_score,
        "dimension_scores": result.dimension_scores,
        "findings": [asdict(f) for f in result.findings],
        "summary": result.summary,
    }
