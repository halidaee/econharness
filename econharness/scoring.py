"""Scoring policy."""

from __future__ import annotations

from collections import defaultdict

from econharness.models import Finding

DIMENSION_WEIGHTS = {
    "automation_and_one_command_rebuild": 22.0,
    "manual_step_elimination": 14.0,
    "directory_and_stage_structure": 14.0,
    "relational_data_discipline": 18.0,
    "environment_reproducibility": 10.0,
    "cluster_environment": 6.0,
    "path_portability": 8.0,
    "artifact_traceability": 8.0,
    "version_control_discipline": 5.0,
    "self_documenting_clarity": 3.0,
    "software_hygiene_and_redundancy": 8.0,
}


def compute_scores(findings: list[Finding]) -> tuple[dict[str, float], float]:
    penalties: dict[str, float] = defaultdict(float)
    for finding in findings:
        penalties[finding.dimension] += finding.score_impact

    dimension_scores: dict[str, float] = {}
    weighted_total = 0.0
    weight_sum = 0.0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        dimension_score = max(0.0, 100.0 - penalties.get(dimension, 0.0))
        dimension_scores[dimension] = round(dimension_score, 1)
        weighted_total += dimension_score * weight
        weight_sum += weight
    overall = round(weighted_total / weight_sum, 1) if weight_sum else 100.0
    return dimension_scores, overall
