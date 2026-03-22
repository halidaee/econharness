---
date: 2026-03-21
topic: hpc-path-portability
---

# HPC Path Portability: Extend Absolute Path Detection

## Problem Frame

Economics research projects increasingly run on Slurm HPC clusters. The current `path_portability` detector covers local machine paths (`/Users/jsmith/`, `/home/jsmith/`) but has no knowledge of HPC-specific cluster filesystems. Scripts with hardcoded paths like `/scratch/jsmith/data.csv` or `/gpfs/scratch/pilab/project/` pass the linter clean today, giving false confidence that the project is portable — when in fact it is tied to a specific cluster and user account.

econharness always runs locally. All detection is pure static analysis of project files.

## Requirements

- R1. The `path_portability` detector flags paths that begin with known HPC cluster filesystem roots: `/scratch/`, `/gpfs/`, `/lustre/`, `/beegfs/`. These roots are not present on local development machines and are therefore always non-portable when hardcoded.
- R2. Paths within these HPC roots that use environment variable interpolation — e.g., `$SCRATCH/`, `$SLURM_TMPDIR/`, `${SCRATCH}/` — are **not** flagged. They are the correct portable HPC pattern.
- R3. Paths like `/scratch/$USER/myproject` (env var for the username but the filesystem root is still hardcoded) **are** flagged. The path remains cluster-specific even with `$USER`.
- R4. The detector scans `.slurm` and `.job` files in addition to the existing `SCRIPT_SUFFIXES` set. Batch scripts are first-class pipeline artifacts and the most common location for cluster-specific paths.
- R5. `.econharness.yml` gains an `allowed_path_prefixes` field (list of strings). Paths matching any prefix in this list are excluded from path portability findings. This allows projects that intentionally use a known shared cluster mount (e.g., `/project/pilab/`) to declare it explicitly rather than suppress per-finding.
- R6. The remediation message for new HPC path findings guides toward env-var parametrization: "Replace with an environment variable such as `$SCRATCH`, `$WORK`, or a path declared in `.econharness.yml`."
- R7. Severity of new HPC path findings matches existing absolute path findings: **high**.

## Success Criteria

- A script containing `/scratch/jsmith/data.csv` produces a high-severity `path_portability` finding.
- A script containing `$SCRATCH/data.csv` produces no finding.
- A script containing `/scratch/$USER/data.csv` produces a finding (cluster-specific root, even with env var username).
- A `.slurm` file containing `/gpfs/scratch/pilab/data.csv` produces a finding.
- A project with `allowed_path_prefixes: ["/project/pilab/"]` in `.econharness.yml` produces no finding for paths under `/project/pilab/`.
- Existing local-machine path detection (`/Users/`, `/home/[username]/`, `/Volumes/`, `/mnt/`) is unchanged.

## Scope Boundaries

- Cluster-canonical software paths (`/apps/R/4.3.1/`, `/software/stata/`) are out of scope — too noisy given researchers often can't control software installation.
- No detection of whether env vars like `$SCRATCH` are actually defined or valid — that requires runtime knowledge econharness doesn't have.
- No new check for whether paths exist on the local filesystem.

## Key Decisions

- **`/scratch/$USER/` is flagged**: Even though `$USER` is parametrized, the filesystem root `/scratch/` is cluster-specific and the path won't work on another cluster or locally.
- **Allowlist over per-finding suppress**: `allowed_path_prefixes` in config is cleaner than suppressing dozens of individual findings for a known shared project directory.
- **`.slurm`/`.job` added to scan scope**: Batch scripts are where HPC paths are most concentrated; not scanning them leaves the biggest gap.

## Dependencies / Assumptions

- The `allowed_path_prefixes` config field requires a `check-config` schema update (plan 006) to validate the new field type.

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Needs research] Which additional HPC filesystem roots beyond `/scratch/`, `/gpfs/`, `/lustre/`, `/beegfs/` are worth including? (e.g., `/work/`, `/ocean/`, `/project/`, `/hpc/`, `/cluster/`) — survey common cluster naming conventions.
- [Affects R2][Technical] How to reliably detect env-var interpolation in paths across R, Python, and shell syntax (`$SCRATCH/`, `Sys.getenv("SCRATCH")`, `os.getenv("SCRATCH")`). Shell detection is straightforward; R and Python require different patterns.
- [Affects R5][Technical] Where in `DEFAULT_CONFIG` and `load_config` does `allowed_path_prefixes` get added, and does it need a migration path for existing configs?

## Next Steps

→ `/ce:plan` for structured implementation planning
