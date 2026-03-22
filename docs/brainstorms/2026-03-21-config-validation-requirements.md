---
date: 2026-03-21
topic: config-validation
---

# Config Validation / Lint Command

## Problem Frame

`load_config` silently merges any malformed `.econharness.yml` with defaults. If a field has
the wrong type, a stage `match` pattern is an invalid regex, or a required section is missing,
the tool proceeds silently — producing zero findings or wrong findings with no explanation.
An agent cannot distinguish "this project is clean" from "your config is broken and nothing ran."
A `check-config` command and scan-time validation close this reliability gap.

## Requirements

- R1. A new `econharness check-config [--path .]` command parses and validates
  `.econharness.yml`. It prints each validation error found and exits non-zero if any errors
  exist. It prints "Config OK" and exits zero if no errors are found.
- R2. Validation covers:
  - Parse errors: invalid JSON or YAML syntax
  - Type errors: fields that exist but have the wrong type (e.g. `stages` is a string instead
    of a list; `pipeline.command.fast` is a list instead of a string)
  - Invalid stage `match` patterns: any pattern that is not a valid Python regex
  - Unknown top-level keys not in the known schema (warning, not error — exits zero)
- R3. Each validation error message identifies the offending field and the problem:
  e.g. `Error: stages[0].match — invalid regex: unterminated character set at position 4`
- R4. `scan` runs config validation before scanning. If validation finds any **errors** (not
  warnings), `scan` exits with a distinct error message:
  `Config error: fix .econharness.yml before scanning (run econharness check-config for details)`
  and exits non-zero. It does not fall back to defaults silently.
- R5. `check-config --json` emits structured output:
  `{"valid": false, "errors": [...], "warnings": [...]}` consistent with the agent JSON output
  feature.
- R6. If `.econharness.yml` does not exist, `check-config` prints:
  `No config file found. Run econharness init to create one.` and exits non-zero.

## Success Criteria

- An agent that generates a bad `.econharness.yml` (invalid regex in a stage match) sees a
  clear error from `scan` rather than a clean-looking scan with no findings.
- `check-config` exits zero on a valid config and non-zero on any error.
- `check-config --json` is parseable by an agent for automated config repair loops.

## Scope Boundaries

- Validation is schema-level only: field types, regex validity, known keys. No semantic
  validation (e.g. "do these paths actually exist") — that is what `scan` is for.
- Unknown keys are warnings (not errors) to allow forward-compatibility with future config fields.
- No auto-fix or suggestion of correct values.

## Key Decisions

- **Errors block scan, warnings do not**: Type errors and invalid regexes produce broken
  behavior; unknown keys are forward-compatible noise. The distinction matters for agent loops.
- **Distinct exit message on scan**: Silent fallback to defaults was the original bug.
  An explicit error message that names `check-config` teaches users what to do next.

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Needs research] What is the full set of typed fields in the config schema?
  Enumerate from `DEFAULT_CONFIG` in config.py and `normalize_stages` in stages.py.
- [Affects R2][Technical] Where are stage `match` patterns compiled? Confirm they are Python
  `re` patterns in stages.py so validation can use `re.compile()` to test them.

## Next Steps
→ `/ce:plan` for structured implementation planning
