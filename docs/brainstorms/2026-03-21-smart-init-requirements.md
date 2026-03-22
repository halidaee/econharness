---
date: 2026-03-21
topic: smart-init
---

# Smart Config Bootstrapping on `init`

## Problem Frame

`econharness init` writes a static default config with empty pipeline commands, empty stages,
and generic placeholder paths. Any agent or researcher who runs `init` then `verify` immediately
gets `ValueError: No 'fast' verification command is configured`. The cold-start problem blocks
every new project. Introspecting the project at init time lets econharness emit a pre-populated
config instead — and flag structural ambiguities it finds as first-class issues.

## Requirements

- R1. `econharness init` introspects the project before writing config. Introspection covers:
  - **Pipeline entry points**: presence of `Makefile`, `run_all.sh`, `run_all.R`, `run_all.py`,
    `Snakefile`, `dodo.py` at the project root
  - **Environment lock files**: presence of `pixi.toml`/`pixi.lock`, `renv.lock`,
    `requirements.txt`, `pyproject.toml`, `conda.yml`/`environment.yml`
  - **Stage directories**: which of `raw/`, `derived/`, `analysis/`, `output/`, `paper/`,
    `temp/` actually exist

- R2. If **exactly one** pipeline entry point is detected, `init` pre-populates
  `pipeline.command.fast`, `.full`, and `.tests` with inferred commands (e.g. `make fast`,
  `make full`, `make tests` for a Makefile; `Rscript run_all.R` for a lone R entry point).
  A YAML comment above each command explains the inference: `# detected: Makefile`.

- R3. If **multiple** pipeline entry points are detected, `init` leaves all pipeline command
  fields blank and adds a YAML comment listing every detected file:
  `# WARNING: multiple pipeline entry points detected (Makefile, run_all.R) — resolve ambiguity`.
  The CLI prints a visible warning: `Warning: multiple pipeline entry points found. Pipeline
  commands left blank — resolve before running verify.`

- R4. A new scanner detector (`detect_ambiguous_pipeline`) flags projects with multiple
  candidate pipeline entry points as a **high-severity** finding in dimension `automation`.
  This fires on `scan`, independently of whether `init` was used. Remediation text: "Designate
  one authoritative pipeline entry point and remove or subordinate the others."

- R5. Detected environment lock files populate the `environment` section. If `renv.lock` is
  found, `environment.r.manager` is set to `renv` and `lockfiles` lists the found file. If
  `pixi.toml` or `pixi.lock` is found, `environment.python.manager` is set to `pixi`. If
  neither R nor Python lock files are found, the environment section retains the default
  with a YAML comment: `# no lock files detected — add renv.lock or pixi.lock`.

- R6. Detected stage directories are reflected in `paths`. If `data/raw/` exists but `raw/`
  does not, `paths.raw` is set to `data/raw`. Paths confirmed to exist are noted with a YAML
  comment: `# directory exists`. Paths not found are noted: `# directory not found — create
  or update this path`.

- R7. `init` prints a summary of what was detected and what was inferred:
  ```
  Detected: Makefile, pixi.toml, renv.lock
  Inferred: pipeline.command.fast = "make fast"
  Not found: raw/, derived/ (paths left as defaults)
  Config written to .econharness.yml
  ```

- R8. The config file is written as **YAML** (not JSON), enabling inline comments. The
  `render_default_config` function remains JSON-only (used by other callers); `init` uses
  a new YAML rendering path.

- R9. `init --force` overwrites an existing config with a fresh introspection-based config,
  same as today but with the new smart behavior. Without `--force`, `init` refuses to
  overwrite an existing config (existing behavior unchanged).

## Success Criteria

- An agent calling `init` then `scan` on a project with a single `Makefile` does not receive
  `ValueError: No 'fast' verification command is configured`.
- A project with both a `Makefile` and `run_all.R` gets a high-severity `ambiguous_pipeline`
  finding on `scan`, independent of how config was created.
- `init` on a blank project produces a commented YAML config explaining every blank field.

## Scope Boundaries

- Introspection is shallow (project root and one level deep for stage dirs). No AST parsing
  of Makefiles or R scripts to infer what targets exist.
- `init` does not create directories or modify existing project files beyond `.econharness.yml`.
- `render_default_config` (JSON) is unchanged — only the `init` command switches to YAML output.
- Stages section is not auto-populated (too complex to infer reliably from structure alone).
- No `--dry-run` flag in this scope.

## Key Decisions

- **Multiple entry points = blank config + high-severity finding**: Ambiguous pipeline is a
  real discipline violation, not just a config-authoring inconvenience. It warrants a scanner
  finding independent of `init`.
- **YAML output with comments**: The primary value of smart init is transparency — users need
  to see what was detected and why. Comments are essential; JSON cannot express them.
- **Shallow introspection only**: Parsing Makefiles or R scripts to infer target names is
  fragile and high-maintenance. Inferring standard command patterns (e.g. `make fast`) from
  file existence is sufficient and stable.

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] What inferred commands should be suggested per entry point? e.g.
  Makefile → `make fast` / `make all` / `make test`; run_all.R → `Rscript run_all.R`; etc.
  Planner to define the full mapping.
- [Affects R8][Technical] Does PyYAML need to be added as an optional or required dependency
  for `init`, or should the YAML be written as a hand-crafted string to preserve
  zero-dependency constraint?
- [Affects R4][Needs research] Check existing detectors (detectors.py) for any existing
  pipeline-ambiguity detection before adding `detect_ambiguous_pipeline`.

## Next Steps
→ `/ce:plan` for structured implementation planning
