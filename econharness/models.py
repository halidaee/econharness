"""Core models for econharness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Finding:
    id: str
    dimension: str
    severity: str
    title: str
    detail: str
    remediation: str
    score_impact: float
    path: str | None = None


@dataclass(slots=True)
class ScanResult:
    project_root: str
    findings: list[Finding]
    dimension_scores: dict[str, float]
    overall_score: float
    summary: dict[str, Any] = field(default_factory=dict)
