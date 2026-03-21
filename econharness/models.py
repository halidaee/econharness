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
class LookupCandidate:
    path: str
    language: str
    source_artifact: str | None
    join_keys: tuple[str, ...]
    projected_columns: frozenset[str]
    derived_columns: frozenset[str]
    derived_families: frozenset[str]
    transform_ops: frozenset[str]
    derivation_kind: str


@dataclass(slots=True)
class ScanResult:
    project_root: str
    findings: list[Finding]
    dimension_scores: dict[str, float]
    overall_score: float
    summary: dict[str, Any] = field(default_factory=dict)
