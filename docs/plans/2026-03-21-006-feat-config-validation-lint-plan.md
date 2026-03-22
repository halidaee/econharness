---
title: "feat: Add check-config command and scan-time config validation"
type: feat
status: completed
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-config-validation-requirements.md
---

# feat: Config Validation & `check-config` Command

## Overview

`load_config` silently merges any malformed `.econharness.yml` with defaults. Type errors,
missing required fields, or invalid values produce no warning — the tool proceeds and emits
zero findings or wrong findings with no explanation. An agent cannot distinguish
"this project is clean" from "your config is broken and nothing ran." A `check-config`
command and scan-time validation close this reliability gap.

## Problem Statement / Motivation

The silent-fallback-to-defaults behavior is the root bug. It was a reasonable design choice
for resilience, but it makes config errors invisible — the worst failure mode for agents in
automated repair loops. The fix is explicit: expose a validation layer that surfaces errors
before scan, gives structured output for machine consumption, and teaches users what to do next.

## Proposed Solution

Add a `validate_config(config_path)` function in a new `config_validator.py` module. It
returns `(errors: list[str], warnings: list[str])` from a schema-level check of the loaded
config dict. A new `check-config` CLI command calls this directly. `scan` calls it before
scanning and exits early on errors. Both support `--json` output.

## Technical Considerations

### Schema-Level Validation Only

Validation covers types, required structure, and known keys. It does not check whether paths
exist, whether pipeline commands run, or whether stage names are meaningful. Those are
`scan`'s job. This keeps the validator fast, stdlib-only, and independent of the filesystem.

### Stage `match` Patterns Are fnmatch Globs, Not Regex

**Critical finding from code inspection:** `stage_contracts.py:38` uses
`fnmatch.fnmatch(rel, pattern)` — glob syntax, not `re.compile`. Virtually no string is
an invalid fnmatch pattern (the stdlib `fnmatch` module does not raise on any input).
Therefore R2's "invalid regex" requirement does not apply. The validator instead checks that
each `stages[].match` entry is a `str`, not that it compiles as a regex.

This is a correction to the origin requirements document, which assumed regex validation.
The actual invariant to enforce is: `match` entries must be strings (not ints, bools, lists).

### Typed Fields Enumerated from `DEFAULT_CONFIG`

From `config.py:13-66`:

| Field path | Expected type |
|---|---|
| `pipeline` | dict |
| `pipeline.command` | dict |
| `pipeline.command.fast/full/tests` | str |
| `pipeline.entrypoints` | list |
| `stages` | list |
| `stages[].name` | str |
| `stages[].match` | list of str |
| `stages[].read_roots / write_roots / inputs / outputs` | list of str |
| `stages[].slow` | bool |
| `stages[].command` | str |
| `paths` | dict |
| `paths.raw / derived / analysis / output / paper / temp` | str |
| `datasets` | list |
| `artifacts` | dict |
| `artifacts.tables / figures / paper_files` | list |
| `environment` | dict |
| `environment.r / environment.python` | dict |
| `environment.r.manager / environment.python.manager` | str |
| `environment.r.lockfiles / environment.python.lockfiles` | list |
| `scorecard` | dict |
| `scorecard.generate` | bool |
| `scorecard.svg_path / html_path` | str |
| `conventions` | dict |
| `conventions.authoritative_pipeline / allow_notebooks` | bool |
| `exclude` | list of str |
| `ignore` | list of str |

Known top-level keys: `pipeline`, `stages`, `paths`, `datasets`, `artifacts`, `environment`,
`scorecard`, `conventions`, `exclude`, `ignore`. Any other top-level key is a warning.

### Validation Happens on the Parsed Dict, Not the Raw File

`load_config` already handles parse errors (raises `ValueError` on JSON/YAML parse failure).
The validator receives the **already-parsed dict** from a call to the raw YAML/JSON loader
(not `load_config`, which merges with defaults and would hide missing keys). For `check-config`
specifically, the validator calls the raw loader, catches `ValueError` parse errors, and
reports them as errors before schema checking.

For scan-time validation, `scan` calls `validate_config_path(project_root)` which combines
the parse step and schema check into a single call, returning errors + warnings.

## System-Wide Impact

- **`econharness/config_validator.py`** (new): Core validation logic. Exposed API:
  `validate_config_path(project_root) -> tuple[list[str], list[str]]` — returns
  `(errors, warnings)`. Handles parse failures as the first error class.
- **`econharness/cli.py`**: New `check-config` subparser + dispatch. `scan` branch calls
  `validate_config_path` before `run_scan`; exits with distinct message on any errors.
- **`econharness/scanner.py`**: No change — validation happens in `cli.py` before `run_scan`.
- **`tests/test_config_validator.py`** (new): Tests for all error and warning classes.

## Acceptance Criteria

- [ ] `econharness check-config [--path .]` runs validation on `.econharness.yml`. Prints each
  error and warning found. Exits zero if no errors; exits non-zero if any errors found.
  Warnings do not change the exit code.
- [ ] `econharness check-config` prints `Config OK` and exits zero on a valid config.
- [ ] `econharness check-config` on a missing config file prints:
  `No config file found. Run econharness init to create one.` and exits non-zero.
- [ ] Validation detects parse errors (invalid JSON/YAML) and reports them as errors.
- [ ] Validation detects type errors for all known typed fields (see table above).
  Error format: `Error: <field-path> — expected <type>, got <actual-type>`.
  e.g. `Error: pipeline.command.fast — expected str, got list`
- [ ] Validation detects that each `stages[].match` entry is a str (not a non-string type).
  Error format: `Error: stages[N].match[M] — expected str, got <type>`.
  *(No regex compilation check — match patterns use fnmatch glob, not Python re.)*
- [ ] Unknown top-level keys produce warnings, not errors.
  Warning format: `Warning: unknown top-level key '<key>' — may be a typo`.
- [ ] `check-config --json` emits:
  `{"valid": false, "errors": [...], "warnings": [...]}` (or `"valid": true` with empty lists).
- [ ] `econharness scan` runs config validation before scanning. If any errors are found,
  `scan` exits with:
  `Config error: fix .econharness.yml before scanning (run econharness check-config for details)`
  and exits non-zero. No scan is run. No silent fallback.
- [ ] If config has only warnings (no errors), `scan` proceeds normally (warnings do not block scan).
- [ ] `scan --json` on a config with errors emits `{"error": "Config error: ..."}` and exits
  non-zero (consistent with plan 001 error JSON convention).
- [ ] `render_default_config()` is unchanged.
- [ ] Tests: parse error, type error (each major field group), invalid match entry type,
  unknown top-level key (warning), valid config passes, missing config file,
  scan exits on error, scan proceeds on warning-only config.

## Dependencies & Risks

- **Depends on plan 001 (agent JSON output)** for the `--json` convention on `check-config`.
  Can be implemented independently; just follow the same `{"error": "..."}` pattern.
- **`load_config` merges before returning** — the validator must call the raw loader (not
  `load_config`) to catch missing or mistyped keys before they are silently filled in from
  defaults. Otherwise a type error on `pipeline.command.fast` would be invisible.
- **Parse errors already raise `ValueError` in `load_config`** — the validator's parse step
  catches `ValueError` from the raw YAML/JSON load and reports it as an error string rather
  than propagating the exception.
- **Stage entry normalization in `stages.py`** already coerces any non-dict stage to a dict
  (`normalize_stage_entry`). Type validation must happen on the **raw** loaded dict, before
  `normalize_stages` is called, to catch type violations.

## Implementation Notes

### New module: `config_validator.py`

```python
# econharness/config_validator.py
import json
import re
from pathlib import Path
from typing import Any

KNOWN_TOP_LEVEL_KEYS = {
    "pipeline", "stages", "paths", "datasets", "artifacts",
    "environment", "scorecard", "conventions", "exclude", "ignore",
}

def validate_config_path(project_root: Path) -> tuple[list[str], list[str]]:
    """Parse and validate .econharness.yml. Returns (errors, warnings)."""
    config_path = project_root / ".econharness.yml"
    if not config_path.exists():
        return (["No config file found. Run econharness init to create one."], [])

    text = config_path.read_text(encoding="utf-8").strip()
    if not text:
        return (["Config file is empty."], [])

    try:
        raw = _parse_raw(text, config_path)
    except ValueError as exc:
        return ([f"Parse error: {exc}"], [])

    if not isinstance(raw, dict):
        return (["Config must be a YAML/JSON object at the top level."], [])

    return _validate_dict(raw)

def _parse_raw(text: str, config_path: Path) -> Any:
    # Try JSON first, then YAML
    ...

def _validate_dict(raw: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    # Check unknown top-level keys
    # Check each known section's type
    # Check stages[] entries
    return errors, warnings
```

### Changes to `cli.py`

**`check-config` subcommand:**
```python
# In create_parser():
check_config_parser = subparsers.add_parser("check-config", ...)
check_config_parser.add_argument("--path", default=".", ...)
check_config_parser.add_argument("--json", action="store_true")

# In dispatch:
if args.command == "check-config":
    from econharness.config_validator import validate_config_path
    errors, warnings = validate_config_path(project_root)
    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings}))
    else:
        for e in errors:
            print(f"Error: {e}")
        for w in warnings:
            print(f"Warning: {w}")
        if not errors:
            print("Config OK")
    sys.exit(1 if errors else 0)
```

**`scan` early-exit on config errors:**
```python
if args.command == "scan":
    from econharness.config_validator import validate_config_path
    errors, _warnings = validate_config_path(project_root)
    if errors:
        msg = "Config error: fix .econharness.yml before scanning (run econharness check-config for details)"
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        sys.exit(1)
    # ... proceed with scan as before
```

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-config-validation-requirements.md](../brainstorms/2026-03-21-config-validation-requirements.md)
  — Key decisions: errors block scan, warnings do not; distinct exit message names `check-config`;
  schema-level only (no path existence checks).
- `econharness/config.py:13-66` — `DEFAULT_CONFIG` (typed field enumeration source)
- `econharness/stages.py:18-54` — `normalize_stage_entry` (stage field types; normalization
  happens *after* raw load, so validator must inspect raw dict before normalization)
- `econharness/stage_contracts.py:38` — `fnmatch.fnmatch(rel, pattern)` confirms match patterns
  are glob (not regex) — validator checks str type only, not pattern syntax
- `econharness/config.py:87-107` — `load_config` (merges before returning; validator bypasses
  this to inspect the raw loaded dict)
- `econharness/cli.py` — dispatch logic and `--json` convention (plan 001)
- Plan 001 (`2026-03-21-001`) — `--json` error format convention: `{"error": "..."}`
