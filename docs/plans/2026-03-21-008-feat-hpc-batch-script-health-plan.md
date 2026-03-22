---
title: "feat: HPC Batch Script Health — detect missing set -e in #SBATCH scripts"
type: feat
status: active
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-hpc-batch-script-health-requirements.md
---

# feat: HPC Batch Script Health

## Overview

Add a new detector `detect_hpc_batch_script_health` that scans Slurm batch scripts (`.sh`, `.slurm`, `.job` files with at least one `#SBATCH` directive) for missing `set -e`. Without `set -e`, a failed step is silently swallowed — the job continues, exits 0, the scheduler marks it complete, and partial outputs are treated as valid results.

Scope is intentionally tight: `set -e` only. `set -u`, partition portability, and login-node anti-patterns are explicitly out of scope (see origin document).

**Prerequisite:** Plan 007 must be merged first so `.slurm` and `.job` are in `SCRIPT_SUFFIXES`. (If implementing independently, add them here instead.)

## Problem Statement

Batch scripts are first-class pipeline artifacts in HPC economics research. `set -e` absence is the #1 reason HPC jobs produce partial outputs that appear valid — the job exits 0, the scheduler marks it complete, and no one knows step 3 was skipped. econharness currently has zero checks on batch script fault-tolerance.

(see origin: docs/brainstorms/2026-03-21-hpc-batch-script-health-requirements.md)

## Proposed Solution

### 1. New detector function (`detectors.py`)

Add `detect_hpc_batch_script_health` after `detect_path_portability`:

```python
# econharness/detectors.py

_SBATCH_PATTERN = re.compile(r"^#SBATCH\b", re.MULTILINE)
_SET_E_PATTERN = re.compile(r"(?m)^\s*set\s+-[a-zA-Z]*e[a-zA-Z]*\b|set\s+-o\s+errexit")
_SHEBANG_DASH_E = re.compile(r"^#!.*\bbash\b.*\s-[a-zA-Z]*e\b")

BATCH_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}

def detect_hpc_batch_script_health(project_root: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix not in BATCH_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        if not _SBATCH_PATTERN.search(text):
            continue
        # Check shebang line for -e flag (e.g. #!/bin/bash -e)
        first_line = text.split("\n", 1)[0]
        if _SHEBANG_DASH_E.match(first_line):
            continue
        # Check body for set -e or set -o errexit
        if _SET_E_PATTERN.search(text):
            continue
        rel = path.relative_to(project_root).as_posix()
        findings.append(
            make_finding(
                dimension="path_portability",  # NOTE: see Technical Considerations
                severity="medium",
                title="Batch script missing `set -e`",
                detail=f"{rel} is a Slurm batch script without `set -e`. A failed command will be silently swallowed and the job will continue.",
                remediation="Add `set -e` near the top of the script so that any failed command causes the job to exit immediately with a non-zero code.",
                score_impact=7,
                path=rel,
            )
        )
    return findings
```

### 2. Register in `scanner.py`

Import the new function and add it to the `scan_project` call chain:

```python
# scanner.py imports
from econharness.detectors import (
    ...
    detect_hpc_batch_script_health,
    ...
)

# scanner.py scan_project body — add after detect_path_portability
findings.extend(detect_hpc_batch_script_health(project_root, files))
```

### 3. New test file `tests/test_hpc_batch_script_health.py`

Follow the pattern of `tests/test_version_control.py` (uses `tempfile.TemporaryDirectory`, creates files, calls detector directly):

Test cases:
- `.slurm` file with `#SBATCH` and no `set -e` → 1 medium finding
- `.slurm` file with `#SBATCH` and `set -e` in body → 0 findings
- `.slurm` file with `#!/bin/bash -e` shebang → 0 findings
- `.sh` file with `#!/bin/bash -e` and `#SBATCH` → 0 findings
- `.sh` file with no `#SBATCH` → 0 findings (not a batch script)
- `.py` file with `set -e` content → 0 findings (wrong suffix)
- `.slurm` file with `set -o errexit` → 0 findings (equivalent to `set -e`)

## Technical Considerations

- **`set -e` variants**: The pattern must cover `set -e`, `set -xe`, `set -ex`, `set -eo pipefail`, and `set -o errexit`. The `_SET_E_PATTERN` above covers these. `set -u` alone does NOT satisfy the requirement and must not match.
- **Dimension assignment**: The `path_portability` dimension is used as a reasonable fit since no dedicated HPC dimension exists today. If a future plan adds an `hpc_discipline` dimension, this finding should be migrated. Document this in the finding title so it's easy to find.
- **Score impact**: 7 points (medium tier, same as machine-specific hint findings).
- **`BATCH_SCRIPT_SUFFIXES` vs `SCRIPT_SUFFIXES`**: This detector uses a narrower set (`{".sh", ".slurm", ".job"}`) because `#SBATCH` cannot appear in `.py`, `.R`, or `.md` files in a meaningful way. If `.slurm`/`.job` were not already in `SCRIPT_SUFFIXES` (from plan 007), this detector still works independently — it uses its own `BATCH_SCRIPT_SUFFIXES` constant and doesn't rely on `SCRIPT_SUFFIXES`.

## Acceptance Criteria

- [ ] A `.slurm` file with `#SBATCH` directives and no `set -e` anywhere produces exactly one medium finding with title "Batch script missing `set -e`"
- [ ] A `.slurm` file with `set -e` anywhere in the body (even after the `#SBATCH` block) produces no finding
- [ ] A `.sh` file with `#!/bin/bash -e` produces no finding
- [ ] A `.sh` file without any `#SBATCH` directive produces no finding
- [ ] A `.slurm` file with `set -o errexit` produces no finding
- [ ] A `.slurm` file with `set -xe` (combining flags) produces no finding
- [ ] The finding appears in the output of `econharness scan` on a project containing a non-compliant batch script
- [ ] `tests/test_hpc_batch_script_health.py` covers all 7 test cases above and passes

## Dependencies & Risks

- **Plan 007 preferred prerequisite**: Adds `.slurm`/`.job` to `SCRIPT_SUFFIXES`. This detector works independently via `BATCH_SCRIPT_SUFFIXES`, but coordinating with plan 007 avoids duplicate suffix additions.
- **Dimension assignment**: Using `path_portability` is a pragmatic choice. If this creates scoring confusion, consider adding a `hpc_discipline` dimension in a future refactor.
- **`set -e` semantics**: `set -e` can be negated by `set +e` later. This detector checks presence/absence only — it does not track `set +e` undoing the flag. Documented limitation.

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-hpc-batch-script-health-requirements.md](../brainstorms/2026-03-21-hpc-batch-script-health-requirements.md) — key decisions: `set -e` only; `#!/bin/bash -e` counts; medium severity; anywhere in file counts
- Detector pattern reference: `econharness/detectors.py:705` (`detect_path_portability` for structure)
- `make_finding` helper: `econharness/detectors.py:107`
- Scanner registration: `econharness/scanner.py:34`
- Test pattern reference: `tests/test_version_control.py`
