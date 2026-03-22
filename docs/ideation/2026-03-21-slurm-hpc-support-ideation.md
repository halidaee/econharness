---
date: 2026-03-21
topic: slurm-hpc-support
focus: Slurm/HPC cluster support — econharness runs locally and lints project code that will run on a Slurm cluster
---

# Ideation: Slurm/HPC Cluster Support (Static Linting Only)

## Scope Constraint

**econharness always runs locally.** It never executes on or communicates with the cluster. All ideas must be pure static analysis of project files — detecting HPC reproducibility problems in code before it is submitted to a scheduler.

## Codebase Context

- **Project shape**: Pure Python 3.11+ CLI, zero runtime dependencies, detector-based scoring across 10 reproducibility dimensions
- **Key files**: `econharness/detectors.py` (15+ detectors), `econharness/config.py` (`.econharness.yml` schema)
- **Relevant false positive**: `ABSOLUTE_PATH_PATTERNS` flags `/scratch/` and `/home/` — a well-written HPC script uses `$SCRATCH/` (portable) rather than `/scratch/username/` (hardcoded), but the current detector cannot tell the difference and flags both
- **Relevant false negative**: `environment_reproducibility` only recognizes `pixi.lock`/`renv.lock` — a project using `module load R/4.3.1` in all its submission scripts satisfies reproducibility requirements but is penalized today
- **Real project evidence**: `apli` project has `analysis/code/cluster_models/` indicating active cluster use; scored 88.3 with path_portability finding on `repo_dag_report.md`

## Ranked Ideas

### 1. Path Intelligence Overhaul
**Description:** Replace the current blanket absolute-path detector with a tier-aware model. `$SCRATCH/`, `$SLURM_TMPDIR`, `${PROJECT}/` are HPC-portable patterns and should pass. `/scratch/username/` is non-portable and should fail. A configurable allowlist in `.econharness.yml` handles cluster-canonical mounts (e.g., `/scratch/`, `/project/`, `/apps/`).
**Rationale:** The current detector flags every well-written HPC script as violating reproducibility norms. It actively miseducates researchers and destroys trust on first contact. Must be fixed before anything else — it is the most immediate correctness failure.
**Downsides:** Shell variable expansion parsing is non-trivial (`${SCRATCH:-/tmp}/` is portable; `$(echo /scratch/jsmith)` is not). Requires judgment calls about what constitutes a "portable" env-var usage.
**Confidence:** 95%
**Complexity:** Medium
**Status:** Explored — 2026-03-21
**Requirements doc:** docs/brainstorms/2026-03-21-hpc-path-portability-requirements.md

### 2. Module Load as Environment Reproducibility Evidence
**Description:** Recognize version-pinned `module load R/4.3.1`, `module load gcc/12.2` as satisfying `environment_reproducibility` — currently the tool penalizes projects that correctly use the cluster module system for lacking `pixi.lock`/`renv.lock`. Additionally scan all submission scripts for module version inconsistencies across scripts (different versions of the same module loaded in different files) and flag those as genuine reproducibility violations.
**Rationale:** False negative that penalizes correct HPC practice on first contact. The positive addition — detecting version drift across scripts — catches a real, common, silent reproducibility failure that no existing tool addresses.
**Downsides:** Need to define "version-pinned enough" — some clusters use short module names with no version (`module load R`), which should be flagged but differently from pixi/renv absence.
**Confidence:** 88%
**Complexity:** Medium
**Status:** Explored — 2026-03-21
**Requirements doc:** docs/brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md

### 3. HPC Batch Script Health Detector
**Description:** New detector scanning `.sh`, `.slurm`, `.job` files containing `#SBATCH` headers for: missing `set -e` and `set -u` (silent failure swallowing), hardcoded cluster-specific partition names that won't transfer (`--partition=owners`, `--partition=gpu_v100`), non-parametrized resource requests, and README/documentation that instructs users to run compute-heavy steps directly on the login node without a submission wrapper.
**Rationale:** Batch scripts are first-class pipeline artifacts. `set -e` absence is the #1 reason HPC jobs produce partial outputs that appear valid — the job exits 0, the scheduler marks it complete, and no one knows step 3 was skipped. Completely invisible to econharness today.
**Downsides:** Static shell script analysis is imperfect — `set -e` can be set inline or inherited. Partition portability is context-dependent (single-cluster projects may legitimately hardcode). Risk of false positives.
**Confidence:** 82%
**Complexity:** Medium
**Status:** Explored — 2026-03-21
**Requirements doc:** docs/brainstorms/2026-03-21-hpc-batch-script-health-requirements.md
**Scope after brainstorm:** Narrowed to `set -e` check only. Partition names dropped (unavoidable), login node check dropped (unreliable), `set -u` dropped (too noisy).

### 4. Job Array Expansion Auditor
**Description:** Detect scripts using `$SLURM_ARRAY_TASK_ID` and statically check: (a) whether the `--array=0-N` index range matches the actual number of parameter combinations in the referenced config/input file; (b) whether multiple scripts write to the same output path without array-index disambiguation (collision risk); (c) whether the task-ID-to-parameter mapping is documented or entirely implicit.
**Rationale:** Job arrays are the standard HPC mechanism for robustness checks and sensitivity analyses — the most scientifically important part of many economics papers. Partial runs and output collisions are silent and impossible to reconstruct. A failure mode that scales catastrophically with team size and is invisible to every existing tool.
**Downsides:** High complexity. Statically inferring array index space from a config file requires understanding the config format. Collision detection may produce false positives if disambiguation logic is non-trivial. Scope to collision check initially.
**Confidence:** 75%
**Complexity:** High
**Status:** Explored — 2026-03-21
**Requirements doc:** docs/brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md
**Scope after brainstorm:** Array range vs config size matching dropped (requires format-specific parsing). Retained: direct output path collision check (medium severity) + undocumented index mapping advisory (low severity). Variable-tracing for indirect disambiguation explicitly out of scope.

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | `srun`/`mpirun` wrapper transparency | Too narrow; pipeline commands are user-configured, not introspected during scan |
| 2 | Auto-generate sbatch boilerplate | Too prescriptive; cluster requirements vary too much |
| 3 | DAG-aware stage submission | Reimplements Snakemake/Nextflow; out of scope for a linting tool |
| 4 | Walltime estimator from sacct history | High complexity for uncertain value; sacct history sparse on new projects |
| 5 | Multi-root project manifests | Breaks core single-root model; over-engineered for actual problem |
| 6 | Detached check execution (econharness as batch job) | Rare problem; login node NFS visibility is the common case |
| 7 | Slurm epilog/prolog hook mode | Requires cluster admin; existing `--json` sufficient for CI integration |
| 8 | Wall-time truncation heuristics | Fragile output file heuristics; sacct-based approach more reliable |
| 9 | Sequential loop → job array lint | Imprecise without understanding script semantics; low signal-to-noise |
| 10 | Hardcoded job ID paths | Subsumed by path intelligence overhaul (#1) |
| 11 | Shared project output collision detector | Real but narrow; lower probability than other issues |
| 12 | Async verify (submit + poll + resume) | econharness is local-only; it never communicates with the cluster scheduler |
| 13 | Filesystem-aware state management (NFS/scratch) | econharness always runs locally; .econharness/ is always a local writable dir |
| 14 | Slurm job environment fingerprint | Requires running on the cluster; out of scope for a local linter |
| 15 | Pipeline topology as reproducibility unit | Abstract; concrete job array auditor (#4) is better |

## Session Log
- 2026-03-21: Initial ideation — 40 candidates generated across 5 frames + 3 cross-cutting syntheses, 6 survivors
- 2026-03-21: Revised after user clarification — econharness is local-only, never runs on cluster. Dropped async verify and filesystem state management (both require cluster execution). 4 survivors remain, all pure static analysis.
- 2026-03-21: Brainstormed idea #1 (Path Intelligence Overhaul) → requirements doc written at docs/brainstorms/2026-03-21-hpc-path-portability-requirements.md
- 2026-03-21: Brainstormed idea #2 (Module Load as Env Reproducibility) → requirements doc written at docs/brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md
- 2026-03-21: Brainstormed idea #3 (HPC Batch Script Health) → narrowed to set -e only; requirements doc at docs/brainstorms/2026-03-21-hpc-batch-script-health-requirements.md
- 2026-03-21: Brainstormed idea #4 (Job Array Expansion Auditor) → dropped array range vs config size matching; retained collision check (medium) + undocumented mapping advisory (low); variable-tracing out of scope; requirements doc at docs/brainstorms/2026-03-21-job-array-expansion-auditor-requirements.md
