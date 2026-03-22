---
date: 2026-03-21
topic: hpc-batch-script-health
---

# HPC Batch Script Health: Missing `set -e` Detection

## Problem Frame

Batch scripts (`.sh`, `.slurm`, `.job` files containing `#SBATCH` headers) are first-class pipeline artifacts in HPC research projects. Without `set -e`, a failed step is silently swallowed — the job continues and exits 0. The scheduler marks it complete, the researcher sees no error, and partial or incorrect outputs are treated as valid results. econharness currently has no checks on batch script fault-tolerance. All detection is pure static analysis.

## Requirements

- R1. The detector scans files with `.sh`, `.slurm`, and `.job` extensions that contain at least one `#SBATCH` directive, and checks whether `set -e` is present anywhere in the file body (including inline, not just at the top).
- R2. `#!/bin/bash -e` in the shebang line counts as satisfying the `set -e` requirement.
- R3. If `set -e` is absent, raise a **medium-severity** finding: "Batch script missing `set -e` — failed steps will be silently swallowed."
- R4. Remediation message: "Add `set -e` near the top of the script so that any failed command causes the job to exit immediately with a non-zero code."

## Success Criteria

- A `.slurm` file with `#SBATCH` directives and no `set -e` anywhere produces a medium finding.
- A `.slurm` file with `set -e` anywhere in the body (even after the `#SBATCH` block) produces no finding.
- A `.sh` file with `#!/bin/bash -e` produces no finding.
- A `.sh` file without any `#SBATCH` directive is not checked (not a batch script).
- A plain shell script with no `#SBATCH` is ignored entirely.

## Scope Boundaries

- `set -u` is out of scope — less universal practice, higher false positive rate.
- Hardcoded partition names are out of scope — often unavoidable and cluster-specific by necessity.
- Login node execution anti-patterns in documentation are out of scope — too hard to detect reliably.
- No check for `set -o pipefail` — keep scope tight to `set -e` only.

## Key Decisions

- **`#SBATCH` presence is the trigger**: Only files with at least one `#SBATCH` line are checked. Plain shell scripts that aren't batch submissions are not affected.
- **Anywhere in file body counts**: `set -e` set inline (not at top) is still valid. The check is presence/absence, not position.
- **Medium severity**: The failure is real but many scripts work without it in practice; same tier as missing lockfile.

## Dependencies / Assumptions

- Depends on `.slurm`/`.job` being added to `SCRIPT_SUFFIXES` (also required by the HPC path portability feature). If that ships first, scan scope is already in place.

## Next Steps

→ `/ce:plan` for structured implementation planning
