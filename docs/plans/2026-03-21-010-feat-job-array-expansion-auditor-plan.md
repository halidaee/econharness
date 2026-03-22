---
title: "feat: Job Array Expansion Auditor — output collision and undocumented mapping detection"
type: feat
status: active
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md
---

# feat: Job Array Expansion Auditor

## Overview

Add a new detector `detect_job_array_expansion` that identifies Slurm job array scripts (files with `#SBATCH` and `$SLURM_ARRAY_TASK_ID`) and checks for two silent failure modes:

1. **Output path collision (medium)**: The script writes to a path that doesn't include `$SLURM_ARRAY_TASK_ID` directly — all tasks overwrite each other's outputs silently.
2. **Undocumented index-to-parameter mapping (low advisory)**: The script uses `$SLURM_ARRAY_TASK_ID` but has no co-located comment explaining what each index value represents.

**Prerequisite:** Plan 007 should be merged first so `.slurm`/`.job` are in `SCRIPT_SUFFIXES`. This detector uses its own `ARRAY_SCRIPT_SUFFIXES` and works independently, but coordinating is cleaner.

## Problem Statement

Job arrays are the standard HPC mechanism for robustness checks and sensitivity analyses. Two silent failure modes are invisible to every existing tool:

- Tasks overwriting each other because output paths don't include the task ID → job exits 0, scheduler says success, researcher sees one file.
- Index-to-parameter mapping is entirely implicit → if the corresponding config is lost or reordered, results become uninterpretable.

(see origin: docs/brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md)

## Proposed Solution

### 1. New detector function (`detectors.py`)

```python
# econharness/detectors.py

ARRAY_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}

# Detects $SLURM_ARRAY_TASK_ID or ${SLURM_ARRAY_TASK_ID} anywhere in a string
_TASK_ID_PATTERN = re.compile(r"\$\{?SLURM_ARRAY_TASK_ID\}?")

# Output-writing operation patterns: shell redirections and common HPC output flags
_OUTPUT_REDIRECT_PATTERN = re.compile(
    r"(?:>>?)\s*([^\s|&;]+)"            # > path or >> path
    r"|(?:-o|--output(?:=|\s+))([^\s|&;]+)"  # -o path or --output=path
    r"|(?:-e|--error(?:=|\s+))([^\s|&;]+)",  # -e path or --error=path
    re.MULTILINE,
)

def detect_job_array_expansion(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in ARRAY_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        # Must have both #SBATCH and $SLURM_ARRAY_TASK_ID
        if not re.search(r"^#SBATCH\b", text, re.MULTILINE):
            continue
        if not _TASK_ID_PATTERN.search(text):
            continue
        rel = path.relative_to(project_root).as_posix()

        # --- Collision check (R2, R3, R5) ---
        lines = text.splitlines()
        for match in _OUTPUT_REDIRECT_PATTERN.finditer(text):
            # Capture group index: 1 for >, 2 for -o/--output, 3 for -e/--error
            output_path_str = match.group(1) or match.group(2) or match.group(3) or ""
            if not output_path_str:
                continue
            # Skip #SBATCH -o lines — those use Slurm's own %a/%A substitution, not shell vars
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_text = text[line_start:text.find("\n", match.start())]
            if line_text.lstrip().startswith("#SBATCH"):
                continue
            # If the path string contains $SLURM_ARRAY_TASK_ID, it's disambiguated
            if _TASK_ID_PATTERN.search(output_path_str):
                continue
            findings.append(
                make_finding(
                    dimension="path_portability",
                    severity="medium",
                    title="Job array script may write to same output path from all tasks",
                    detail=f"{rel} uses `$SLURM_ARRAY_TASK_ID` but writes to `{output_path_str}` without including the task ID in the path. All tasks will overwrite each other's output.",
                    remediation="Include `$SLURM_ARRAY_TASK_ID` in the output filename: e.g. `results_${SLURM_ARRAY_TASK_ID}.csv`.",
                    score_impact=10,
                    path=rel,
                )
            )
            break  # One collision finding per file is enough

        # --- Undocumented mapping check (R4) ---
        task_id_lines = [
            i for i, line in enumerate(lines)
            if _TASK_ID_PATTERN.search(line)
        ]
        has_nearby_comment = False
        for lineno in task_id_lines:
            window_start = max(0, lineno - 5)
            window_end = min(len(lines), lineno + 6)
            for nearby_line in lines[window_start:window_end]:
                stripped = nearby_line.strip()
                # A non-SBATCH comment near the task ID counts as documentation
                if stripped.startswith("#") and not stripped.startswith("#SBATCH"):
                    has_nearby_comment = True
                    break
            if has_nearby_comment:
                break
        if not has_nearby_comment:
            findings.append(
                make_finding(
                    dimension="path_portability",
                    severity="low",
                    title="Job array index-to-parameter mapping is undocumented",
                    detail=f"{rel} uses `$SLURM_ARRAY_TASK_ID` with no nearby comment explaining what each index value represents.",
                    remediation="Add a comment near the `$SLURM_ARRAY_TASK_ID` usage explaining the mapping, e.g.: `# Index N corresponds to country N in params/countries.csv`.",
                    score_impact=3,
                    path=rel,
                )
            )
    return findings
```

### 2. Register in `scanner.py`

```python
# scanner.py imports — add
from econharness.detectors import (
    ...
    detect_job_array_expansion,
    ...
)

# scanner.py scan_project body — add after detect_hpc_batch_script_health (plan 008)
findings.extend(detect_job_array_expansion(project_root, files))
```

### 3. New test file `tests/test_job_array_expansion.py`

Follow the `tempfile.TemporaryDirectory` pattern:

Test cases:
- `.slurm` file with `#SBATCH`, `$SLURM_ARRAY_TASK_ID`, and `> results/output.csv` (fixed path) → medium collision finding
- `.slurm` file with `> results/output_${SLURM_ARRAY_TASK_ID}.csv` → no collision finding
- `.slurm` file with `$SLURM_ARRAY_TASK_ID` and a `#SBATCH -o slurm-%a.out` line → no collision finding (SBATCH `-o` line skipped)
- `.slurm` file with no comment near `$SLURM_ARRAY_TASK_ID` usage → low advisory finding
- `.slurm` file with `# index N = country N` within 5 lines of `$SLURM_ARRAY_TASK_ID` → no advisory finding
- `.sh` file with no `#SBATCH` → 0 findings
- `.slurm` file with `#SBATCH` but no `$SLURM_ARRAY_TASK_ID` → 0 findings (not a job array)

## Technical Considerations

- **`#SBATCH -o`/`-e` lines**: Slurm's own output directives use `%a` (task ID) and `%j` (job ID) rather than shell variable syntax. A `#SBATCH -o results_%a.out` line is already correct and must not trigger a collision finding. The implementation above skips lines starting with `#SBATCH`.
- **Variable-tracing out of scope**: If `OUT="results_${SLURM_ARRAY_TASK_ID}.csv"` is set at the top and used as `> $OUT` later, the indirect disambiguation is not detected. This is documented as a known limitation in the requirements doc. The implementer must not attempt to resolve it — it would require partial shell interpretation.
- **"Break after first collision"**: The plan includes `break` after the first collision finding per file to avoid flooding output for heavily-redirecting scripts. A single finding per file is sufficient to communicate the problem.
- **Proximity window (5 lines)**: The requirements doc specified 5 lines as the proximity heuristic for the documentation check. The implementer should validate this against real apli batch scripts before finalizing.
- **Dimension assignment**: Uses `path_portability` pragmatically (no dedicated HPC dimension today). Same caveat as plan 008 — migrate to `hpc_discipline` in a future pass if that dimension is added.
- **Score impacts**: Collision is 10 points (between medium absolute path at 7 and high at 12). Undocumented mapping is 3 points (low advisory).

## Acceptance Criteria

- [ ] `.slurm` with `#SBATCH`, `$SLURM_ARRAY_TASK_ID`, and `> results/output.csv` → medium finding "Job array script may write to same output path from all tasks"
- [ ] `.slurm` with `> results/output_${SLURM_ARRAY_TASK_ID}.csv` → no collision finding
- [ ] `#SBATCH -o slurm-%a.out` line does NOT trigger collision finding
- [ ] `.slurm` with no comment near `$SLURM_ARRAY_TASK_ID` → low advisory finding
- [ ] Comment `# index N = country` within 5 lines → no advisory finding
- [ ] `.sh` with no `#SBATCH` → 0 findings
- [ ] `.slurm` with `#SBATCH` but no `$SLURM_ARRAY_TASK_ID` → 0 findings
- [ ] All test cases in `tests/test_job_array_expansion.py` pass
- [ ] Finding appears in `econharness scan` output on a non-compliant project

## Dependencies & Risks

- **Plan 007 preferred prerequisite**: Same rationale as plans 008 and 009. Works independently via `ARRAY_SCRIPT_SUFFIXES`.
- **Regex for output redirections**: The `_OUTPUT_REDIRECT_PATTERN` handles common cases but may have edge cases with complex shell quoting or piping. Validate against `apli/analysis/code/cluster_models/` before finalizing.
- **False positives on collision check**: A script that does disambiguate via an intermediate variable (`OUT="$SLURM_ARRAY_TASK_ID.csv"; echo "hi" > $OUT`) will be falsely flagged. This is a documented limitation. The finding message should be worded carefully — "may write to same output path" (not "does write") — to acknowledge uncertainty.

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md](../brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md) — key decisions: array-range matching dropped; direct-path collision only; 5-line proximity window; medium for collision, low for documentation
- Detector structure reference: `econharness/detectors.py:705` (`detect_path_portability`)
- `make_finding`: `econharness/detectors.py:107`
- Scanner: `econharness/scanner.py:34`
- Test pattern: `tests/test_version_control.py`
