"""Project scanning orchestration."""

from __future__ import annotations

from pathlib import Path

from econharness.config import load_config
from econharness.detectors import (
    detect_artifact_traceability,
    detect_automation,
    detect_directory_structure,
    detect_environment_reproducibility,
    detect_function_state_discipline,
    detect_heavy_stage_smoke_gaps,
    detect_manual_steps,
    detect_merge_workflow,
    detect_paper_source_leakage,
    detect_path_portability,
    detect_raw_data_writes,
    detect_relational_data,
    detect_sample_construction_drift,
    detect_self_documenting_clarity,
    detect_software_hygiene,
    detect_stage_contracts,
    detect_tests_presence,
    detect_version_control_discipline,
    iter_project_files,
)
from econharness.models import ScanResult
from econharness.scoring import compute_scores


def scan_project(project_root: Path) -> ScanResult:
    project_root = project_root.resolve()
    config = load_config(project_root)
    files = list(iter_project_files(project_root, config.get("exclude", [])))
    findings = []
    findings.extend(detect_automation(project_root, config, files))
    findings.extend(detect_heavy_stage_smoke_gaps(config))
    findings.extend(detect_manual_steps(project_root, files))
    findings.extend(detect_directory_structure(project_root, config))
    findings.extend(detect_raw_data_writes(project_root, config, files))
    findings.extend(detect_environment_reproducibility(project_root, config, files))
    findings.extend(detect_path_portability(project_root, files))
    findings.extend(detect_version_control_discipline(project_root, config, files))
    findings.extend(detect_self_documenting_clarity(project_root, files))
    findings.extend(detect_function_state_discipline(project_root, files))
    findings.extend(detect_tests_presence(project_root, config, files))
    findings.extend(detect_stage_contracts(project_root, config, files))
    findings.extend(detect_artifact_traceability(project_root, config, files))
    findings.extend(detect_paper_source_leakage(project_root, config, files))
    findings.extend(detect_relational_data(project_root, config))
    findings.extend(detect_merge_workflow(project_root, config, files))
    findings.extend(detect_sample_construction_drift(project_root, files))
    findings.extend(detect_software_hygiene(project_root, files))
    findings.sort(key=lambda finding: ({"high": 0, "medium": 1, "low": 2}.get(finding.severity, 9), -finding.score_impact, finding.id))
    dimension_scores, overall_score = compute_scores(findings)
    summary = {
        "files_scanned": len(files),
        "findings": len(findings),
        "high_severity": sum(1 for finding in findings if finding.severity == "high"),
    }
    return ScanResult(
        project_root=str(project_root),
        findings=findings,
        dimension_scores=dimension_scores,
        overall_score=overall_score,
        summary=summary,
    )
