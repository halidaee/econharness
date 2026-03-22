---
date: 2026-03-22
topic: fix-collision-false-positives-and-env-conflation
focus: Fix (1) job array collision false positives and (4) cluster vs local reproducibility conflation
---

# Ideation: Fix Collision False Positives and Env Conflation

## Problem Context

Two concrete bugs surfaced from running econharness on the `apli` project:

**Problem (1) — collision false positives**
`detect_job_array_expansion` flags two well-written scripts because disambiguation happens via intermediate variables rather than a literal `$SLURM_ARRAY_TASK_ID` in the redirect path:
- `cluster_shap/submit.sh`: sets `OUT_DIR` env var, passes it to R worker — R script does the actual writing
- `nested_cv/run_true_nested_cv_array.sh`: maps `TASK_ID → SCOPE → A2_OUTPUT_DIR`, writes to `$A2_OUTPUT_DIR/`

The detector's check: `if _TASK_ID_PATTERN.search(output_path_str)` — only matches direct expressions, not variable derivations.

**Problem (4) — cluster vs local reproducibility conflation**
`detect_environment_reproducibility` uses a "downgrade medium → low" hack when version-pinned module loads are present without a lockfile. This treats cluster-level env pinning as a *substitute* for local lockfile reproducibility, when they're actually *complements*. The scoring conflation means the `environment_reproducibility` dimension conflates two distinct questions:
- Local reproducibility: does the project have `renv.lock`/`pixi.lock`?
- Cluster reproducibility: are module loads version-pinned and consistent?

## Codebase Grounding

- `detect_job_array_expansion` (detectors.py:942): collision check at line 957–988; regex at line 933–937
- `detect_environment_reproducibility` (detectors.py:689): downgrade logic at 699–731; module load findings at 767–803
- `DIMENSION_WEIGHTS` (scoring.py:9–20): `environment_reproducibility` is 10.0 weight; no `cluster_environment` dimension exists
- All module load findings currently emit `dimension="environment_reproducibility"`
- The downgrade is a conditional: if pinned R module loads exist, emit `severity="low"` instead of `severity="medium"` for the missing lockfile finding

---

## Ranked Ideas

### 1. Suppress Collision Finding When Any Shell Variable Is in the Redirect Path (Problem 1)
**Description:** Change the collision check to skip the finding when `output_path_str` contains any `$` character. The rationale: a path like `> $OUT_DIR/results.csv` or `> ${A2_OUTPUT_DIR}/output.csv` was explicitly parameterized by the author. Only literal paths (e.g., `> results/output.csv`) are unambiguously suspicious. One regex change or one `in "$"` guard.
**Rationale:** Directly addresses both apli false positives. The detector already can't trace variable assignments, so the right posture is: "if the user parameterized the path at all, trust it." True positives (literal paths) are fully preserved. One-line fix.
**Downsides:** Introduces false negatives for a path like `> ${FIXED_PREFIX}_results.csv` where `FIXED_PREFIX` is a constant. Rare in practice; the benefit of eliminating trust-destroying false positives outweighs this.
**Confidence:** 95%
**Complexity:** Low — one-line guard in the collision check loop
**Status:** Unexplored

### 2. Inline Suppression Directive (Problem 1, complement)
**Description:** Support `# econharness: skip-collision-check` or `# econharness: disable=collision` on the same line as or the line before the redirect. Provides an escape hatch for scripts that need variable-path suppression in perpetuity without a code change.
**Rationale:** Some scripts will always have indirect disambiguation that we can't detect. An inline directive lets the author signal intent without modifying detector logic. Low implementation cost.
**Downsides:** Adds a new suppression mechanism to the public API. Must be documented. Risk of overuse ("just suppress everything").
**Confidence:** 75%
**Complexity:** Low
**Status:** Unexplored

### 3. New `cluster_environment` Dimension (Problem 4)
**Description:** Add `cluster_environment` to `DIMENSION_WEIGHTS` (weight ~5.0–7.0). Move all module load findings (`unpinned`, `inconsistent`, `pinned-but-no-lockfile`) to `dimension="cluster_environment"`. Remove the downgrade logic from `detect_environment_reproducibility` entirely — the lockfile check becomes unconditional. The "pinned via module load but no renv.lock" finding moves from being a modified lockfile finding to being a standalone cluster-env advisory under the new dimension.
**Rationale:** Architecturally correct. Two distinct questions → two distinct dimensions → two distinct scores. Eliminates the downgrade hack. A project using module loads correctly scores 100 on `cluster_environment`; its `environment_reproducibility` reflects local lockfile status only. Scores become interpretable.
**Downsides:** Changes the scoring model — existing users will see score changes (existing "penalized for good HPC hygiene" behavior is fixed, but overall score distribution shifts). Requires updating `scoring.py` and any score-related tests.
**Confidence:** 90%
**Complexity:** Medium — mostly mechanical: new dimension key, updated dimension string on findings, remove downgrade, update tests
**Status:** Unexplored

### 4. `environment.mode: cluster_only` Config Opt-Out (Problem 4, complement)
**Description:** Allow `.econharness.yml` to declare `environment.mode: cluster_only`. When set, local lockfile findings (missing renv.lock, missing pixi.lock) are suppressed entirely — the project is HPC-first and local development reproducibility is not applicable. Module load findings still fire.
**Rationale:** Some research groups work exclusively on the cluster with no local R/Python development. For them, the lockfile findings are pure noise. A single config line provides a clean opt-out without distorting the dimension scores for everyone else.
**Downsides:** Requires `.econharness.yml` edit. Risk that it's used to suppress legitimate concerns. Should emit an informational note that local lockfile check is disabled.
**Confidence:** 70%
**Complexity:** Low — config read + conditional suppression
**Status:** Unexplored

---

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Two-hop variable assignment trace | Variable assignment in bash can span multiple lines, use arrays, use arithmetic — static tracing would be fragile and complex for minimal gain over the any-variable suppression |
| 2 | Downgrade collision to low severity | Treats the symptom (false positives hurt), not the root cause (wrong detection criterion); also makes true positives less visible |
| 3 | Keep downgrade but document it | The conflation is a correctness problem, not a documentation problem |

---

## Recommended Sequence

1. **Fix (1) first**: Idea 1 is a one-liner, zero risk, immediate trust improvement. Idea 2 is a useful follow-on.
2. **Fix (4) with Idea 3**: The new dimension is the right architectural fix. Idea 4 is optional — add if needed after testing against apli.

## Session Log
- 2026-03-22: Focused ideation on two specific bugs from apli sanity test — 4 candidates generated, 0 rejected (all are actionable and non-overlapping), sequence recommended
