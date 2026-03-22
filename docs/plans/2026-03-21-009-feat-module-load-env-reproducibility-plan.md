---
title: "feat: Module Load as Environment Reproducibility Evidence"
type: feat
status: active
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md
---

# feat: Module Load as Environment Reproducibility Evidence

## Overview

The `detect_environment_reproducibility` detector penalizes HPC projects that correctly pin their environment via `module load R/4.3.1` in submission scripts, because it only recognizes `renv.lock`/`pixi.lock`. This plan extends the detector to:

1. Recognize version-pinned module loads as partial environment evidence (downgrade medium → low for lockfile finding)
2. Flag unpinned module loads (`module load R` with no version) as a distinct medium finding
3. Flag cross-script version inconsistency (`module load R/4.2` in one script, `module load R/4.3.1` in another) as a high finding

**Prerequisite:** Plan 007 should be merged first so `.slurm`/`.job` are in `SCRIPT_SUFFIXES` — this detector scans those files for `module load` statements. If implementing independently, scanning those suffixes can be handled locally.

## Problem Statement

`detect_environment_reproducibility` (`detectors.py:667`) checks `renv.lock` / `pixi.lock` existence only. On HPC clusters, `renv` cannot always be used; `module load R/4.3.1` is the correct and expected reproducibility mechanism. The tool actively penalizes correct HPC practice. Additionally, version drift across scripts (`module load R/4.2` in one, `module load R/4.3.1` in another) is a genuine silent reproducibility failure that no tool currently detects.

(see origin: docs/brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md)

## Proposed Solution

### 1. Extract module load data from submission scripts

Add a helper function that scans a list of files for `module load` statements and returns a structured result:

```python
# econharness/detectors.py

# Matches: module load R/4.3.1  OR  ml R/4.3.1  OR  module load R  OR  ml R
# Captures: (module_name, version_or_None)
_MODULE_LOAD_PATTERN = re.compile(
    r"(?:^|\s)(?:module\s+load|ml)\s+([A-Za-z][A-Za-z0-9_\-+.]*?)(?:/([A-Za-z0-9._\-]+))?(?:\s|$)",
    re.MULTILINE,
)
SUBMISSION_SCRIPT_SUFFIXES = {".sh", ".slurm", ".job"}

def _collect_module_loads(files: list[Path]) -> dict:
    """
    Returns:
      {
        "pinned": {"R": {"4.3.1": [Path, ...], ...}, "gcc": {...}, ...},
        "unpinned": {"R": [Path, ...], ...},
      }
    """
    pinned: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    unpinned: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        if path.suffix not in SUBMISSION_SCRIPT_SUFFIXES:
            continue
        text = _read_text(path)
        for match in _MODULE_LOAD_PATTERN.finditer(text):
            name = match.group(1)
            version = match.group(2)
            if version:
                pinned[name][version].append(path)
            else:
                unpinned[name].append(path)
    return {"pinned": dict(pinned), "unpinned": dict(unpinned)}
```

### 2. Refactor `detect_environment_reproducibility` to use module load data

The function currently raises findings unconditionally when lockfiles are absent. Refactor to:

```python
def detect_environment_reproducibility(project_root: Path, config: dict, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    module_data = _collect_module_loads(files)
    pinned = module_data["pinned"]
    unpinned = module_data["unpinned"]

    # --- R lockfile check (R2) ---
    has_r = any(path.suffix.lower() in {".r", ".qmd", ".rmd"} for path in files)
    if has_r:
        lockfiles = config.get("environment", {}).get("r", {}).get("lockfiles", ["renv.lock"])
        if not any((project_root / lf).exists() for lf in lockfiles):
            r_pinned_versions = pinned.get("R", {})
            if r_pinned_versions:
                # Downgrade to low: version-pinned module load found
                findings.append(make_finding(
                    dimension="environment_reproducibility",
                    severity="low",
                    title="R environment pinned via module load but no renv.lock",
                    detail="R files are present. Version-pinned `module load R/...` statements were found in submission scripts, which satisfies cluster reproducibility. An `renv.lock` would additionally cover local development.",
                    remediation="Consider adopting `renv` for local development reproducibility. The module load already handles cluster execution.",
                    score_impact=5,
                ))
            else:
                # Original medium finding (no lockfile, no module load evidence)
                findings.append(make_finding(
                    dimension="environment_reproducibility",
                    severity="medium",
                    title="Missing R environment lockfile",
                    detail="R or Quarto files are present, but no declared R lockfile such as `renv.lock` was found.",
                    remediation="Adopt `renv` or another declared lockfile-backed R environment manager.",
                    score_impact=12,
                ))

    # --- Python lockfile check (R3) ---
    has_python = any(path.suffix.lower() == ".py" for path in files)
    if has_python:
        env_config = config.get("environment", {})
        lockfiles = env_config.get("python", {}).get("lockfiles", ["pixi.lock"])
        py_manager = env_config.get("python", {}).get("manager", "pixi")
        manager_hint = project_root / "pixi.toml"
        has_declared_lock = any((project_root / lf).exists() for lf in lockfiles)
        if not has_declared_lock or (py_manager == "pixi" and not manager_hint.exists()):
            py_pinned = {k: v for k, v in pinned.items() if k.lower() in ("python", "python3")}
            if py_pinned:
                findings.append(make_finding(
                    dimension="environment_reproducibility",
                    severity="low",
                    title="Python environment pinned via module load but no pixi.lock",
                    detail="Python files are present. Version-pinned `module load python/...` statements were found in submission scripts. A `pixi.lock` would additionally cover local development.",
                    remediation="Consider adopting `pixi` for local development reproducibility.",
                    score_impact=5,
                ))
            else:
                findings.append(make_finding(
                    dimension="environment_reproducibility",
                    severity="medium",
                    title="Missing Python reproducible environment metadata",
                    detail="Python files are present, but no declared lockfile-backed environment such as `pixi.toml` + `pixi.lock` was found.",
                    remediation="Adopt `pixi` or another declared lockfile-backed Python environment manager.",
                    score_impact=12,
                ))

    # --- Unpinned module loads (R4) ---
    for module_name, paths_list in unpinned.items():
        example_path = paths_list[0].name
        findings.append(make_finding(
            dimension="environment_reproducibility",
            severity="medium",
            title=f"Module loaded without version pin: `{module_name}`",
            detail=f"`module load {module_name}` (no version) found in submission scripts (e.g. `{example_path}`). The loaded version is cluster-default and may change silently.",
            remediation=f"Pin the version explicitly: `module load {module_name}/<version>` (e.g. `module load {module_name}/4.3.1`).",
            score_impact=8,
        ))

    # --- Version inconsistency across scripts (R5) ---
    for module_name, version_map in pinned.items():
        if len(version_map) > 1:
            version_summary = ", ".join(
                f"`{v}` ({p[0].name})" for v, p in sorted(version_map.items())
            )
            findings.append(make_finding(
                dimension="environment_reproducibility",
                severity="high",
                title=f"Module version inconsistent across scripts: `{module_name}`",
                detail=f"Different scripts load different versions of `{module_name}`: {version_summary}. Results depend on which script ran.",
                remediation=f"Standardize all submission scripts to load the same version of `{module_name}`.",
                score_impact=12,
            ))

    return findings
```

### 3. New test file `tests/test_module_load_env_reproducibility.py`

Follow the `tempfile.TemporaryDirectory` pattern from `test_version_control.py`:

Test cases:
- R files + no renv.lock + `module load R/4.3.1` in a `.slurm` → 1 low finding (not medium)
- R files + no renv.lock + `module load R` (unpinned) → medium lockfile finding + medium unpinned finding
- `script_a.slurm` with `module load R/4.2`, `script_b.slurm` with `module load R/4.3.1` → high version inconsistency finding
- R files + renv.lock + `module load R/4.3.1` → 0 findings (R6: gold standard)
- No submission scripts + no renv.lock → medium finding (unchanged behavior, R: existing behavior preserved)
- `module load gcc/12.2` in one script, `module load gcc/11.3` in another → high finding for `gcc` (R7: any module)
- `module load R` in a script → medium unpinned finding regardless of renv.lock existence

## Technical Considerations

- **`ml` shorthand**: Many HPC users use `ml` as shorthand for `module load`. The regex must cover both. The `_MODULE_LOAD_PATTERN` above handles this.
- **Multi-module lines**: `module load R/4.3.1 gcc/12.2` should be parsed as two separate loads. The `finditer` approach handles this naturally as long as the pattern doesn't consume the rest of the line on the first match. The pattern above uses a non-greedy name group and stops at whitespace/EOL.
- **Module name case sensitivity**: `R` vs `r` — use the exact case from the script. R is conventionally uppercase; Python may appear as `python`, `Python`, or `python3`. Handle `python`/`python3` as equivalent for the lockfile downgrade logic.
- **Deferred regex validation**: The outstanding question in the requirements doc asks to validate the regex against real apli batch scripts. The implementer should check `apli/analysis/code/cluster_models/` before finalizing the pattern.
- **R6 (gold standard, no finding)**: When `renv.lock` exists AND pinned module loads are found, the existing `has_declared_lock` check will return `True` and skip the lockfile finding entirely. The unpinned-module and version-inconsistency findings still fire independently of lockfile presence.

## Acceptance Criteria

- [ ] R files + no renv.lock + `module load R/4.3.1` in a batch script → low-severity finding recommending renv for local dev (not medium)
- [ ] R files + no renv.lock + `module load R` (unpinned) → medium lockfile finding AND medium unpinned-module finding
- [ ] `script_a.slurm` has `module load R/4.2`, `script_b.slurm` has `module load R/4.3.1` → high finding naming both versions and files
- [ ] R files + `renv.lock` present + `module load R/4.3.1` → no finding (gold standard)
- [ ] No submission scripts + no renv.lock → medium finding (existing behavior unchanged)
- [ ] `ml R/4.3.1` (shorthand) is parsed identically to `module load R/4.3.1`
- [ ] `module load R/4.3.1 gcc/12.2` (multi-module line) → two separate loads detected
- [ ] Version inconsistency for non-R, non-Python modules (e.g., `gcc`) still fires a high finding
- [ ] All test cases in `tests/test_module_load_env_reproducibility.py` pass

## Dependencies & Risks

- **Plan 007 preferred prerequisite**: Adds `.slurm`/`.job` to `SCRIPT_SUFFIXES`. This detector uses its own `SUBMISSION_SCRIPT_SUFFIXES` constant, so it works independently; however, coordinating with plan 007 is cleaner.
- **Refactors existing function**: `detect_environment_reproducibility` is an existing, presumably tested function. Ensure existing behavior (medium finding when no lockfile and no module loads) is preserved exactly.
- **Python module name ambiguity**: `python` vs `python3` needs explicit handling in the lockfile-downgrade path (R3). The version inconsistency check (R5) should treat `python` and `python3` as distinct modules (to avoid false positives), or normalize them — choose one approach and document it.

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md](../brainstorms/2026-03-21-module-load-env-reproducibility-requirements.md) — key decisions: downgrade not suppress; unpinned is distinct finding; version inconsistency is high severity
- Function to modify: `econharness/detectors.py:667` (`detect_environment_reproducibility`)
- Config pattern: `econharness/config.py:37` (environment section)
- Test pattern reference: `tests/test_version_control.py`
