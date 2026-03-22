---
title: "feat: HPC Path Portability — cluster filesystem roots + env-var exemptions + allowlist config"
type: feat
status: active
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-hpc-path-portability-requirements.md
---

# feat: HPC Path Portability

## Overview

The current `path_portability` detector only flags local-machine paths (`/Users/`, `/home/`, `/Volumes/`, `/mnt/`). Scripts hardcoding HPC cluster filesystem roots (`/scratch/jsmith/`, `/gpfs/pilab/`) pass clean today, giving false confidence. This plan extends the detector with:

1. HPC filesystem root detection (`/scratch/`, `/gpfs/`, `/lustre/`, `/beegfs/`)
2. Env-var exemptions (`$SCRATCH/`, `$SLURM_TMPDIR/` are portable and must NOT be flagged)
3. Scan extension to `.slurm` and `.job` files (batch scripts are first-class pipeline artifacts)
4. `allowed_path_prefixes` config field for intentional shared cluster mounts

This is the **foundational HPC plan** — plans 008, 009, and 010 all depend on the `.slurm`/`.job` scan extension introduced here.

## Problem Statement

`detect_path_portability` (`detectors.py:705`) scans `SCRIPT_SUFFIXES` against `ABSOLUTE_PATH_PATTERNS`. Neither the suffix set nor the pattern set is aware of HPC cluster filesystems:

- `SCRIPT_SUFFIXES` (`detectors.py:48`) does not include `.slurm` or `.job`, so batch scripts are never scanned.
- `ABSOLUTE_PATH_PATTERNS` has no HPC entries — `/scratch/jsmith/data.csv` passes clean.
- The detector cannot distinguish `/scratch/jsmith/` (hardcoded, bad) from `$SCRATCH/data.csv` (env-var, portable).
- There is no mechanism to whitelist a known shared cluster mount such as `/project/pilab/`.

Projects like `apli` that actively use `analysis/code/cluster_models/` receive a clean score on the dimension that matters most for cluster portability.

(see origin: docs/brainstorms/2026-03-21-hpc-path-portability-requirements.md)

## Proposed Solution

### 1. Add `.slurm` and `.job` to `SCRIPT_SUFFIXES` (`detectors.py:48`)

```python
# detectors.py
SCRIPT_SUFFIXES = {".py", ".R", ".r", ".qmd", ".sh", ".md", ".txt", ".do", ".slurm", ".job"}
```

This is a prerequisite for plans 008, 009, and 010. All batch script scanning in those features flows through `SCRIPT_SUFFIXES`.

### 2. Add HPC path patterns and env-var exemption logic (`detectors.py`)

Add a new constant for HPC filesystem roots:

```python
# detectors.py — after ABSOLUTE_PATH_PATTERNS
HPC_PATH_ROOT_PATTERN = re.compile(r"/(?:scratch|gpfs|lustre|beegfs)/")
# Portable: path begins with an environment variable like $SCRATCH/ or ${SLURM_TMPDIR}/
HPC_ENV_VAR_PREFIX_PATTERN = re.compile(r'\$\{?[A-Z_][A-Z0-9_]*\}?/')
```

Detection logic: for each line in the file, if `HPC_PATH_ROOT_PATTERN` matches, check whether the match position is immediately preceded by a `$` or `${`. If yes → env-var path → skip. If no → hardcoded root → flag. Note that `/scratch/$USER/` must still be flagged (the root `/scratch/` is hardcoded even though the username is parametrized).

### 3. Add `allowed_path_prefixes` to `DEFAULT_CONFIG` and `config.py`

```python
# config.py DEFAULT_CONFIG — add new top-level key
"path_portability": {
    "allowed_prefixes": [],
},
```

`allowed_prefixes` is a list of strings. Any path matching one of these prefixes is excluded from path portability findings. Example: `["/project/pilab/"]`.

### 4. Update `detect_path_portability` signature to accept `config`

```python
# detectors.py
def detect_path_portability(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
```

Update the call in `scanner.py:46`:
```python
findings.extend(detect_path_portability(project_root, config, files))
```

Inside the function, extract the allowlist:
```python
allowed_prefixes = config.get("path_portability", {}).get("allowed_prefixes", [])
```

Skip any path match that starts with a prefix in `allowed_prefixes`.

### 5. HPC finding message

```python
make_finding(
    dimension="path_portability",
    severity="high",
    title="HPC cluster path hardcoded in project source",
    detail=f"{rel} contains a hardcoded HPC filesystem path.",
    remediation="Replace with an environment variable such as `$SCRATCH`, `$WORK`, or declare the prefix in `.econharness.yml` under `path_portability.allowed_prefixes`.",
    score_impact=12,
    path=rel,
)
```

### 6. Update `bootstrap_config` and `render_default_config`

`bootstrap_config` (`config.py:126`) generates the annotated YAML written by `init`. Add a `path_portability` section:

```yaml
path_portability:
  allowed_prefixes: []  # add known shared cluster mounts to suppress findings
```

`render_default_config` uses `json.dumps(default_config())` so the new key appears automatically once added to `DEFAULT_CONFIG`.

## Technical Considerations

- **Env-var prefix detection**: The check `text[match.start()-1] in ('$',)` is not sufficient for `${VAR}/`. Use a backward scan or a combined pattern that anchors the HPC root to the start of a path token. Safest: use a negative lookbehind regex `(?<!\}|[A-Z0-9_$])/scratch/` — but Python `re` doesn't support variable-length lookbehinds. Alternative: scan line-by-line and check if the portion before the matched `/scratch/` ends in a closing `}` or a `$`-prefixed identifier. This is a deferred implementation detail.
- **Existing false positive on `apli`**: The `repo_dag_report.md` path portability finding on `apli` (score 88.3) was `/scratch/` appearing inside a markdown doc — a description, not a path reference. After this change, the same logic applies: if the markdown line contains a bare `/scratch/jsmith/`, it would now be flagged as HPC non-portable (correct). The existing finding was already flagging a different pattern.
- **`detect_path_portability` now requires `config`**: Every call site in tests and `scanner.py` must be updated. There are no tests that call `detect_path_portability` directly today (confirmed: no `test_detectors.py` file), but integration tests via `scan_project` will be affected if `DEFAULT_CONFIG` doesn't include the new key.
- **Config schema test**: `test_config_schema.py` tests `default_config()` shape — add an assertion that `config["path_portability"]["allowed_prefixes"] == []`.

## Acceptance Criteria

- [ ] `/scratch/jsmith/data.csv` in any `SCRIPT_SUFFIXES` file produces a high-severity `path_portability` finding (title: "HPC cluster path hardcoded in project source")
- [ ] `$SCRATCH/data.csv` in a script produces no finding
- [ ] `${SLURM_TMPDIR}/data.csv` in a script produces no finding
- [ ] `/scratch/$USER/data.csv` produces a finding (cluster-specific root despite parametrized username)
- [ ] A `.slurm` file containing `/gpfs/pilab/data.csv` produces a finding
- [ ] A `.slurm` file containing `$SCRATCH/data.csv` produces no finding
- [ ] A project with `path_portability: {allowed_prefixes: ["/project/pilab/"]}` produces no finding for `/project/pilab/output.csv`
- [ ] A plain `.sh` file without `#SBATCH` is still scanned (`.sh` was already in `SCRIPT_SUFFIXES`)
- [ ] Existing local-machine path detection (`/Users/`, `/home/[username]/`, `/Volumes/`, `/mnt/`) is unchanged
- [ ] `detect_path_portability` accepts `config` as its second positional argument; all call sites updated
- [ ] `default_config()` includes `path_portability.allowed_prefixes: []`
- [ ] `bootstrap_config()` output includes the `path_portability` section with a comment

## Dependencies & Risks

- **Foundational for plans 008, 009, 010**: The `.slurm`/`.job` SCRIPT_SUFFIXES addition here removes a prerequisite step from all three downstream plans. Implement this plan first.
- **Config parameter addition to `detect_path_portability`**: Low risk — `scanner.py` is the only call site outside tests. Must be updated atomically with the detector change.
- **No test file for path portability yet**: Tests must be added as part of this plan (a `test_path_portability.py`). Follow the pattern in `test_version_control.py` using `tempfile.TemporaryDirectory` and direct detector calls.

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-hpc-path-portability-requirements.md](../brainstorms/2026-03-21-hpc-path-portability-requirements.md) — key decisions: env-var exempt but root-hardcoded flagged; allowlist over per-finding suppress; `.slurm`/`.job` added to scan scope
- Similar detector implementation: `econharness/detectors.py:705` (`detect_path_portability`)
- Config pattern: `econharness/config.py:13` (`DEFAULT_CONFIG`)
- Scanner call site: `econharness/scanner.py:46`
- Config schema tests: `tests/test_config_schema.py`
