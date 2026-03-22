---
date: 2026-03-21
topic: job-array-expansion-auditor
---

# Job Array Expansion Auditor

## Problem Frame

Job arrays (`#SBATCH --array=0-N`) are the standard HPC mechanism for running robustness checks and sensitivity analyses — the most scientifically important part of many economics papers. Two silent failure modes are common and invisible to every existing tool:

1. **Output path collisions**: Multiple tasks write to the same file path (no array-index in the filename), causing tasks to overwrite each other's results. The job exits 0; the scheduler reports success; the researcher sees one output file and never knows that 99 tasks overwrote each other.

2. **Implicit index-to-parameter mapping**: The script uses `$SLURM_ARRAY_TASK_ID` as an index but nowhere documents what each index value represents (e.g., which country, specification, or dataset). If the corresponding parameter file or config is lost or reordered, results become uninterpretable.

econharness is a local static linter. All detection is pure static analysis of project files.

## Requirements

- R1. The detector identifies **job array scripts**: files with `.sh`, `.slurm`, or `.job` extensions that contain both at least one `#SBATCH` directive and at least one reference to `$SLURM_ARRAY_TASK_ID` or `${SLURM_ARRAY_TASK_ID}`.
- R2. For each job array script, the detector scans for **output-writing operations**: shell output redirections (`>` and `>>`) and common HPC output flags (`-o <path>`, `--output=<path>`, `-e <path>`, `--error=<path>`).
- R3. If an output path from R2 is a bare string literal (no variable interpolation at all) or is an interpolated string that does **not** include `$SLURM_ARRAY_TASK_ID` or `${SLURM_ARRAY_TASK_ID}` directly in the same expression, raise a **medium-severity** collision-risk finding: "Job array script may write to the same output path from all tasks — include `$SLURM_ARRAY_TASK_ID` in the output filename to prevent tasks from overwriting each other."
- R4. If a job array script has no comment (lines beginning with `#` that are not `#SBATCH` directives) near any `$SLURM_ARRAY_TASK_ID` usage that explains what the index values correspond to — and no reference to a config/params file in those comments — raise a **low-severity** advisory finding: "Job array index-to-parameter mapping is undocumented. Add a comment or README entry explaining what each array index value represents."
- R5. When `$SLURM_ARRAY_TASK_ID` or `${SLURM_ARRAY_TASK_ID}` appears directly in the same output path expression, no collision finding is raised for that path.

## Success Criteria

- A `.slurm` file with `#SBATCH --array=0-9` and `> results/output.csv` (fixed path, no task ID) produces a medium collision finding.
- A `.slurm` file with `> results/output_${SLURM_ARRAY_TASK_ID}.csv` produces no collision finding.
- A `.slurm` file using `$SLURM_ARRAY_TASK_ID` with no comment explaining the index mapping produces a low advisory finding.
- A `.slurm` file with `# index corresponds to country in params.csv` near the `$SLURM_ARRAY_TASK_ID` usage produces no advisory finding.
- A `.sh` file with no `#SBATCH` directive is not checked.
- A `.slurm` file with `#SBATCH` but no `$SLURM_ARRAY_TASK_ID` usage is not checked (not a job array script).

## Scope Boundaries

- **No array range vs config size matching**: Statically inferring whether `--array=0-N` matches the actual number of parameter combinations in a config file requires parsing arbitrary formats (CSV, JSON, R vectors, etc.) — out of scope.
- **No variable tracing**: If `OUT="results_${SLURM_ARRAY_TASK_ID}.csv"` is set at the top and used as `> $OUT` later, the indirect disambiguation is not detected. Only direct path expressions are checked. This is a documented limitation, not a bug.
- **No check that `$SLURM_ARRAY_TASK_ID` is actually used in meaningful computation** — only its presence in output paths and documentation context is checked.
- **`$SLURM_ARRAY_JOB_ID` is not a substitute for `$SLURM_ARRAY_TASK_ID`** in output paths — the job ID is shared across all tasks and does not disambiguate outputs.

## Key Decisions

- **Medium severity for collision, low for documentation**: Collision is a correctness failure (results silently overwritten); documentation absence is advisory (research is still reproducible, just harder to interpret). The asymmetry in severity reflects this.
- **"Near the usage" is the proximity heuristic for R4**: A comment within 5 lines of any `$SLURM_ARRAY_TASK_ID` reference (above or below) counts as documentation. Distant README-only documentation is out of scope — the comment must be co-located with the code.
- **Non-SBATCH `.sh` files ignored**: The `#SBATCH` trigger (from R1) is the gate. Plain shell scripts that aren't batch submissions are not affected.
- **`$SLURM_ARRAY_JOB_ID` in output flags counted as ambiguous**: Unlike `$SLURM_ARRAY_TASK_ID`, the job ID is shared across the whole array and does not prevent collisions. Do not treat it as disambiguating.

## Dependencies / Assumptions

- Depends on `.slurm`/`.job` being added to `SCRIPT_SUFFIXES` (also required by HPC path portability and batch script health features). If those ship first, scan scope is already in place.
- The R4 proximity heuristic (5-line window) is intentionally simple. A deferred planning question should validate this against real apli cluster scripts.

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] What is the complete regex set for capturing output paths from shell redirections and common HPC output flags (`-o`, `--output`, `-e`, `--error`) reliably across R, Python, and shell invocations? Validate against apli's `analysis/code/cluster_models/` scripts.
- [Affects R4][Technical] Is 5 lines the right proximity window for "near the usage"? Read actual apli batch scripts to see how comments are typically placed relative to `$SLURM_ARRAY_TASK_ID` usage.
- [Affects R3][Design] Should the finding report the specific output path(s) that lack task-ID disambiguation, or only flag the file? Naming paths is more actionable but may be verbose if a script has many redirections.

## Next Steps

→ `/ce:plan` for structured implementation planning
