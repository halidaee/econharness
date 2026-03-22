"""Static detectors for economics research projects."""

from __future__ import annotations

import ast
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from econharness.function_state import (
    iter_global_write_issues,
    iter_outer_scope_dependency_issues,
)
from econharness.lookup_reconstruction import (
    cluster_repeated_lookup_candidates,
    extract_lookup_candidates,
)
from econharness.models import Finding
from econharness.self_documenting import (
    iter_vague_filename_issues,
    iter_vague_function_name_issues,
)
from econharness.slow_stages import iter_slow_stage_issues
from econharness.stage_contracts import iter_stage_contract_issues
from econharness.stages import normalize_stages
from econharness.tests_presence import summarize_test_presence
from econharness.version_control import (
    iter_filename_variant_clusters,
    iter_versioned_filename_issues,
)

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"/home/[^/\s]+/"),
    re.compile(r"[A-Z]:\\\\Users\\\\"),
    re.compile(r"/Volumes/"),
    re.compile(r"/mnt/"),
]
HPC_PATH_ROOT_PATTERN = re.compile(r"/(?:scratch|gpfs|lustre|beegfs)/")
MACHINE_SPECIFIC_HINTS = ("Desktop", "Downloads", "Dropbox", "OneDrive", "Documents")
MANUAL_STEP_PATTERNS = [
    re.compile(r"\bedit (this|the) file by hand\b", re.IGNORECASE),
    re.compile(r"\bmanually\b", re.IGNORECASE),
    re.compile(r"\bcopy (this|the) .* into\b", re.IGNORECASE),
    re.compile(r"\brun this manually\b", re.IGNORECASE),
]
SCRIPT_SUFFIXES = {".py", ".R", ".r", ".qmd", ".sh", ".md", ".txt", ".do", ".slurm", ".job"}
CODE_SUFFIXES = {".py", ".R", ".r", ".sh"}
PAPER_SUFFIXES = {".qmd", ".Rmd", ".rmd", ".tex", ".md"}
R_JOIN_FUNCTIONS = {"left_join", "right_join", "inner_join", "full_join"}
R_LOAD_FUNCTIONS = {"readRDS", "read_csv", "read_delim", "read_tsv", "fread", "read_dta"}
R_DERIVATION_FUNCTIONS = {
    "mutate",
    "transmute",
    "summarise",
    "summarize",
    "pivot_longer",
    "pivot_wider",
    "separate",
    "separate_wider_delim",
    "unite",
    "group_by",
    "ungroup",
    "quantile",
    "ntile",
    "cut",
    "rowMeans",
    "across",
    "case_when",
}
R_IDENTIFIER_STOPWORDS = {
    "all_of",
    "any_of",
    "c",
    "data",
    "desc",
    "ends_with",
    "everything",
    "false",
    "first",
    "function",
    "ifelse",
    "na",
    "na_real_",
    "names",
    "starts_with",
    "true",
    "where",
}
SAMPLE_PATTERNS = [
    re.compile(r"\bfilter\s*\("),
    re.compile(r"\bsubset\s*\("),
    re.compile(r"\bdrop if\b", re.IGNORECASE),
    re.compile(r"\bkeep if\b", re.IGNORECASE),
    re.compile(r"\banalysis_sample\b"),
    re.compile(r"\bsample_flag\b"),
    re.compile(r"\beligible\s*=="),
]
OVERSIZED_SCRIPT_TIERS = [
    (1000, "high", 8),
    (500, "medium", 4),
    (250, "low", 2),
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


def _mask_string_literals(text: str) -> str:
    return re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", '""', text, flags=re.DOTALL)


def _paren_delta(text: str) -> int:
    masked = _mask_string_literals(text)
    opens = sum(masked.count(char) for char in "([{")
    closes = sum(masked.count(char) for char in ")]}")
    return opens - closes


def _extract_balanced_call(text: str, open_paren_index: int) -> tuple[str, int] | None:
    depth = 0
    in_string: str | None = None
    escaped = False
    for index in range(open_paren_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_index + 1 : index], index
    return None


def _split_top_level_args(text: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth = 0
    in_string: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
            continue
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            depth -= 1
            continue
        if char == "," and depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        args.append(tail)
    return args


def _iter_r_function_calls(text: str, function_names: set[str]) -> Iterable[tuple[str, str]]:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_.]+::)?({'|'.join(sorted(map(re.escape, function_names), key=len, reverse=True))})\s*\(",
    )
    for match in pattern.finditer(text):
        open_paren_index = text.find("(", match.end() - 1)
        if open_paren_index < 0:
            continue
        extracted = _extract_balanced_call(text, open_paren_index)
        if extracted is None:
            continue
        args_text, _ = extracted
        yield match.group(1), args_text


def _extract_r_assignments(text: str) -> defaultdict[str, list[dict[str, object]]]:
    assignments: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-\s*(.*)$", line)
        if not match:
            index += 1
            continue
        start_line = index + 1
        block_lines = [line]
        rhs_lines = [match.group(2)]
        depth = _paren_delta(line)
        index += 1
        while index < len(lines):
            next_line = lines[index]
            stripped = next_line.strip()
            if depth <= 0 and stripped == "":
                break
            if depth <= 0 and re.match(r"^\s*[A-Za-z][A-Za-z0-9_.]*\s*<-\s*", next_line):
                break
            if (
                depth <= 0
                and not next_line.startswith((" ", "\t"))
                and not re.match(r"^\s*(%>%|\|>|\)|\+|,)", next_line)
            ):
                break
            block_lines.append(next_line)
            rhs_lines.append(next_line)
            depth += _paren_delta(next_line)
            index += 1
        assignments[match.group(1)].append(
            {
                "line": start_line,
                "text": "\n".join(block_lines),
                "rhs": "\n".join(rhs_lines).strip(),
            }
        )
    return assignments


def _extract_artifact_label(expr: str) -> str | None:
    if not any(f"{name}(" in expr or f"{name} (" in expr for name in R_LOAD_FUNCTIONS):
        return None
    quoted = re.findall(r"['\"]([^'\"]+\.[A-Za-z0-9]+)['\"]", expr)
    if not quoted:
        return None
    return Path(quoted[-1]).name


def _leading_r_source_variable(expr: str) -> str | None:
    match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*(?:%>%|\|>|$)", expr)
    if not match:
        return None
    token = match.group(1)
    if token in R_IDENTIFIER_STOPWORDS or token in R_LOAD_FUNCTIONS:
        return None
    return token


def _first_r_argument_variable(expr: str) -> str | None:
    call_match = re.match(r"^\s*(?:[A-Za-z0-9_.]+::)?[A-Za-z][A-Za-z0-9_.]*\s*\(", expr)
    if not call_match:
        return None
    open_paren_index = expr.find("(", call_match.end() - 1)
    if open_paren_index < 0:
        return None
    extracted = _extract_balanced_call(expr, open_paren_index)
    if extracted is None:
        return None
    args_text, _ = extracted
    args = _split_top_level_args(args_text)
    if not args:
        return None
    first_arg = args[0].strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", first_arg):
        return first_arg
    return None


def _extract_identifier_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.]*\b", text)
        if token not in R_IDENTIFIER_STOPWORDS and not token[0].isupper()
    }
    return tokens


def _extract_select_columns(text: str) -> set[str]:
    columns: set[str] = set()
    for _, args_text in _iter_r_function_calls(text, {"select"}):
        for arg in _split_top_level_args(args_text):
            columns.update(
                token
                for token in _extract_identifier_tokens(arg)
                if token not in {"select", "across"}
            )
            columns.update(re.findall(r"['\"]([^'\"]+)['\"]", arg))
    return columns


def _extract_created_columns(text: str) -> set[str]:
    columns: set[str] = set()
    for function_name, args_text in _iter_r_function_calls(
        text,
        {"mutate", "transmute", "summarise", "summarize", "rename"},
    ):
        for arg in _split_top_level_args(args_text):
            match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*=", arg)
            if match:
                columns.add(match.group(1))
        if function_name in {"mutate", "transmute"}:
            name_templates = re.findall(r"\.names\s*=\s*['\"]([^'\"]+)['\"]", args_text)
            for template in name_templates:
                if "quint" in template:
                    columns.add("quality_quint")
    for _, args_text in _iter_r_function_calls(text, {"pivot_longer", "pivot_wider", "separate", "separate_wider_delim"}):
        for arg in _split_top_level_args(args_text):
            for parameter in {"names_to", "values_to", "names_from", "values_from"}:
                match = re.match(rf"^\s*{parameter}\s*=\s*['\"]([^'\"]+)['\"]", arg)
                if match:
                    columns.add(match.group(1))
    return columns


def _extract_transform_tokens(text: str) -> set[str]:
    transforms: set[str] = set()
    for function_name, _ in _iter_r_function_calls(text, R_DERIVATION_FUNCTIONS):
        transforms.add(function_name.lower())
    return transforms


def _latest_assignment_before(
    assignments: defaultdict[str, list[dict[str, object]]],
    var_name: str,
    before_line: int,
) -> dict[str, object] | None:
    for assignment in reversed(assignments.get(var_name, [])):
        line = int(assignment["line"])
        if line < before_line:
            return assignment
    return None


def _empty_lookup_summary() -> dict[str, object]:
    return {
        "artifact": None,
        "created_columns": set(),
        "output_columns": set(),
        "transform_tokens": set(),
    }


def _resolve_r_variable(
    var_name: str,
    assignments: defaultdict[str, list[dict[str, object]]],
    before_line: int,
    seen: set[tuple[str, int]],
) -> dict[str, object]:
    assignment = _latest_assignment_before(assignments, var_name, before_line)
    if assignment is None:
        return _empty_lookup_summary()
    identity = (var_name, int(assignment["line"]))
    if identity in seen:
        return _empty_lookup_summary()

    rhs = str(assignment["rhs"])
    artifact = _extract_artifact_label(rhs)
    created_columns = _extract_created_columns(rhs)
    output_columns = _extract_select_columns(rhs) or set(created_columns)
    transform_tokens = _extract_transform_tokens(rhs)

    source_var = _leading_r_source_variable(rhs) or _first_r_argument_variable(rhs)
    if source_var:
        parent = _resolve_r_variable(
            source_var,
            assignments,
            int(assignment["line"]),
            seen | {identity},
        )
        artifact = artifact or parent["artifact"]
        created_columns |= set(parent["created_columns"])
        transform_tokens |= set(parent["transform_tokens"])
        if not output_columns:
            output_columns = set(parent["output_columns"])

    return {
        "artifact": artifact,
        "created_columns": created_columns,
        "output_columns": output_columns,
        "transform_tokens": transform_tokens,
    }


def _analyze_r_lookup_expression(
    expr: str,
    assignments: defaultdict[str, list[dict[str, object]]],
    before_line: int,
) -> dict[str, object]:
    expr = expr.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", expr):
        return _resolve_r_variable(expr, assignments, before_line, set())

    artifact = _extract_artifact_label(expr)
    created_columns = _extract_created_columns(expr)
    output_columns = _extract_select_columns(expr) or set(created_columns)
    transform_tokens = _extract_transform_tokens(expr)

    source_var = _leading_r_source_variable(expr) or _first_r_argument_variable(expr)
    if source_var:
        parent = _resolve_r_variable(source_var, assignments, before_line, set())
        artifact = artifact or parent["artifact"]
        created_columns |= set(parent["created_columns"])
        transform_tokens |= set(parent["transform_tokens"])

    return {
        "artifact": artifact,
        "created_columns": created_columns,
        "output_columns": output_columns,
        "transform_tokens": transform_tokens,
    }


def _normalize_column_family(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    normalized = re.sub(r"_(global|within_firm|overall|pooled)$", "", normalized)
    if normalized.endswith("_quintile"):
        normalized = normalized.removesuffix("_quintile") + "_quint"
    return normalized


def _extract_lookup_families(summary: dict[str, object], join_keys: tuple[str, ...]) -> set[str]:
    created_columns = {
        _normalize_column_family(column)
        for column in set(summary["created_columns"])
    }
    output_columns = {
        _normalize_column_family(column)
        for column in set(summary["output_columns"])
    }
    join_families = {_normalize_column_family(key) for key in join_keys}
    families = {column for column in created_columns & output_columns if column and column not in join_families}
    return families


def _lookup_candidates_match(left: dict[str, object], right: dict[str, object]) -> bool:
    if left["artifact"] != right["artifact"]:
        return False
    if left["join_keys"] != right["join_keys"]:
        return False
    shared_families = set(left["families"]) & set(right["families"])
    if not shared_families:
        return False
    shared_transforms = set(left["transform_tokens"]) & set(right["transform_tokens"])
    return bool(shared_transforms) or len(shared_families) >= 2


def detect_automation(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    commands = config.get("pipeline", {}).get("command", {})
    fast = str(commands.get("fast", "")).strip()
    full = str(commands.get("full", "")).strip()
    slow_stages = [
        stage
        for stage in normalize_stages(config).get("stages", [])
        if bool(stage.get("slow"))
    ]
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
    if not fast and not slow_stages:
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


SUBMISSION_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}
# Matches: module load R/4.3.1  |  ml R/4.3.1  |  module load R  |  ml R
# Also handles multi-module lines: module load R/4.3.1 gcc/12.2
# Anchored to start of line (with MULTILINE) so .+ stops at end of line.
_MODULE_LOAD_PATTERN = re.compile(
    r"^[ \t]*(?:module\s+load|ml)\s+(.+?)[ \t]*$",
    re.MULTILINE,
)
# Matches an individual module token: name (with optional /version)
_MODULE_ITEM_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9_\-+.]*)(?:/([A-Za-z0-9._\-]+))?")


def _collect_module_loads(files: list[Path]) -> dict[str, dict]:
    """Collect module load statements from submission scripts.

    Returns:
        {
          "pinned":   {module_name: {version: [Path, ...]}},
          "unpinned": {module_name: [Path, ...]},
        }
    """
    pinned: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    unpinned: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        if path.suffix not in SUBMISSION_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        for load_match in _MODULE_LOAD_PATTERN.finditer(text):
            modules_str = load_match.group(1)
            for item_match in _MODULE_ITEM_PATTERN.finditer(modules_str):
                name = item_match.group(1)
                version = item_match.group(2)
                if version:
                    pinned[name][version].append(path)
                else:
                    unpinned[name].append(path)
    return {"pinned": dict(pinned), "unpinned": dict(unpinned)}


def detect_environment_reproducibility(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    has_r = any(path.suffix.lower() in {".r", ".qmd", ".rmd"} for path in files)
    has_python = any(path.suffix.lower() == ".py" for path in files)
    env_config = config.get("environment", {})
    module_data = _collect_module_loads(files)
    pinned = module_data["pinned"]
    unpinned = module_data["unpinned"]

    # R lockfile check — local reproducibility concern, always fires if lockfile absent
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
            # Cluster advisory: if pinned module loads exist, note local dev gap separately
            r_pinned = pinned.get("R", {})
            if r_pinned:
                findings.append(
                    make_finding(
                        dimension="cluster_environment",
                        severity="low",
                        title="R cluster environment pinned via module load — consider renv for local dev",
                        detail=(
                            "Version-pinned `module load R/...` statements satisfy cluster reproducibility. "
                            "An `renv.lock` would additionally cover local development reproducibility."
                        ),
                        remediation=(
                            "Consider adopting `renv` for local development reproducibility. "
                            "The module load already handles cluster execution."
                        ),
                        score_impact=3,
                    )
                )

    # Python lockfile check — local reproducibility concern, always fires if lockfile absent
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
            # Cluster advisory: if pinned module loads exist, note local dev gap separately
            py_pinned = {k: v for k, v in pinned.items() if k.lower() in ("python", "python3")}
            if py_pinned:
                findings.append(
                    make_finding(
                        dimension="cluster_environment",
                        severity="low",
                        title="Python cluster environment pinned via module load — consider pixi for local dev",
                        detail=(
                            "Version-pinned `module load python/...` statements satisfy cluster reproducibility. "
                            "A `pixi.lock` would additionally cover local development reproducibility."
                        ),
                        remediation="Consider adopting `pixi` for local development reproducibility.",
                        score_impact=3,
                    )
                )

    # Unpinned module loads — cluster env concern
    for module_name, paths_list in unpinned.items():
        example = paths_list[0].name
        findings.append(
            make_finding(
                dimension="cluster_environment",
                severity="medium",
                title=f"Module loaded without version pin: `{module_name}`",
                detail=(
                    f"`module load {module_name}` (no version) found in submission scripts "
                    f"(e.g. `{example}`). The loaded version is cluster-default and may change silently."
                ),
                remediation=f"Pin the version explicitly: `module load {module_name}/<version>`.",
                score_impact=8,
            )
        )

    # Version inconsistency across scripts — cluster env concern
    for module_name, version_map in pinned.items():
        if len(version_map) > 1:
            version_summary = ", ".join(
                f"`{v}` ({p[0].name})" for v, p in sorted(version_map.items())
            )
            findings.append(
                make_finding(
                    dimension="cluster_environment",
                    severity="high",
                    title=f"Module version inconsistent across scripts: `{module_name}`",
                    detail=(
                        f"Different scripts load different versions of `{module_name}`: "
                        f"{version_summary}. Results depend on which script ran."
                    ),
                    remediation=f"Standardize all submission scripts to load the same version of `{module_name}`.",
                    score_impact=12,
                )
            )

    return findings


def _extract_path_token(text: str, start: int) -> str:
    """Extract a path token from `text` starting at `start` until whitespace or quote."""
    end = start
    while end < len(text) and text[end] not in (" ", "\t", "\n", '"', "'", ";", ")"):
        end += 1
    return text[start:end]


def detect_path_portability(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    allowed_prefixes: list[str] = config.get("path_portability", {}).get("allowed_prefixes", [])
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
            for match in HPC_PATH_ROOT_PATTERN.finditer(text):
                path_token = _extract_path_token(text, match.start())
                if allowed_prefixes and any(path_token.startswith(p) for p in allowed_prefixes):
                    continue
                findings.append(
                    make_finding(
                        dimension="path_portability",
                        severity="high",
                        title="HPC cluster path hardcoded in project source",
                        detail=f"{rel} contains a hardcoded HPC filesystem path (`{path_token}`).",
                        remediation=(
                            "Replace with an environment variable such as `$SCRATCH`, `$WORK`, "
                            "or declare the prefix in `.econharness.yml` under `path_portability.allowed_prefixes`."
                        ),
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


_SBATCH_PATTERN = re.compile(r"^#SBATCH\b", re.MULTILINE)
_SET_E_BODY_PATTERN = re.compile(r"(?m)(?:^|\s)set\s+(?:-[a-zA-Z]*e[a-zA-Z]*\b|-o\s+errexit)")
_SHEBANG_DASH_E_PATTERN = re.compile(r"^#!.*\bbash\b.*\s-[a-zA-Z]*e(?:\s|$)")
BATCH_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}


def detect_hpc_batch_script_health(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in BATCH_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        if not _SBATCH_PATTERN.search(text):
            continue
        first_line = text.split("\n", 1)[0]
        if _SHEBANG_DASH_E_PATTERN.match(first_line):
            continue
        if _SET_E_BODY_PATTERN.search(text):
            continue
        rel = path.relative_to(project_root).as_posix()
        findings.append(
            make_finding(
                dimension="path_portability",
                severity="medium",
                title="Batch script missing `set -e`",
                detail=(
                    f"{rel} is a Slurm batch script without `set -e`. "
                    "A failed command will be silently swallowed and the job will continue."
                ),
                remediation=(
                    "Add `set -e` near the top of the script so that any failed command "
                    "causes the job to exit immediately with a non-zero code."
                ),
                score_impact=7,
                path=rel,
            )
        )
    return findings


ARRAY_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}
_TASK_ID_PATTERN = re.compile(r"\$\{?SLURM_ARRAY_TASK_ID\}?")
# Shell redirections and common HPC output flags
_OUTPUT_REDIRECT_PATTERN = re.compile(
    r"(?:>>?)\s*(\S+)"
    r"|(?:-o|--output(?:=|\s))(\S+)"
    r"|(?:-e|--error(?:=|\s))(\S+)",
)
_DOCUMENTATION_COMMENT_PATTERN = re.compile(r"^\s*#(?!SBATCH)", re.MULTILINE)
_NEARBY_WINDOW = 5  # lines above/below task ID usage to look for a comment


def detect_job_array_expansion(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in ARRAY_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        if not _SBATCH_PATTERN.search(text):
            continue
        if not _TASK_ID_PATTERN.search(text):
            continue
        rel = path.relative_to(project_root).as_posix()
        lines = text.splitlines()

        # ── Collision check: output paths that don't include $SLURM_ARRAY_TASK_ID ──
        collision_found = False
        for match in _OUTPUT_REDIRECT_PATTERN.finditer(text):
            output_path_str = match.group(1) or match.group(2) or match.group(3) or ""
            if not output_path_str:
                continue
            # Skip #SBATCH directive lines (use Slurm %a/%A substitution, not shell vars)
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_text = text[line_start:text.find("\n", match.start())]
            if line_text.lstrip().startswith("#SBATCH"):
                continue
            # If the path contains any shell variable reference the author intentionally
            # parameterized it — we cannot trace variable assignments, so trust it.
            if "$" in output_path_str:
                continue
            findings.append(
                make_finding(
                    dimension="path_portability",
                    severity="medium",
                    title="Job array script may write to same output path from all tasks",
                    detail=(
                        f"{rel} uses `$SLURM_ARRAY_TASK_ID` but may write to "
                        f"`{output_path_str}` without including the task ID in the path. "
                        "All tasks could overwrite each other's output."
                    ),
                    remediation=(
                        "Include `$SLURM_ARRAY_TASK_ID` in the output filename: "
                        "e.g. `results_${SLURM_ARRAY_TASK_ID}.csv`."
                    ),
                    score_impact=10,
                    path=rel,
                )
            )
            collision_found = True
            break  # one collision finding per file is sufficient

        # ── Undocumented mapping: no comment near any $SLURM_ARRAY_TASK_ID usage ──
        task_id_linenos = [
            i for i, line in enumerate(lines)
            if _TASK_ID_PATTERN.search(line)
        ]
        has_nearby_comment = False
        for lineno in task_id_linenos:
            window_start = max(0, lineno - _NEARBY_WINDOW)
            window_end = min(len(lines), lineno + _NEARBY_WINDOW + 1)
            for nearby in lines[window_start:window_end]:
                stripped = nearby.strip()
                # A non-SBATCH, non-shebang comment counts as documentation
                if (
                    stripped.startswith("#")
                    and not stripped.startswith("#SBATCH")
                    and not stripped.startswith("#!")
                ):
                    has_nearby_comment = True
                    break
            if has_nearby_comment:
                break

        if not has_nearby_comment and task_id_linenos:
            findings.append(
                make_finding(
                    dimension="path_portability",
                    severity="low",
                    title="Job array index-to-parameter mapping is undocumented",
                    detail=(
                        f"{rel} uses `$SLURM_ARRAY_TASK_ID` with no nearby comment "
                        "explaining what each index value represents."
                    ),
                    remediation=(
                        "Add a comment near the `$SLURM_ARRAY_TASK_ID` usage explaining the mapping, "
                        "e.g.: `# Index N corresponds to country N in params/countries.csv`."
                    ),
                    score_impact=3,
                    path=rel,
                )
            )
    return findings


def detect_version_control_discipline(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []

    for issue in iter_versioned_filename_issues(project_root, config, files):
        findings.append(
            make_finding(
                dimension="version_control_discipline",
                severity="low",
                title="Filename appears to encode manual version history",
                detail=f"{issue.path} includes {issue.reason}, which suggests the repo is using filenames to track versions.",
                remediation="Keep one canonical filename and rely on git history instead of suffixes like `final`, `new`, `v2`, or date stamps.",
                score_impact=3,
                path=issue.path,
            )
        )

    for cluster in iter_filename_variant_clusters(project_root, config, files):
        findings.append(
            make_finding(
                dimension="version_control_discipline",
                severity="medium",
                title="Parallel filename variants suggest manual versioning",
                detail=(
                    f"Files sharing the canonical name `{cluster.canonical_name}` appear in parallel: "
                    f"{', '.join(cluster.paths[:4])}."
                ),
                remediation="Collapse competing filename variants into one canonical file and preserve history in git rather than sibling copies.",
                score_impact=5,
                path=cluster.paths[0],
            )
        )

    return findings


def detect_self_documenting_clarity(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []

    for issue in iter_vague_filename_issues(project_root, files):
        findings.append(
            make_finding(
                dimension="self_documenting_clarity",
                severity="low",
                title="Code filename is too generic",
                detail=f"{issue.path} uses a {issue.reason}, which makes the file's purpose harder to infer from its name.",
                remediation="Rename the file to describe its stage or purpose rather than using placeholders like `tmp`, `script2`, or `analysis2`.",
                score_impact=2,
                path=issue.path,
            )
        )

    for issue in iter_vague_function_name_issues(project_root, files):
        findings.append(
            make_finding(
                dimension="self_documenting_clarity",
                severity="low",
                title="Function name is too generic",
                detail=f"{issue.path} defines `{issue.subject}`, a {issue.reason} that does not communicate purpose clearly.",
                remediation="Rename reusable functions so their names describe what they compute or transform.",
                score_impact=2,
                path=issue.path,
            )
        )

    return findings


def detect_function_state_discipline(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for issue in iter_global_write_issues(project_root, files):
        findings.append(
            make_finding(
                dimension="software_hygiene_and_redundancy",
                severity="medium",
                title="Function writes to hidden global state",
                detail=f"{issue.path} {issue.detail}.",
                remediation="Pass state explicitly through function arguments and return values instead of mutating module-level or global variables from inside functions.",
                score_impact=5,
                path=issue.path,
            )
        )
    grouped_outer_scope: defaultdict[str, list[object]] = defaultdict(list)
    for issue in iter_outer_scope_dependency_issues(project_root, files):
        grouped_outer_scope[issue.path].append(issue)
    for path, issues in grouped_outer_scope.items():
        if len(issues) < 2:
            continue
        function_names = ", ".join(f"`{issue.function_name}`" for issue in issues[:4])
        findings.append(
            make_finding(
                dimension="software_hygiene_and_redundancy",
                severity="low",
                title="Function depends on outer scope",
                detail=(
                    f"{path} has {len(issues)} function(s) that depend on same-file module-level names rather than explicit inputs, "
                    f"including {function_names}."
                ),
                remediation="Pass shared inputs explicitly into the function or move the dependency into a clearly documented config layer.",
                score_impact=2,
                path=path,
            )
        )
    return findings


def detect_tests_presence(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    summary = summarize_test_presence(project_root, config, files)
    findings: list[Finding] = []

    if summary.helper_heavy and not summary.test_paths and not summary.has_tests_command:
        findings.append(
            make_finding(
                dimension="automation_and_one_command_rebuild",
                severity="medium",
                title="Helper-heavy project has no automated tests",
                detail="The repo defines reusable helper code but does not declare a test command or include conventional test files.",
                remediation="Add a lightweight automated test path and declare it under `pipeline.command.tests` in `.econharness.yml`.",
                score_impact=6,
            )
        )

    if summary.test_paths and not summary.has_tests_command:
        findings.append(
            make_finding(
                dimension="automation_and_one_command_rebuild",
                severity="low",
                title="Test files exist without configured test command",
                detail=f"Conventional test files exist, including {', '.join(summary.test_paths[:3])}, but `pipeline.command.tests` is not configured.",
                remediation="Declare one authoritative test command so agents and collaborators know how to run the project checks.",
                score_impact=3,
                path=summary.test_paths[0],
            )
        )

    return findings


def detect_stage_contracts(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for issue in iter_stage_contract_issues(project_root, config, files):
        if issue.kind == "unmatched":
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="low",
                    title="Code file is not assigned to a configured stage",
                    detail=f"{issue.path} does not match any configured `stages[].match` pattern.",
                    remediation="Assign code files to explicit stages so read/write contracts can be enforced consistently.",
                    score_impact=2,
                    path=issue.path,
                )
            )
        elif issue.kind == "ambiguous":
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="medium",
                    title="Code file matches multiple configured stages",
                    detail=f"{issue.path} matches multiple stage patterns: {', '.join(issue.matched_stages)}.",
                    remediation="Make stage match patterns mutually exclusive so each code file has one clear contract.",
                    score_impact=4,
                    path=issue.path,
                )
            )
        elif issue.kind == "read_violation":
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="medium",
                    title="Stage reads outside declared roots",
                    detail=f"{issue.path} belongs to stage `{issue.stage_name}` but reads `{issue.referenced_path}` outside its configured `read_roots`.",
                    remediation="Update the stage contract or move the read so the file only consumes declared stage inputs.",
                    score_impact=4,
                    path=issue.path,
                )
            )
        elif issue.kind == "write_violation":
            findings.append(
                make_finding(
                    dimension="directory_and_stage_structure",
                    severity="medium",
                    title="Stage writes outside declared roots",
                    detail=f"{issue.path} belongs to stage `{issue.stage_name}` but writes `{issue.referenced_path}` outside its configured `write_roots`.",
                    remediation="Update the stage contract or write outputs into the stage's declared destinations.",
                    score_impact=5,
                    path=issue.path,
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
    candidates = []
    for path in files:
        if path.suffix.lower() not in {".r", ".py"}:
            continue
        text = _read_text(path)
        candidates.extend(extract_lookup_candidates(path, text, project_root=project_root))

    findings: list[Finding] = []
    for cluster in cluster_repeated_lookup_candidates(candidates):
        family_phrase = ", ".join(cluster.families[:3]) if cluster.families else "derived lookup columns"
        findings.append(
            make_finding(
                dimension="relational_data_discipline",
                severity=cluster.severity,
                title="Repeated derived lookup reconstruction across scripts",
                detail=(
                    f"A derived lookup from `{cluster.source_artifact}` joined on "
                    f"`{', '.join(cluster.join_keys)}` is rebuilt in multiple scripts: "
                    f"{', '.join(cluster.paths[:4])}. Shared derived families include {family_phrase}."
                ),
                remediation="Materialize the derived lookup once as an intermediate artifact and load it downstream.",
                score_impact=cluster.score_impact,
                path=cluster.paths[0],
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
        line_count = len(lines)
        for threshold, severity, score_impact in OVERSIZED_SCRIPT_TIERS:
            if line_count >= threshold:
                findings.append(
                    make_finding(
                        dimension="software_hygiene_and_redundancy",
                        severity=severity,
                        title="Oversized code script",
                        detail=f"{rel} has {line_count} non-empty lines and likely carries too many responsibilities.",
                        remediation="Split the script by stage or purpose only when the split makes the pipeline easier to understand.",
                        score_impact=score_impact,
                        path=rel,
                    )
                )
                break
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


def detect_slow_stage_discipline(config: dict) -> list[Finding]:
    findings: list[Finding] = []
    for issue in iter_slow_stage_issues(config):
        if issue.kind == "missing_fast":
            findings.append(
                make_finding(
                    dimension="automation_and_one_command_rebuild",
                    severity="medium",
                    title="Slow stage is declared without a fast verification path",
                    detail=(
                        "Slow stages "
                        f"{', '.join(issue.stage_names)} are declared, but `pipeline.command.fast` is empty."
                    ),
                    remediation="Add `pipeline.command.fast` that skips or stubs slow stages while still checking pipeline wiring.",
                    score_impact=8,
                )
            )
        elif issue.kind == "fast_matches_full":
            findings.append(
                make_finding(
                    dimension="automation_and_one_command_rebuild",
                    severity="medium",
                    title="Fast verification command matches full rebuild despite slow stages",
                    detail=(
                        "`pipeline.command.fast` and `pipeline.command.full` resolve to the same command even though slow stages "
                        f"{', '.join(issue.stage_names)} are declared."
                    ),
                    remediation="Make `pipeline.command.fast` materially cheaper than the full rebuild, or unset `slow: true` on stages that are not actually expensive.",
                    score_impact=8,
                )
            )
        elif issue.kind == "missing_outputs" and issue.stage_name:
            findings.append(
                make_finding(
                    dimension="automation_and_one_command_rebuild",
                    severity="medium",
                    title="Slow stage does not declare outputs",
                    detail=f"Slow stage `{issue.stage_name}` is marked expensive but does not declare any outputs to preserve and reuse.",
                    remediation="Add `stages[].outputs` for the artifacts this stage produces so downstream work can reuse them.",
                    score_impact=6,
                )
            )
        elif issue.kind == "no_reusable_outputs" and issue.stage_name:
            findings.append(
                make_finding(
                    dimension="automation_and_one_command_rebuild",
                    severity="medium",
                    title="Slow stage has no reusable artifact roots",
                    detail=(
                        f"Slow stage `{issue.stage_name}` only declares outputs in non-reusable roots: "
                        f"{', '.join(issue.outputs)}."
                    ),
                    remediation="Point `stages[].outputs` at derived or output roots that downstream stages can reuse.",
                    score_impact=6,
                )
            )
    return findings


def detect_heavy_stage_smoke_gaps(config: dict) -> list[Finding]:
    return detect_slow_stage_discipline(config)
