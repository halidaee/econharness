---
title: "feat: Smart config bootstrapping on init with ambiguous-pipeline detector"
type: feat
status: completed
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-smart-init-requirements.md
---

# feat: Smart Config Bootstrapping on `init`

## Overview

`econharness init` currently writes a static default config with empty pipeline commands.
Any agent or researcher who runs `init` then `verify` immediately gets `ValueError: No 'fast'
verification command is configured`. This fix introspects the project at init time to emit
a pre-populated YAML config with inline comments, and adds a `detect_ambiguous_pipeline`
scanner detector for projects with multiple conflicting entry points.

## Problem Statement / Motivation

Cold-start friction blocks every new project. The `init` → `scan` → `verify` loop is the
primary agent workflow; an empty config breaks it at step 3. Beyond that, a project with
both a `Makefile` and a `run_all.R` has an ambiguous authoritative pipeline — a real
discipline violation that the scanner should flag, regardless of how config was created.

## Proposed Solution

Add a `bootstrap_config(project_root)` function that introspects the project root for known
pipeline entry points and environment lock files, then renders a YAML config string with
inline comments. `init` calls this instead of `render_default_config`. The new
`detect_ambiguous_pipeline` detector catches the multiple-entry-point violation at scan time.

## Technical Considerations

### YAML Output: Hand-crafted String (No New Dependency)

`load_config` already optionally imports PyYAML for reading (`config.py:99`). For writing
YAML **with inline comments**, PyYAML is not usable (it strips comments). The config must
be written as a hand-crafted template string. This preserves the zero-runtime-dependency
constraint — PyYAML is only needed at read time and remains optional.

`render_default_config` (JSON) is unchanged. Only `init` uses the new YAML path.

### Introspection: Shallow, Root-Level Only

Check `project_root` (and one level deep for stage dirs). No Makefile parsing, no R script
AST. Existence of a file is the only signal used.

### Inferred Command Mapping

| Entry point | `fast` | `full` | `tests` |
|---|---|---|---|
| `Makefile` | `make fast` | `make` | `make test` |
| `run_all.sh` | `bash run_all.sh` | `bash run_all.sh` | *(blank)* |
| `run_all.R` | `Rscript run_all.R` | `Rscript run_all.R` | *(blank)* |
| `run_all.py` | `python run_all.py` | `python run_all.py` | *(blank)* |
| `Snakefile` | `snakemake` | `snakemake` | *(blank)* |
| `dodo.py` | `doit` | `doit` | *(blank)* |

For `Makefile`: `make fast` and `make test` are common conventions but may not exist —
a YAML comment notes this: `# verify 'make fast' and 'make test' targets exist`.

### `detect_ambiguous_pipeline` Detector

New detector in `detectors.py` using `make_finding`. Scans project root for the set of
known entry point filenames. If 2+ are found: emits one high-severity finding. This fires
on every `scan`, independently of `init`. The detector lives in `detectors.py` alongside
the other detectors and is registered in `scanner.py`.

## System-Wide Impact

- **`config.py`**: `render_default_config` unchanged. New `bootstrap_config(project_root) -> str`
  function added, returns a YAML string. `init` calls `bootstrap_config` instead of
  `render_default_config`.
- **`cli.py` `init` branch**: Path check and `--force` logic unchanged. Config content
  switches from `render_default_config()` (JSON) to `bootstrap_config(project_root)` (YAML).
  Prints detection summary after writing.
- **`detectors.py`**: New `detect_ambiguous_pipeline(project_root, config)` function added.
- **`scanner.py`**: `detect_ambiguous_pipeline` registered in the detector list.
- **`load_config`**: No change needed — already supports YAML via optional PyYAML
  (`config.py:99`). A YAML config written by smart `init` will load correctly.
- **`tests/`**: Tests for `bootstrap_config` (single entry, multiple entries, no entries,
  env detection, path detection) and `detect_ambiguous_pipeline`.

## Acceptance Criteria

- [ ] `econharness init` on a project with a single `Makefile` writes `.econharness.yml` as
  YAML with `pipeline.command.fast: make fast`, `.full: make`, `.tests: make test` and a
  comment `# detected: Makefile — verify 'make fast' and 'make test' targets exist`.
- [ ] `econharness init` on a project with `run_all.R` and no other entry point writes
  `pipeline.command.fast: Rscript run_all.R` etc.
- [ ] `econharness init` on a project with **both** `Makefile` and `run_all.R` leaves all
  pipeline command fields blank and adds YAML comment:
  `# WARNING: multiple pipeline entry points detected (Makefile, run_all.R) — resolve ambiguity`.
  CLI prints: `Warning: multiple pipeline entry points found. Pipeline commands left blank — resolve before running verify.`
- [ ] `econharness init` on a project with no known entry points writes blank pipeline
  commands with comment `# no pipeline entry point detected — set manually`.
- [ ] Detected environment lock files populate `environment` section:
  - `pixi.toml` or `pixi.lock` → `environment.python.manager: pixi`
  - `renv.lock` → `environment.r.manager: renv`, `lockfiles: [renv.lock]`
  - Neither found → section retains defaults with comment `# no lock files detected`
- [ ] Detected stage directories reflected in `paths`: if `data/raw/` exists but `raw/`
  does not, `paths.raw: data/raw`. Confirmed dirs noted `# directory exists`; missing dirs
  noted `# directory not found — create or update this path`.
- [ ] `init` prints a detection summary to stdout listing detected files and inferred values.
- [ ] `econharness init --force` re-introspects and overwrites. `init` without `--force` still
  refuses to overwrite an existing config (existing behavior unchanged).
- [ ] `render_default_config()` (used by other callers) is unchanged — still returns JSON.
- [ ] `econharness scan` on a project with both `Makefile` and `run_all.R` emits a
  **high-severity** finding `detect_ambiguous_pipeline` in dimension `automation`.
  Remediation: `"Designate one authoritative pipeline entry point and remove or subordinate the others."`
- [ ] `detect_ambiguous_pipeline` fires regardless of how `.econharness.yml` was created.
- [ ] Tests: `bootstrap_config` single-entry, multiple-entry, no-entry, env detection, path
  detection. `detect_ambiguous_pipeline`: single entry (no finding), multiple entries (finding).

## Dependencies & Risks

- **PyYAML for reading**: `load_config` already handles YAML optionally. The YAML produced
  by `bootstrap_config` must be valid YAML that `json.loads` will fail on (so fallback to
  PyYAML kicks in). Comments starting with `#` make the file non-JSON-parseable, ensuring
  the PyYAML path is used. If PyYAML is not installed on the user's system, `load_config`
  will raise `ValueError` on a YAML config. Document this: if `init` writes YAML, PyYAML
  must be present at scan time.
- **Alternative**: Write config as JSON but emit a separate human-readable summary file.
  Rejected — comments in the config file itself are more discoverable and natural.
- **Stage path detection**: Only checks exact default names (`raw/`, `derived/` etc.) plus
  one `data/<name>/` variant. More exotic layouts fall back to defaults with a comment.

## Implementation Notes

### New function: `config.py` — `bootstrap_config`
```python
# config.py
ENTRY_POINT_COMMANDS = {
    "Makefile": {"fast": "make fast", "full": "make", "tests": "make test"},
    "run_all.sh": {"fast": "bash run_all.sh", "full": "bash run_all.sh", "tests": ""},
    "run_all.R":  {"fast": "Rscript run_all.R", "full": "Rscript run_all.R", "tests": ""},
    "run_all.py": {"fast": "python run_all.py", "full": "python run_all.py", "tests": ""},
    "Snakefile":  {"fast": "snakemake", "full": "snakemake", "tests": ""},
    "dodo.py":    {"fast": "doit", "full": "doit", "tests": ""},
}

def bootstrap_config(project_root: Path) -> str:
    # 1. Detect entry points, env files, stage dirs
    # 2. Build annotated YAML string using string template
    # 3. Return YAML string
```

### New detector: `detectors.py` — `detect_ambiguous_pipeline`
```python
KNOWN_ENTRY_POINTS = list(ENTRY_POINT_COMMANDS.keys())  # or defined locally

def detect_ambiguous_pipeline(project_root: Path, config: dict) -> list[Finding]:
    found = [ep for ep in KNOWN_ENTRY_POINTS if (project_root / ep).exists()]
    if len(found) >= 2:
        return [make_finding(
            dimension="automation",
            severity="high",
            title="Ambiguous authoritative pipeline",
            detail=f"Multiple pipeline entry points found: {', '.join(found)}. "
                   "It is unclear which is the single source of truth for the full pipeline.",
            remediation="Designate one authoritative pipeline entry point and remove or "
                        "subordinate the others.",
            score_impact=8.0,
        )]
    return []
```

### Sample YAML output (single Makefile)
```yaml
# econharness configuration
# Generated by econharness init — edit as needed

pipeline:
  command:
    fast: "make fast"   # detected: Makefile — verify 'make fast' target exists
    full: "make"        # detected: Makefile
    tests: "make test"  # detected: Makefile — verify 'make test' target exists
  entrypoints: []

environment:
  python:
    manager: pixi       # detected: pixi.toml
    lockfiles: [pixi.lock]
  r:
    manager: renv       # detected: renv.lock
    lockfiles: [renv.lock]

paths:
  raw: raw              # directory not found — create or update this path
  derived: derived      # directory not found — create or update this path
  analysis: analysis    # directory exists
  ...
```

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-smart-init-requirements.md](../brainstorms/2026-03-21-smart-init-requirements.md)
  — Key decisions: YAML with comments; multiple entry points = blank + high-severity finding;
  shallow introspection only; `render_default_config` (JSON) unchanged.
- `econharness/config.py:79-111` — `default_config`, `render_default_config`, `load_config`
- `econharness/cli.py:76-78` — `init` subparser, `--force` flag (model for unchanged behavior)
- `econharness/detectors.py:107-129` — `make_finding` function to use for new detector
- `econharness/scanner.py` — detector registration (planner: verify registration pattern)
