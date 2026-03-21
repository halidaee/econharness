# econharness Implementation Plan

This plan turns [ROADMAP.md](/Users/halidaee/Documents/GitHub/econharness/ROADMAP.md) into an execution sequence.

Scope covered here:

- version-control discipline
- stage contracts
- narrow self-documenting-code checks
- function state discipline
- test command and test presence
- from-scratch rebuild verification with quarantine
- slow-stage discipline
- README / agent-prompt tightening needed to support the new config

Out of scope for this plan:

- relational keyed-table / foreign-key / normalization analysis
- guard detection around joins and other risky operations
- task-tracking checks
- LLM-based naming or semantic readability analysis

## Working Principles

### 1. One Increment Per Commit

Each milestone below should end with:

- targeted tests for the new feature
- a full test-suite run
- a clean git worktree
- one commit before moving to the next milestone

No milestone should bundle two logically separate features unless one is required to expose the other.

### 2. Prefer Small New Modules Over Growing `detectors.py`

The current repo already benefits from moving complex logic into dedicated modules such as [lookup_reconstruction.py](/Users/halidaee/Documents/GitHub/econharness/econharness/lookup_reconstruction.py).

Follow the same pattern for the remaining work:

- keep [detectors.py](/Users/halidaee/Documents/GitHub/econharness/econharness/detectors.py) as the orchestration surface
- move feature-specific parsing or reasoning into focused modules
- add small helpers in [config.py](/Users/halidaee/Documents/GitHub/econharness/econharness/config.py) and [verify.py](/Users/halidaee/Documents/GitHub/econharness/econharness/verify.py) rather than embedding policy in the CLI

### 3. Add Focused Test Modules

Do not continue growing [tests/test_cli.py](/Users/halidaee/Documents/GitHub/econharness/tests/test_cli.py) as the only place for new behavior.

Add focused modules:

- `tests/test_config_schema.py`
- `tests/test_version_control.py`
- `tests/test_self_documenting_clarity.py`
- `tests/test_function_state.py`
- `tests/test_stage_contracts.py`
- `tests/test_verify.py`

Keep [tests/test_cli.py](/Users/halidaee/Documents/GitHub/econharness/tests/test_cli.py) for end-to-end CLI wiring and smoke behavior.

### 4. Verify In Three Layers

For every milestone:

1. run targeted tests for the new feature
2. run the full unit test suite
3. run one manual smoke command when the feature affects CLI behavior or scan output

Recommended recurring commands:

```bash
python3 -m py_compile econharness/*.py tests/*.py
python3 -m unittest -q
python3 -m econharness scan --path tests/fixtures/good_project
```

When the feature changes detector behavior materially, also run a calibration smoke on a real repo such as `/Users/halidaee/apli` and record the before/after finding set in the commit notes.

## Architecture Decisions To Lock Before Coding

### Unified Stage Schema

Use one top-level `stages` list in `.econharness.yml` rather than splitting stage contracts and slow stages into different config sections.

Proposed schema:

```yaml
stages:
  - name: main_analysis
    match: ["analysis/code/main/**"]
    read_roots: ["raw", "derived"]
    write_roots: ["derived", "temp/main_analysis"]
    slow: false

  - name: estimate_models
    match: ["analysis/code/models/**"]
    read_roots: ["derived"]
    write_roots: ["derived/models", "temp/models"]
    slow: true
    command: "Rscript analysis/code/models/run_models.R"
    outputs: ["derived/models", "derived/predictions"]
```

Field behavior:

- `name`: required
- `match`: optional for pure pipeline stages, but required for stage-contract enforcement on code files
- `read_roots`: optional list of allowed read roots
- `write_roots`: optional list of allowed write roots
- `slow`: boolean, default `false`
- `command`: optional stage-level command
- `inputs`: optional stage artifact roots
- `outputs`: optional stage artifact roots produced by the stage

Backward compatibility:

- keep reading `pipeline.heavy_stages` for one release as a fallback
- normalize it into the new `stages` representation during config load
- prefer the new `stages` shape in `init`, README examples, and all new tests

### Quarantine Instead Of Deletion

All from-scratch verification must move generated artifacts into a gitignored quarantine directory rather than deleting them.

Proposed location:

- `.econharness/quarantine/<timestamp>/`

Behavior:

- move only generated artifacts, never raw inputs
- preserve relative paths under quarantine
- emit a structured report of what was moved and what regenerated

### Dimension Mapping

Keep score changes minimal while still making the new features visible.

Proposed mapping:

- `version_control_discipline`: new dimension
- `directory_and_stage_structure`: stage-contract findings
- `self_documenting_clarity`: filename and function-name clarity findings
- `software_hygiene_and_redundancy`: function state discipline findings
- `automation_and_one_command_rebuild`: test-command presence and slow-stage discipline findings

Add the new dimension weight in [scoring.py](/Users/halidaee/Documents/GitHub/econharness/econharness/scoring.py) during Milestone 1 so scorecard output stays stable as detectors land.

## Milestone Sequence

### Milestone 1. Config Schema Groundwork And README Prompt Tightening

Goal:

- introduce the unified `stages` schema
- keep config loading backward-compatible
- update the default config and README prompt so LLM agents are expected to populate stage and slow-stage metadata

Code changes:

- update [config.py](/Users/halidaee/Documents/GitHub/econharness/econharness/config.py)
- add stage-normalization helpers, likely in a new module such as `econharness/stages.py`
- update [README.md](/Users/halidaee/Documents/GitHub/econharness/README.md)
- update [scoring.py](/Users/halidaee/Documents/GitHub/econharness/econharness/scoring.py) to add `version_control_discipline`

Tests:

- add `tests/test_config_schema.py`
- verify `default_config()` includes `stages: []`
- verify legacy `pipeline.heavy_stages` is normalized into stage objects
- verify `render_default_config()` emits the new shape
- add a CLI `init` test that checks the written file contains `stages`

Verification:

```bash
python3 -m unittest tests.test_config_schema -q
python3 -m unittest tests.test_cli -q
python3 -m unittest -q
```

Commit:

- `feat: add unified stage config schema`

Exit criteria:

- no detector behavior changes yet
- schema exists, tests pass, README prompt updated

### Milestone 2. Static Version-Control Discipline Detector

Goal:

- detect filename-based manual versioning and duplicate-version file clusters

Code changes:

- add a module such as `econharness/version_control.py`
- add a detector wrapper in [detectors.py](/Users/halidaee/Documents/GitHub/econharness/econharness/detectors.py)
- wire it through [scanner.py](/Users/halidaee/Documents/GitHub/econharness/econharness/scanner.py)

Detection scope:

- filenames containing `final`, `new`, `old`, `copy`, `rev`, `v2`, `v3`, date suffixes, or initials
- near-duplicate siblings such as `clean_data.R`, `clean_data_v2.R`, `clean_data_final.R`

Guardrails:

- do not flag raw archival files by default
- do not flag paper drafts unless they live in code or output paths
- keep severity low unless there are repeated patterns

Tests:

- add `tests/test_version_control.py`
- positive cases for manual-versioned code files
- positive cases for duplicate sibling variants
- negative cases for legitimate raw archives and paper drafts

Verification:

```bash
python3 -m unittest tests.test_version_control -q
python3 -m unittest -q
python3 -m econharness scan --path tests/fixtures/bad_project
```

Optional calibration:

- run a scan on `/Users/halidaee/apli` and review any filename findings manually before committing

Commit:

- `feat: detect manual filename versioning`

Exit criteria:

- static versioning findings appear in scan output
- no obvious false positives on the smoke repo

### Milestone 3. Narrow Self-Documenting-Code Checks

Goal:

- add low-noise clarity checks for vague filenames and vague reusable function names

Code changes:

- add a module such as `econharness/self_documenting.py`
- emit findings under `self_documenting_clarity`

Detection scope:

- vague filenames like `tmp`, `script2`, `analysis_new`, `final_final`
- vague function names like `helper`, `run`, `foo`, `bar`, `temp_func`
- only flag function names that look reusable or top-level, not every short local helper inside a test

Guardrails:

- ignore conventional entrypoint names like `main`
- ignore obvious test helpers under test files
- keep findings low-severity by default

Tests:

- add `tests/test_self_documenting_clarity.py`
- positive filename cases
- positive reusable-function-name cases in Python and R
- negative cases for conventional CLI entrypoints and test helpers

Verification:

```bash
python3 -m unittest tests.test_self_documenting_clarity -q
python3 -m unittest -q
```

Commit:

- `feat: add naming clarity detectors`

Exit criteria:

- `self_documenting_clarity` is now populated by real findings

### Milestone 4. Strong Hidden-Global-Write Detection

Goal:

- catch the highest-confidence hidden-state patterns first

Code changes:

- add a module such as `econharness/function_state.py`
- implement language-specific detection for:
  - Python `global`
  - writes to module-level mutable containers from inside functions
  - R `<<-`
  - `assign(..., envir = .GlobalEnv)`
  - explicit `.GlobalEnv` writes

Guardrails:

- only flag writes from inside functions
- do not flag simple module-level constant declarations

Tests:

- add `tests/test_function_state.py`
- positive Python global-write cases
- positive R global-write cases
- negative cases for local mutation within function scope

Verification:

```bash
python3 -m unittest tests.test_function_state -q
python3 -m unittest -q
```

Commit:

- `feat: detect hidden global writes`

Exit criteria:

- strong hidden-state writes are caught with low ambiguity

### Milestone 5. Soft Outer-Scope Dependency Detection

Goal:

- flag functions that silently depend on names from outer scope

Code changes:

- extend `econharness/function_state.py`
- for Python, use `ast` to collect free variables per function
- for R, use a conservative token-based detector for names used inside function bodies that are not parameters or local assignments

Severity policy:

- low severity only
- detail should say "depends on outer scope" rather than claiming the function is wrong

Guardrails:

- allow common imported names and known builtins
- ignore all-uppercase config constants if needed behind a small allowlist
- avoid scoring test files aggressively

Tests:

- positive cases for hidden outer-scope dependencies
- negative cases where the dependency is passed explicitly
- negative cases for imported modules and builtins

Verification:

```bash
python3 -m unittest tests.test_function_state -q
python3 -m unittest -q
```

Optional calibration:

- run on `/Users/halidaee/apli` and inspect whether config-heavy scripts are being over-flagged

Commit:

- `feat: flag outer-scope function dependencies`

Exit criteria:

- soft dependency findings appear without flooding the smoke repo

### Milestone 6. Test Command And Test Presence

Goal:

- reward projects that automate correctness checks

Code changes:

- extend [config.py](/Users/halidaee/Documents/GitHub/econharness/econharness/config.py) so `pipeline.command.tests` exists by default
- add a detector in [detectors.py](/Users/halidaee/Documents/GitHub/econharness/econharness/detectors.py) or a dedicated module such as `econharness/tests_presence.py`

Detection scope:

- missing `pipeline.command.tests`
- no conventional test files/directories despite reusable helper-heavy code
- optionally lighter findings when test files exist but no explicit test command is configured

Guardrails:

- do not punish tiny single-script repos as harshly as multi-module projects
- use helper-density or module-count thresholds before warning

Tests:

- add `tests/test_tests_presence.py`
- positive case: helper-heavy project with no tests
- positive case: test files present but no test command
- negative case: declared test command and test directory

Verification:

```bash
python3 -m unittest tests.test_tests_presence -q
python3 -m unittest tests.test_cli -q
python3 -m unittest -q
```

Commit:

- `feat: add test command and presence checks`

Exit criteria:

- test automation is visible in scoring and scan results

### Milestone 7. Stage Contract Enforcement

Goal:

- make stage boundaries enforceable through config-backed read/write rules

Code changes:

- add a module such as `econharness/path_usage.py` for extracting explicit path reads and writes from Python and R
- add a module such as `econharness/stage_contracts.py` for:
  - matching files to stages
  - checking extracted reads against `read_roots`
  - checking extracted writes against `write_roots`
- wire findings through [detectors.py](/Users/halidaee/Documents/GitHub/econharness/econharness/detectors.py)

Detection scope:

- explicit path reads outside allowed roots
- writes outside allowed roots
- unmatched code files when stage contracts are enabled

Guardrails:

- start with explicit literal paths only
- do not attempt semantic path reconstruction in v1
- report the referenced path and stage name in every finding

Tests:

- add `tests/test_stage_contracts.py`
- positive read violation case
- positive write violation case
- positive unmatched-file case when stage contracts are enabled
- negative cases for compliant reads and writes
- negative cases for repos with no configured stages

Verification:

```bash
python3 -m unittest tests.test_stage_contracts -q
python3 -m unittest -q
python3 -m econharness scan --path tests/fixtures/good_project
```

Optional calibration:

- create a small temporary project with two stages and deliberately cross-wire one read and one write
- after targeted tests pass, run a smoke scan on `/Users/halidaee/apli` only if a draft stage config is available

Commit:

- `feat: enforce stage read and write contracts`

Exit criteria:

- stage contract findings are precise on explicit path usage

### Milestone 8. Quarantined From-Scratch Verification And Clean-Tree Check

Goal:

- extend `verify` so it can test rebuild integrity without deleting artifacts
- add the dynamic half of version-control discipline by checking whether a verification run leaves the tree unstable

Code changes:

- extend [verify.py](/Users/halidaee/Documents/GitHub/econharness/econharness/verify.py)
- extend [cli.py](/Users/halidaee/Documents/GitHub/econharness/econharness/cli.py)
- likely add a helper module such as `econharness/quarantine.py`
- extend `VerifyResult` to include metadata such as:
  - `from_scratch`
  - `quarantine_dir`
  - `moved_paths`
  - `regenerated_paths`
  - `clean_tree_before`
  - `clean_tree_after`

CLI shape:

- `econharness verify --path . --profile full --from-scratch`
- `econharness verify --path . --profile full --check-clean-tree`

Behavior:

- move generated artifacts from configured generated roots into quarantine
- run the configured command
- compare generated outputs before and after
- report whether the worktree was clean before and after the run

Guardrails:

- refuse to touch raw-data roots
- create quarantine directories under `.econharness/`
- if quarantine fails midway, abort before running the build

Tests:

- add `tests/test_verify.py`
- positive from-scratch rebuild case using a temporary project and a tiny fake build script
- failure case where expected outputs do not regenerate
- clean-tree check case where the build modifies a tracked file
- CLI coverage in [tests/test_cli.py](/Users/halidaee/Documents/GitHub/econharness/tests/test_cli.py)

Verification:

```bash
python3 -m unittest tests.test_verify -q
python3 -m unittest tests.test_cli -q
python3 -m unittest -q
```

Optional manual smoke:

- run `econharness verify --path <temp-project> --profile full --from-scratch`
- inspect the quarantine directory contents directly

Commit:

- `feat: add quarantined from-scratch verification`

Exit criteria:

- from-scratch verify works on temp fixtures
- clean-tree reporting is visible in CLI output

### Milestone 9. Slow-Stage Discipline

Goal:

- enforce pure-config declarations for computationally expensive stages

Code changes:

- extend `econharness/stages.py` and/or add `econharness/slow_stages.py`
- add detector logic under `automation_and_one_command_rebuild`

Detection scope:

- slow stage declared but no `pipeline.command.fast`
- slow stage declared but no stage outputs
- slow stages with commands but no reusable artifact roots
- fast verification path that appears to be identical to full path despite slow-stage config

Guardrails:

- do not guess slow stages from heuristics
- only emit these findings when stage config exists

Tests:

- add `tests/test_slow_stages.py`
- positive case: slow stage with no fast path
- positive case: slow stage with no outputs
- negative case: well-configured fast/full split
- config backward-compat test if legacy heavy-stage config is still supported

Verification:

```bash
python3 -m unittest tests.test_slow_stages -q
python3 -m unittest -q
```

Commit:

- `feat: add slow-stage discipline checks`

Exit criteria:

- stage config can now express computationally expensive work
- scan output nudges projects to preserve reusable outputs and a real fast path

### Milestone 10. Integration Sweep And Score Calibration

Goal:

- verify that the full feature set works together and does not overfire

Scope:

- no new feature ideas here
- only integration fixes, score tuning, README cleanup, and test hardening

Work items:

- add one or two composite fixtures that combine multiple new features
- review score impacts across the new dimensions and detectors
- update README examples and prompt text so they reflect the final schema and CLI options
- update any outdated version strings in docs if touched

Verification:

```bash
python3 -m unittest -q
python3 -m econharness scan --path tests/fixtures/good_project
python3 -m econharness scan --path tests/fixtures/bad_project
python3 -m econharness verify --path <temp-project> --profile full --from-scratch
```

Recommended smoke calibration:

- run a scan on `/Users/halidaee/apli`
- compare the new findings against manual judgment
- if any detector is too eager, adjust before the final commit

Commit:

- `chore: calibrate new project-discipline detectors`

Exit criteria:

- full suite green
- docs consistent with implementation
- at least one real-repo smoke pass reviewed manually

## File-By-File Expected Impact

Core files likely to change:

- [config.py](/Users/halidaee/Documents/GitHub/econharness/econharness/config.py)
- [detectors.py](/Users/halidaee/Documents/GitHub/econharness/econharness/detectors.py)
- [scanner.py](/Users/halidaee/Documents/GitHub/econharness/econharness/scanner.py)
- [verify.py](/Users/halidaee/Documents/GitHub/econharness/econharness/verify.py)
- [cli.py](/Users/halidaee/Documents/GitHub/econharness/econharness/cli.py)
- [models.py](/Users/halidaee/Documents/GitHub/econharness/econharness/models.py)
- [scoring.py](/Users/halidaee/Documents/GitHub/econharness/econharness/scoring.py)
- [README.md](/Users/halidaee/Documents/GitHub/econharness/README.md)

Likely new modules:

- `econharness/stages.py`
- `econharness/version_control.py`
- `econharness/self_documenting.py`
- `econharness/function_state.py`
- `econharness/path_usage.py`
- `econharness/stage_contracts.py`
- `econharness/quarantine.py`
- `econharness/tests_presence.py`
- `econharness/slow_stages.py`

Likely new tests:

- `tests/test_config_schema.py`
- `tests/test_version_control.py`
- `tests/test_self_documenting_clarity.py`
- `tests/test_function_state.py`
- `tests/test_stage_contracts.py`
- `tests/test_verify.py`
- `tests/test_tests_presence.py`
- `tests/test_slow_stages.py`

## Execution Rules While Implementing

- Do not combine milestones in one commit just because the code overlaps.
- If a milestone exposes architectural problems, fix them inside the same milestone only if they are required for that feature to land cleanly.
- Keep temporary compatibility shims small and remove them in a later planned milestone if they become dead weight.
- When a detector is added, calibrate it on both synthetic fixtures and at least one real project before declaring it done.
- Do not implement the deferred relational-data and guard-detection work opportunistically during these milestones.
