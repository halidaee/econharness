---
date: 2026-03-21
topic: module-load-env-reproducibility
---

# Module Load as Environment Reproducibility Evidence

## Problem Frame

The `environment_reproducibility` detector checks for `renv.lock` and `pixi.lock` only. HPC projects that correctly pin their environment via `module load R/4.3.1` in submission scripts are penalized for lacking a lockfile — even though they have done the right thing for their cluster context. renv cannot always be used on a cluster, but is still preferred for local development.

Additionally, version inconsistency across scripts (`module load R/4.2` in one script, `module load R/4.3.1` in another) is a genuine reproducibility failure that no detector currently catches — results depend on which script ran, silently.

econharness is a local static linter. All detection is pure static analysis of project files.

## Requirements

- R1. The detector scans submission scripts (`.sh`, `.slurm`, `.job`) for `module load <name>/<version>` statements (version-pinned) and `module load <name>` statements (unpinned, no version).
- R2. When R files are present, no `renv.lock` exists, but **version-pinned** R module loads are found across submission scripts, the existing "Missing R environment lockfile" finding is **downgraded from medium to low severity**. The updated message acknowledges the module loads and recommends renv as an additional layer for local reproducibility.
- R3. Same logic applies to Python: version-pinned Python module loads downgrade the "Missing Python reproducible environment" finding to low.
- R4. When R or Python module loads are present but **unpinned** (no version suffix, e.g., `module load R`), a new **medium-severity** finding is raised: "Module loaded without version pin." This is distinct from the missing-lockfile finding and fires regardless of whether a lockfile exists. Message: "Pin the version explicitly: `module load R/4.3.1`."
- R5. When multiple submission scripts load **different versions** of the same module (e.g., `module load R/4.2` in one script and `module load R/4.3.1` in another), a new **high-severity** finding is raised: "Module version inconsistent across scripts." The finding names the conflicting versions and the files they appear in.
- R6. If a project has both a lockfile (`renv.lock`) and version-pinned module loads, no finding is raised — this is the gold standard and should not be penalized.
- R7. Module load detection covers R and Python specifically for the lockfile downgrade logic (R2, R3). The version inconsistency check (R5) applies to any module, not just R and Python (e.g., `gcc`, `stata`, `julia`).

## Success Criteria

- A project with R files, no `renv.lock`, and `module load R/4.3.1` in all batch scripts produces a low-severity finding (not medium), with message recommending renv for local dev.
- A project with R files, no `renv.lock`, and `module load R` (unpinned) produces both the medium lockfile finding AND the medium unpinned-module finding.
- A project where `script_a.sh` has `module load R/4.2` and `script_b.sh` has `module load R/4.3.1` produces a high-severity version inconsistency finding.
- A project with `renv.lock` and `module load R/4.3.1` produces no finding.
- A project with no submission scripts and no `renv.lock` behaves exactly as today (medium finding, no change).

## Scope Boundaries

- Detecting whether a specific module version is available on any particular cluster is out of scope — static analysis only.
- No tracking of transitive dependencies loaded by module (e.g., `module load R/4.3.1` may implicitly load `gcc`) — only explicit `module load` statements.
- Non-R, non-Python module inconsistency (e.g., two versions of `gcc`) triggers R5 but does NOT affect the lockfile downgrade logic in R2/R3.

## Key Decisions

- **Downgrade, not suppress**: Version-pinned module loads reduce the lockfile finding to low, not zero. renv is still preferred for local reproducibility and deserves a nudge.
- **Unpinned is a distinct finding**: `module load R` creates false confidence — the researcher believes they've pinned their env but haven't. Deserves its own medium-severity message rather than being silently folded into "missing lockfile."
- **Version inconsistency is high severity**: Matches the severity of hardcoded paths. Results depending on script execution order is as serious a reproducibility failure as a non-portable path.

## Dependencies / Assumptions

- Depends on `.slurm`/`.job` being added to `SCRIPT_SUFFIXES` (see HPC path portability requirements). If that ships first, the scan scope is already in place. If not, this feature must add it independently.

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] What regex reliably captures `module load <name>/<version>` vs `module load <name>` across `ml` shorthand and multi-module lines (e.g., `module load R/4.3.1 gcc/12.2`)? Verify against real batch scripts in the apli project.
- [Affects R5][Technical] How to group findings when more than two scripts disagree on version — report all pairs or just flag the module name with a list of seen versions?

## Next Steps

→ `/ce:plan` for structured implementation planning
