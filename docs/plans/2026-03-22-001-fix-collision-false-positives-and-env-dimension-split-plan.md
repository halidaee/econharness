---
title: "fix: Reduce collision false positives and split cluster env reproducibility into own dimension"
type: fix
status: completed
date: 2026-03-22
origin: docs/ideation/2026-03-22-fix-collision-false-positives-and-env-conflation-ideation.md
---

# fix: Reduce Collision False Positives and Split Cluster Env Reproducibility

## Overview

Two concrete bugs surfaced from running econharness against the `apli` project:

1. **Collision false positives**: `detect_job_array_expansion` flags well-written scripts that disambiguate output paths via intermediate shell variables rather than a literal `$SLURM_ARRAY_TASK_ID` in the redirect path.
2. **Env dimension conflation**: Module load findings (cluster reproducibility) and lockfile findings (local reproducibility) both score against `environment_reproducibility`, using a "downgrade medium → low" hack that treats them as substitutes when they are complements.

## Problem Statement

### Problem 1 — Collision false positives

The collision check at `detectors.py:957` uses `_TASK_ID_PATTERN.search(output_path_str)` to determine whether a redirect path is disambiguated. This only matches direct expressions. Two apli scripts are correctly written but get flagged:

- `cluster_shap/submit.sh`: sets `OUT_DIR` from `$SLURM_ARRAY_TASK_ID`, passes it as env var to R worker which does the actual file writing — no shell redirect in the bash file at all, OR redirect to `$OUT_DIR/...` where `OUT_DIR` encodes the task ID.
- `nested_cv/run_true_nested_cv_array.sh`: `SLURM_ARRAY_TASK_ID → SCOPE → A2_OUTPUT_DIR=".../${SCOPE}"` then writes to `$A2_OUTPUT_DIR/` — full disambiguation via intermediate variable.

In both cases the output path expression is a `$VAR` reference, not a literal path. The detector cannot trace variable assignments (out of scope per the original requirements doc), so the correct posture is: **if the path contains any shell variable, the author intentionally parameterized it — skip the collision finding**.

### Problem 4 — Cluster vs local env conflation

`detect_environment_reproducibility` uses conditional branching:
- If version-pinned module loads present → emit `severity="low"` for missing lockfile (downgraded)
- If no module loads → emit `severity="medium"` for missing lockfile (full penalty)

This is architecturally wrong: it treats cluster-level environment pinning as a substitute for local lockfiles. `module load R/4.3.1` and `renv.lock` answer different questions:
- **`renv.lock`**: reproducible local development environment (package versions, CRAN snapshot)
- **`module load R/4.3.1`**: reproducible cluster execution environment (system R version, HPC module system)

Both the "downgrade" logic and the fact that all module load findings score against `environment_reproducibility` conflate these. The fix is to introduce a separate `cluster_environment` dimension.

## Proposed Solution

### Fix 1 — Any `$` in redirect path suppresses collision finding

In the collision check loop (`detectors.py:957–988`), add a guard: if `output_path_str` contains `$`, skip the collision finding.

```python
# econharness/detectors.py — inside the collision check loop
if not output_path_str:
    continue
# Skip #SBATCH directive lines ...
if line_text.lstrip().startswith("#SBATCH"):
    continue
# NEW: If the path contains any shell variable reference, the author
# intentionally parameterized it — we can't trace variable assignments,
# so trust the parameterization.
if "$" in output_path_str:
    continue
# If the path directly contains $SLURM_ARRAY_TASK_ID it's disambiguated
if _TASK_ID_PATTERN.search(output_path_str):
    continue
```

The existing `_TASK_ID_PATTERN` check becomes redundant (since task ID contains `$`) but can be kept for clarity/documentation.

**What still gets flagged**: literal paths with no `$` at all — e.g., `> results/output.csv`, `> /data/output.csv`. These are the true positives.

**Accepted false negative**: a path like `> ${FIXED_PREFIX}_results.csv` where `FIXED_PREFIX` is a constant string, not derived from task ID. Rare in practice.

### Fix 4 — New `cluster_environment` dimension

**Step 4a — `scoring.py`**: Add `cluster_environment` to `DIMENSION_WEIGHTS` with weight `6.0`. Adjust other weights minimally to maintain sum coherence (or leave sum as-is — weights are relative).

```python
# econharness/scoring.py
DIMENSION_WEIGHTS = {
    "automation_and_one_command_rebuild": 22.0,
    "manual_step_elimination": 14.0,
    "directory_and_stage_structure": 14.0,
    "relational_data_discipline": 18.0,
    "environment_reproducibility": 10.0,
    "cluster_environment": 6.0,          # NEW
    "path_portability": 8.0,
    "artifact_traceability": 8.0,
    "version_control_discipline": 5.0,
    "self_documenting_clarity": 3.0,
    "software_hygiene_and_redundancy": 8.0,
}
```

**Step 4b — `detectors.py`**: In `detect_environment_reproducibility`:
1. Remove all "downgrade" conditional logic (the `if r_pinned / else` and `if py_pinned / else` blocks)
2. Make lockfile findings unconditional — always `severity="medium"` when lockfile is absent
3. Change all module load findings (`unpinned`, `inconsistent`, `pinned-but-no-lockfile` advisory) to use `dimension="cluster_environment"`

The "pinned but no lockfile" advisory becomes:
```python
# When pinned module loads exist but no lockfile — advisory under cluster_environment
make_finding(
    dimension="cluster_environment",
    severity="low",
    title="R cluster environment pinned via module load — consider renv for local dev",
    ...
    score_impact=3,   # low impact; cluster env is correctly handled
)
```

The `unpinned` and `inconsistent` findings move to `cluster_environment` unchanged except for `dimension=`.

## Technical Considerations

- **Scoring model change**: Adding `cluster_environment` changes the weighted average denominator. Existing projects will see slight overall score adjustments. Projects currently benefiting from the "downgrade" will likely see `environment_reproducibility` worsen (correct: they don't have a lockfile) but gain a new `cluster_environment` score that reflects their actual cluster hygiene.
- **`apli` expected outcome**: Both collision false positives disappear. `environment_reproducibility` will show a medium finding for missing `renv.lock` (correct), and `cluster_environment` will be 100 (pinned R module loads, no unpinned, no inconsistency). Net score impact depends on weights chosen.
- **Backward compatibility**: No config schema changes. No CLI changes. Pure internal detector/scoring logic.

## Implementation Units

### Unit A — Fix collision false positive (Problem 1)
**Goal:** Suppress collision finding when redirect path contains a shell variable reference.

**Files:**
- `econharness/detectors.py` — add `if "$" in output_path_str: continue` guard in the collision loop (~line 966)
- `tests/test_job_array_expansion.py` — add tests

**Approach:**
1. Add the `$` guard immediately after the `#SBATCH` line skip
2. The existing `_TASK_ID_PATTERN` check can be retained as a fast-path comment/doc aid

**Test scenarios to add:**
- `test_variable_path_not_flagged`: redirect to `> $OUT_DIR/results.csv` — no collision finding
- `test_braced_variable_path_not_flagged`: redirect to `> ${OUT_DIR}/results.csv` — no collision finding
- `test_literal_path_without_variable_still_flagged`: redirect to `> results/output.csv` — collision finding fires (existing test `test_fixed_output_path_flagged` covers this but verify it still passes)
- `test_derived_variable_path_not_flagged`: script that sets `OUT_DIR` from task ID then redirects to `$OUT_DIR/file.csv`

**Verification:** `python -m pytest tests/test_job_array_expansion.py -v` — all pass, no regressions.

**Execution note:** Test-first. Write the failing tests for variable-path redirect first, then add the guard.

**Patterns to follow:** `tests/test_job_array_expansion.py` — `_make_project`, `_scan` helpers. `CollisionTests` class structure.

---

### Unit B — New `cluster_environment` dimension (Problem 4)
**Goal:** Separate cluster env reproducibility from local env reproducibility in scoring.

**Files:**
- `econharness/scoring.py` — add `cluster_environment: 6.0` to `DIMENSION_WEIGHTS`
- `econharness/detectors.py` — update `detect_environment_reproducibility`: remove downgrade logic, change module load findings to `dimension="cluster_environment"`, make lockfile findings unconditional
- `tests/test_module_load_env_reproducibility.py` — update tests for new behavior

**Approach:**
1. Add the new dimension key to `scoring.py` first
2. In `detect_environment_reproducibility`:
   - Collapse the R lockfile check from `if r_pinned / else` into a single unconditional block: always `severity="medium"`, `score_impact=12`, `dimension="environment_reproducibility"`
   - Same for Python lockfile check
   - Change `dimension="environment_reproducibility"` → `dimension="cluster_environment"` on: unpinned module findings, version inconsistency findings, and the "pinned but no lockfile" advisory
   - The "pinned but no lockfile" advisory: lower its `score_impact` to ~3 (informational) and update its title/detail to reflect it's a cluster-env advisory, not a local env concern

**Updated behavior table:**

| Project state | environment_reproducibility | cluster_environment |
|---|---|---|
| renv.lock present, pinned modules | 100 | 100 |
| renv.lock absent, pinned modules | 88 (medium finding, -12) | 97 (low advisory, -3) |
| renv.lock absent, unpinned modules | 88 | 92 (medium finding, -8) |
| renv.lock absent, no modules | 88 | 100 (no cluster env to check) |
| renv.lock absent, inconsistent versions | 88 | 88 (high finding, -12) |

**Test scenarios to update:**
- `test_r_files_no_renv_pinned_module_gives_low`: was checking low severity on `environment_reproducibility`; now should check that `environment_reproducibility` finding is medium AND a separate `cluster_environment` advisory (low) exists
- `test_r_files_no_renv_pinned_module_downgraded_not_medium`: rename/refactor — lockfile finding IS now medium; the module load advisory is a separate low finding in `cluster_environment`
- All `dimension` assertions in existing tests that check `environment_reproducibility` for module load findings need updating to `cluster_environment`
- Add: `test_module_finding_scores_cluster_dimension` — verify module load findings have `dimension == "cluster_environment"`
- Add: `test_lockfile_finding_always_medium_regardless_of_modules` — verify no downgrade

**Verification:** `python -m pytest tests/test_module_load_env_reproducibility.py -v` — all pass.

**Execution note:** Characterization-first for the test updates — document existing behavior before rewriting, then update tests to reflect new intended behavior, then change the implementation.

**Patterns to follow:** `tests/test_module_load_env_reproducibility.py` — `ModuleLoadRLockfileTests`, `_scan` helper. `econharness/scoring.py` — `DIMENSION_WEIGHTS` dict structure.

---

## Acceptance Criteria

- [ ] `detect_job_array_expansion`: redirect paths containing any `$` variable reference do not produce collision findings
- [ ] `detect_job_array_expansion`: literal output paths (no `$`) with no task ID still produce medium collision findings
- [ ] `detect_environment_reproducibility`: missing lockfile always produces medium finding in `environment_reproducibility`, regardless of module load presence
- [ ] `detect_environment_reproducibility`: all module load findings (`unpinned`, `inconsistent`, pinned advisory) use `dimension="cluster_environment"`
- [ ] `scoring.py`: `cluster_environment` dimension exists in `DIMENSION_WEIGHTS`
- [ ] All existing tests pass
- [ ] New tests cover the apli false positive patterns
- [ ] Running econharness on `apli` at `/Users/halidaee/apli` produces no collision false positives for `cluster_shap/submit.sh` and `nested_cv/run_true_nested_cv_array.sh`

## Scope Boundaries

- No `environment.mode: cluster_only` config opt-out (Idea 4 from ideation doc) — deferred; the dimension split makes it much less necessary
- No inline suppression directive (Idea 2 from ideation doc) — deferred; the `$` guard covers the real cases
- No variable assignment tracing — remains explicitly out of scope; the `$` guard is the right level of precision
- No weight rebalancing of other dimensions — add `cluster_environment: 6.0` without touching others

## Sources & References

- **Origin document:** [docs/ideation/2026-03-22-fix-collision-false-positives-and-env-conflation-ideation.md](docs/ideation/2026-03-22-fix-collision-false-positives-and-env-conflation-ideation.md) — Key decisions: (1) any-`$`-in-path suppresses collision; (4) new dimension rather than downgrade hack
- Collision check: `econharness/detectors.py:942–1030`
- Env reproducibility detector: `econharness/detectors.py:689–804`
- Scoring model: `econharness/scoring.py:9–20`
- Collision tests: `tests/test_job_array_expansion.py`
- Env repro tests: `tests/test_module_load_env_reproducibility.py`
