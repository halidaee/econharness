"""Static detectors for economics research projects."""

from __future__ import annotations

import ast
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from econharness.models import Finding

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"/home/[^/\s]+/"),
    re.compile(r"[A-Z]:\\\\Users\\\\"),
    re.compile(r"/Volumes/"),
    re.compile(r"/mnt/"),
]
MACHINE_SPECIFIC_HINTS = ("Desktop", "Downloads", "Dropbox", "OneDrive", "Documents")
MANUAL_STEP_PATTERNS = [
    re.compile(r"\bedit (this|the) file by hand\b", re.IGNORECASE),
    re.compile(r"\bmanually\b", re.IGNORECASE),
    re.compile(r"\bcopy (this|the) .* into\b", re.IGNORECASE),
    re.compile(r"\brun this manually\b", re.IGNORECASE),
]
SCRIPT_SUFFIXES = {".py", ".R", ".r", ".qmd", ".sh", ".md", ".txt", ".do"}
CODE_SUFFIXES = {".py", ".R", ".r", ".sh"}
PAPER_SUFFIXES = {".qmd", ".Rmd", ".rmd", ".tex", ".md"}
MERGE_PATTERNS = [
    re.compile(r"\.merge\s*\("),
    re.compile(r"\bpd\.merge\s*\("),
    re.compile(r"\bleft_join\s*\("),
    re.compile(r"\bright_join\s*\("),
    re.compile(r"\binner_join\s*\("),
    re.compile(r"\bfull_join\s*\("),
    re.compile(r"\bmerge\s+[0-9m:]+\s+.+\s+using\b", re.IGNORECASE),
    re.compile(r"\bjoinby\b", re.IGNORECASE),
]
SAMPLE_PATTERNS = [
    re.compile(r"\bfilter\s*\("),
    re.compile(r"\bsubset\s*\("),
    re.compile(r"\bdrop if\b", re.IGNORECASE),
    re.compile(r"\bkeep if\b", re.IGNORECASE),
    re.compile(r"\banalysis_sample\b"),
    re.compile(r"\bsample_flag\b"),
    re.compile(r"\beligible\s*=="),
]


def make_finding(
    *,
    dimension: str,
    severity: str,
    title: str,
    detail: str,
    remediation: str,
    score_impact: float,
    path: str | None = None,
) -> Finding:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    path_part = path or "project"
    identifier = f"{dimension}:{slug}:{path_part}"
    return Finding(
        id=identifier,
        dimension=dimension,
        severity=severity,
        title=title,
        detail=detail,
        remediation=remediation,
        score_impact=score_impact,
        path=path,
    )


def iter_project_files(project_root: Path, exclude_patterns: list[str]) -> Iterable[Path]:
    excludes = tuple(exclude_patterns)
    for path in project_root.rglob("*"):
        rel = path.relative_to(project_root).as_posix()
        if any(rel == pattern or rel.startswith(f"{pattern.rstrip('/')}/") for pattern in excludes):
            continue
        if any(part in excludes for part in path.parts):
            continue
        if path.is_file():
            yield path


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def detect_automation(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    commands = config.get("pipeline", {}).get("command", {})
    fast = str(commands.get("fast", "")).strip()
    full = str(commands.get("full", "")).strip()
    if not full:
        findings.append(
            make_finding(
                dimension="automation_and_one_command_rebuild",
                severity="high",
                title="Missing authoritative full rebuild command",
                detail="The project does not declare a single full command from raw inputs to final outputs.",
                remediation="Add `pipeline.command.full` to `.econharness.yml` and point it at the authoritative rebuild entrypoint.",
                score_impact=28,
            )
        )
    if not fast:
        findings.append(
            make_finding(
                dimension="automation_and_one_command_rebuild",
                severity="medium",
                title="Missing fast verification command",
                detail="The project does not declare a cheap fast verification path.",
                remediation="Add `pipeline.command.fast` for a smoke-check rebuild path that skips or stubs heavy stages.",
                score_impact=10,
            )
        )
    notebooks = [path for path in files if path.suffix == ".ipynb"]
    if notebooks and not full:
        findings.append(
            make_finding(
                dimension="automation_and_one_command_rebuild",
                severity="medium",
                title="Notebooks present without declared authoritative pipeline",
                detail="Notebook-heavy projects without a declared production command tend to rely on tacit execution order.",
                remediation="Keep notebooks exploratory and declare a script- or Makefile-based authoritative rebuild path.",
                score_impact=8,
            )
        )
    return findings


def detect_manual_steps(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        for pattern in MANUAL_STEP_PATTERNS:
            if pattern.search(text):
                findings.append(
                    make_finding(
                        dimension="manual_step_elimination",
                        severity="high",
                        title="Manual project step documented in source",
                        detail=f"{path.relative_to(project_root)} appears to instruct a manual step: `{pattern.pattern}`.",
                        remediation="Replace the manual step with code or declare it as an explicit automated pipeline stage.",
                        score_impact=12,
                        path=path.relative_to(project_root).as_posix(),
                    )
                )
                break
    return findings


def detect_directory_structure(project_root: Path, config: dict) -> list[Finding]:
    findings: list[Finding] = []
    paths = config.get("paths", {})
    required = ["raw", "derived", "analysis", "output", "paper"]
    seen: dict[str, Path] = {}
    for key in required:
        rel = paths.get(key, "")
        if not rel:
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="high",
                    title=f"Missing configured {key} path",
                    detail=f"No path is configured for the `{key}` stage.",
                    remediation="Declare the stage path in `.econharness.yml`.",
                    score_impact=12,
                )
            )
            continue
        stage_path = project_root / rel
        seen[key] = stage_path
        if not stage_path.exists():
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="medium",
                    title=f"Configured {key} path does not exist",
                    detail=f"The configured `{key}` path `{rel}` is missing.",
                    remediation="Create the directory or update the config to match the actual project layout.",
                    score_impact=6,
                    path=rel,
                )
            )
    if "raw" in seen and "derived" in seen and seen["raw"] == seen["derived"]:
        findings.append(
            make_finding(
                dimension="directory_and_stage_structure",
                severity="high",
                title="Raw and derived data share a directory",
                detail="Raw and derived data should not live in the same directory.",
                remediation="Separate immutable raw inputs from constructed datasets.",
                score_impact=20,
            )
        )
    return findings


def detect_raw_data_writes(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    raw_rel = str(config.get("paths", {}).get("raw", "")).strip().strip("/")
    if not raw_rel:
        return findings
    escaped_raw = re.escape(raw_rel)
    write_patterns = [
        re.compile(rf"write_[A-Za-z0-9_]*\s*\([^)]*{escaped_raw}"),
        re.compile(rf"to_csv\s*\([^)]*{escaped_raw}"),
        re.compile(rf"saveRDS\s*\([^)]*{escaped_raw}"),
        re.compile(rf"writeLines\s*\([^)]*{escaped_raw}"),
        re.compile(rf"write_text\s*\([^)]*{escaped_raw}"),
        re.compile(rf"open\s*\([^)]*{escaped_raw}[^)]*,\s*[\"']w"),
    ]
    for path in files:
        if path.suffix not in CODE_SUFFIXES:
            continue
        text = _read_text(path)
        for pattern in write_patterns:
            if pattern.search(text):
                rel = path.relative_to(project_root).as_posix()
                findings.append(
                    make_finding(
                        dimension="manual_step_elimination",
                        severity="high",
                        title="Code appears to write into raw-data paths",
                        detail=f"{rel} appears to write outputs under the configured raw-data path `{raw_rel}`.",
                        remediation="Keep raw data immutable and write constructed files into the derived or temp stage.",
                        score_impact=16,
                        path=rel,
                    )
                )
                break
    return findings


def detect_environment_reproducibility(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    suffixes = {path.suffix.lower() for path in files}
    has_r = any(path.suffix.lower() in {".r", ".qmd", ".rmd"} for path in files)
    has_python = any(path.suffix.lower() == ".py" for path in files)
    env_config = config.get("environment", {})
    if has_r:
        lockfiles = env_config.get("r", {}).get("lockfiles", ["renv.lock"])
        if not any((project_root / lockfile).exists() for lockfile in lockfiles):
            findings.append(
                make_finding(
                    dimension="environment_reproducibility",
                    severity="medium",
                    title="Missing R environment lockfile",
                    detail="R or Quarto files are present, but no declared R lockfile such as `renv.lock` was found.",
                    remediation="Adopt `renv` or another declared lockfile-backed R environment manager.",
                    score_impact=12,
                )
            )
    if has_python:
        lockfiles = env_config.get("python", {}).get("lockfiles", ["pixi.lock"])
        py_manager = env_config.get("python", {}).get("manager", "pixi")
        manager_hint = project_root / "pixi.toml"
        has_declared_lock = any((project_root / lockfile).exists() for lockfile in lockfiles)
        if not has_declared_lock or (py_manager == "pixi" and not manager_hint.exists()):
            findings.append(
                make_finding(
                    dimension="environment_reproducibility",
                    severity="medium",
                    title="Missing Python reproducible environment metadata",
                    detail="Python files are present, but no declared lockfile-backed environment such as `pixi.toml` + `pixi.lock` was found.",
                    remediation="Adopt `pixi` or another declared lockfile-backed Python environment manager.",
                    score_impact=12,
                )
            )
    return findings


def detect_path_portability(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        rel = path.relative_to(project_root).as_posix()
        found_issue = False
        for pattern in ABSOLUTE_PATH_PATTERNS:
            if pattern.search(text):
                findings.append(
                    make_finding(
                        dimension="path_portability",
                        severity="high",
                        title="Absolute path embedded in project source",
                        detail=f"{rel} contains a machine-specific absolute path.",
                        remediation="Replace absolute paths with project-root-relative paths or configured path variables.",
                        score_impact=12,
                        path=rel,
                    )
                )
                found_issue = True
                break
        if not found_issue:
            for hint in MACHINE_SPECIFIC_HINTS:
                if hint in text:
                    findings.append(
                        make_finding(
                            dimension="path_portability",
                            severity="medium",
                            title="Machine-specific storage path referenced",
                            detail=f"{rel} references a machine-specific location such as `{hint}`.",
                            remediation="Replace user-specific storage references with project-root-relative paths.",
                            score_impact=7,
                            path=rel,
                        )
                    )
                    break
        if path.suffix == ".do" and re.search(r"^\s*cd\s+[\"']", text, flags=re.MULTILINE):
            findings.append(
                make_finding(
                    dimension="path_portability",
                    severity="medium",
                    title="Stata script changes directory explicitly",
                    detail=f"{rel} uses `cd`, which often bakes machine-specific project-root assumptions into the workflow.",
                    remediation="Resolve project paths from a declared root or config instead of changing directories inside `.do` files.",
                    score_impact=6,
                    path=rel,
                )
            )
    return findings


def detect_artifact_traceability(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    artifacts = config.get("artifacts", {})
    expected_outputs = list(artifacts.get("tables", [])) + list(artifacts.get("figures", []))
    paper_files = artifacts.get("paper_files", [])
    searchable_files = [path for path in files if path.suffix in PAPER_SUFFIXES | CODE_SUFFIXES]
    joined_text = "\n".join(_read_text(path) for path in searchable_files)
    for artifact in expected_outputs:
        if artifact and artifact not in joined_text:
            findings.append(
                make_finding(
                    dimension="artifact_traceability",
                    severity="medium",
                    title="Declared artifact is not referenced in project sources",
                    detail=f"The declared artifact `{artifact}` does not appear in the scanned code or paper files.",
                    remediation="Wire the artifact into the authoritative pipeline or remove the stale declaration.",
                    score_impact=8,
                    path=artifact,
                )
            )
    for paper in paper_files:
        if not (project_root / paper).exists():
            findings.append(
                make_finding(
                    dimension="artifact_traceability",
                    severity="medium",
                    title="Declared paper file is missing",
                    detail=f"The configured paper file `{paper}` does not exist.",
                    remediation="Create the file or update the config.",
                    score_impact=6,
                    path=paper,
                )
            )
    return findings


def detect_paper_source_leakage(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    artifacts = config.get("artifacts", {})
    declared = set(artifacts.get("tables", [])) | set(artifacts.get("figures", []))
    raw_rel = str(config.get("paths", {}).get("raw", "")).strip().strip("/")
    derived_rel = str(config.get("paths", {}).get("derived", "")).strip().strip("/")
    paper_files = [path for path in files if path.suffix in {".qmd", ".Rmd", ".rmd", ".tex"}]
    for path in paper_files:
        rel = path.relative_to(project_root).as_posix()
        text = _read_text(path)
        if raw_rel and f"{raw_rel}/" in text:
            findings.append(
                make_finding(
                    dimension="artifact_traceability",
                    severity="high",
                    title="Paper references non-output artifacts directly",
                    detail=f"{rel} references the raw-data path `{raw_rel}/` directly.",
                    remediation="Make the paper consume declared final outputs instead of raw or intermediate files.",
                    score_impact=14,
                    path=rel,
                )
            )
            continue
        if derived_rel and f"{derived_rel}/" in text:
            findings.append(
                make_finding(
                    dimension="artifact_traceability",
                    severity="high",
                    title="Paper references non-output artifacts directly",
                    detail=f"{rel} references the derived-data path `{derived_rel}/` directly.",
                    remediation="Make the paper consume declared final outputs instead of intermediate files.",
                    score_impact=14,
                    path=rel,
                )
            )
            continue
        references = re.findall(r"([A-Za-z0-9_./-]+\.(?:csv|png|pdf|tex))", text)
        for reference in references:
            if reference in declared:
                continue
            if reference.startswith("output/"):
                findings.append(
                    make_finding(
                        dimension="artifact_traceability",
                        severity="medium",
                        title="Paper references undeclared output artifact",
                        detail=f"{rel} references `{reference}`, which is not declared in `.econharness.yml`.",
                        remediation="Declare the artifact or remove the stale paper reference.",
                        score_impact=7,
                        path=rel,
                    )
                )
                break
    return findings


def detect_relational_data(project_root: Path, config: dict) -> list[Finding]:
    findings: list[Finding] = []
    datasets = config.get("datasets", [])
    if not datasets:
        findings.append(
            make_finding(
                dimension="relational_data_discipline",
                severity="medium",
                title="No dataset metadata declared",
                detail="Important intermediate datasets should declare stage, unit, primary key, and parents.",
                remediation="Add key datasets under `datasets` in `.econharness.yml`.",
                score_impact=8,
            )
        )
        return findings

    for dataset in datasets:
        name = dataset.get("name", "<unnamed>")
        path_value = dataset.get("path", "")
        unit = dataset.get("unit")
        primary_key = dataset.get("primary_key")
        stage = dataset.get("stage")
        if not unit or not primary_key or not stage:
            findings.append(
                make_finding(
                    dimension="relational_data_discipline",
                    severity="high",
                    title="Dataset metadata is incomplete",
                    detail=f"Dataset `{name}` should declare `stage`, `unit`, and `primary_key`.",
                    remediation="Complete the dataset metadata so the harness can reason about relational structure.",
                    score_impact=10,
                    path=path_value or name,
                )
            )
            continue
        parents = dataset.get("parents", [])
        if stage in {"derived", "build"} and isinstance(parents, list) and len(parents) >= 3:
            findings.append(
                make_finding(
                    dimension="relational_data_discipline",
                    severity="medium",
                    title="Early merged dataset has many upstream parents",
                    detail=f"Dataset `{name}` is declared at stage `{stage}` with {len(parents)} parents, which suggests a wide merged working file early in the pipeline.",
                    remediation="Keep transformed tables normalized longer and merge late into a final analysis dataset where possible.",
                    score_impact=9,
                    path=path_value or name,
                )
            )
        if not path_value:
            continue
        path = project_root / path_value
        if path.suffix.lower() != ".csv" or not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
        except OSError:
            continue
        keys = primary_key if isinstance(primary_key, list) else [primary_key]
        missing = 0
        duplicates = 0
        seen = set()
        for row in rows:
            key_tuple = tuple(row.get(key, "") for key in keys)
            if any(not item for item in key_tuple):
                missing += 1
                continue
            if key_tuple in seen:
                duplicates += 1
            seen.add(key_tuple)
        if missing:
            findings.append(
                make_finding(
                    dimension="relational_data_discipline",
                    severity="high",
                    title="Dataset primary key has missing values",
                    detail=f"{name} has {missing} rows with missing primary-key values.",
                    remediation="Repair the unit-of-observation definition or key construction before downstream merges.",
                    score_impact=14,
                    path=path_value,
                )
            )
        if duplicates:
            findings.append(
                make_finding(
                    dimension="relational_data_discipline",
                    severity="high",
                    title="Dataset primary key is not unique",
                    detail=f"{name} has {duplicates} duplicate primary-key rows.",
                    remediation="Fix duplicate keys or document an explicit many-to-many structure before merging.",
                    score_impact=16,
                    path=path_value,
                )
            )
    return findings


def detect_merge_workflow(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    analysis_rel = str(config.get("paths", {}).get("analysis", "")).strip().strip("/")
    for path in files:
        if path.suffix not in {".py", ".R", ".r", ".do"}:
            continue
        rel = path.relative_to(project_root).as_posix()
        if analysis_rel and not rel.startswith(f"{analysis_rel}/") and rel != analysis_rel:
            continue
        text = _read_text(path)
        merge_count = sum(len(pattern.findall(text)) for pattern in MERGE_PATTERNS)
        if merge_count >= 2:
            findings.append(
                make_finding(
                    dimension="relational_data_discipline",
                    severity="medium",
                    title="Analysis script performs repeated merges",
                    detail=f"{rel} contains {merge_count} merge/join operations in the analysis stage.",
                    remediation="Push data construction into earlier build stages and keep analysis scripts closer to final estimation or output production.",
                    score_impact=8,
                    path=rel,
                )
            )
    return findings


def detect_sample_construction_drift(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    line_locations: defaultdict[str, set[str]] = defaultdict(set)
    for path in files:
        if path.suffix not in {".py", ".R", ".r", ".do"}:
            continue
        rel = path.relative_to(project_root).as_posix()
        for raw_line in _read_text(path).splitlines():
            line = raw_line.strip()
            if len(line) < 15:
                continue
            if not any(pattern.search(line) for pattern in SAMPLE_PATTERNS):
                continue
            normalized = re.sub(r"\s+", " ", line)
            line_locations[normalized].add(rel)
    repeated = [(line, locations) for line, locations in line_locations.items() if len(locations) > 1]
    if repeated:
        line, locations = sorted(repeated, key=lambda item: (-len(item[1]), item[0]))[0]
        findings.append(
            make_finding(
                dimension="software_hygiene_and_redundancy",
                severity="medium",
                title="Repeated sample-construction logic across scripts",
                detail=f"The line `{line}` appears in multiple scripts: {', '.join(sorted(locations)[:3])}.",
                remediation="Centralize or clearly stage shared sample-construction logic so inclusion rules do not drift across files.",
                score_impact=8,
                path=sorted(locations)[0],
            )
        )
    return findings


def detect_software_hygiene(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    duplicate_blocks: Counter[tuple[str, ...]] = Counter()
    duplicate_examples: dict[tuple[str, ...], str] = {}
    function_defs: defaultdict[str, list[str]] = defaultdict(list)
    python_imports: list[tuple[Path, list[str], set[str]]] = []

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if path.suffix not in CODE_SUFFIXES:
            continue
        text = _read_text(path)
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        if len(lines) > 220:
            findings.append(
                make_finding(
                    dimension="software_hygiene_and_redundancy",
                    severity="medium",
                    title="Oversized code script",
                    detail=f"{rel} has {len(lines)} non-empty lines and likely carries too many responsibilities.",
                    remediation="Split the script by stage or purpose only when the split makes the pipeline easier to understand.",
                    score_impact=6,
                    path=rel,
                )
            )
        for index in range(max(0, len(lines) - 4)):
            block = tuple(lines[index : index + 5])
            duplicate_blocks[block] += 1
            duplicate_examples.setdefault(block, rel)
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.asname or alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.extend(alias.asname or alias.name for alias in node.names)
                elif isinstance(node, ast.FunctionDef):
                    function_defs[node.name].append(rel)
            python_imports.append((path, imported, used_names))
        elif path.suffix.lower() == ".r":
            matches = re.findall(r"([A-Za-z0-9_]+)\s*<-\s*function\s*\(", text)
            for name in matches:
                function_defs[name].append(rel)

    for path, imported, used_names in python_imports:
        rel = path.relative_to(project_root).as_posix()
        unused = [name for name in imported if name not in used_names and name != "*"]
        if unused:
            findings.append(
                make_finding(
                    dimension="software_hygiene_and_redundancy",
                    severity="medium",
                    title="Unused Python imports",
                    detail=f"{rel} imports symbols that are not used: {', '.join(sorted(unused)[:5])}.",
                    remediation="Remove unused imports so the analysis logic is easier to scan.",
                    score_impact=6,
                    path=rel,
                )
            )

    for name, locations in function_defs.items():
        unique_locations = sorted(set(locations))
        if len(unique_locations) > 1:
            findings.append(
                make_finding(
                    dimension="software_hygiene_and_redundancy",
                    severity="medium",
                    title="Repeated function name across scripts",
                    detail=f"`{name}` is defined in multiple scripts: {', '.join(unique_locations[:3])}.",
                    remediation="Consolidate repeated transformation logic or make the stage distinction explicit.",
                    score_impact=5,
                    path=unique_locations[0],
                )
            )

    for block, count in duplicate_blocks.items():
        if count > 1 and len(" ".join(block)) > 80:
            findings.append(
                make_finding(
                    dimension="software_hygiene_and_redundancy",
                    severity="medium",
                    title="Repeated code block across project",
                    detail=f"A 5-line code block appears {count} times; example in {duplicate_examples[block]}.",
                    remediation="Factor repeated cleaning or path setup logic into a shared helper, or make stage-specific duplication explicit.",
                    score_impact=7,
                    path=duplicate_examples[block],
                )
            )
            break
    return findings


def detect_heavy_stage_smoke_gaps(config: dict) -> list[Finding]:
    findings: list[Finding] = []
    for stage in config.get("pipeline", {}).get("heavy_stages", []):
        name = stage.get("name", "<unnamed>")
        if not stage.get("smoke_command") and not stage.get("justification"):
            findings.append(
                make_finding(
                    dimension="automation_and_one_command_rebuild",
                    severity="medium",
                    title="Heavy stage has no smoke command",
                    detail=f"Heavy stage `{name}` is declared without a smoke command or explicit justification.",
                    remediation="Add `smoke_command` for a cheap confidence check, or document why only full runs make sense.",
                    score_impact=6,
                )
            )
    return findings
