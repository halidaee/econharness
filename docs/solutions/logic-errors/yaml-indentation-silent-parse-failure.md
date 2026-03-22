---
name: YAML indentation causes silent nested key parse failure
description: Hand-crafted YAML with wrong indentation levels causes nested keys to parse as siblings, silently returning None for expected nested values
type: logic-errors
tags: [yaml, indentation, config, silent-failure, python]
date: 2026-03-21
---

# YAML Indentation Causes Silent Nested Key Parse Failure

## Problem Symptom

`pipeline.command` returns `None` after calling `load_config()`, even though the config file appears to contain valid `fast`, `full`, and `tests` keys. No parse error or exception is raised.

```python
cfg = load_config(project_root)
print(cfg["pipeline"]["command"])  # → None  (expected dict with fast/full/tests)
```

## Investigation Steps Tried

- Printed the raw loaded dict — confirmed `pipeline.command` was `None`
- Checked that the YAML file existed and was non-empty
- Checked `load_config` for merge bugs — logic looked correct
- Added `print(raw)` before merge — revealed `command` was present but `fast/full/tests` appeared as **top-level keys**, not nested under `command`

## Root Cause

In hand-crafted YAML template strings, indentation level determines nesting. An off-by-one error in the number of leading spaces causes keys that should be **children** of a mapping key to instead be parsed as **siblings** at the parent's level.

The `bootstrap_config()` function built a YAML string with 2-space indent for `fast/full/tests`, making them siblings of `command:` rather than children:

```yaml
# ❌ Wrong — fast/full/tests are siblings of command (both at 2-space indent)
pipeline:
  command:
  fast: "make fast"     ← 2 spaces: sibling of command
  full: "make"          ← 2 spaces: sibling of command
  tests: "make test"    ← 2 spaces: sibling of command
```

YAML parses `command:` as a key with value `None` (no children), and `fast/full/tests` as separate keys under `pipeline`.

## Working Solution

Use 4-space indent (or 2 more than the parent's indent level) for nested keys:

```yaml
# ✅ Correct — fast/full/tests are children of command (4-space indent)
pipeline:
  command:
    fast: "make fast"   ← 4 spaces: child of command
    full: "make"        ← 4 spaces: child of command
    tests: "make test"  ← 4 spaces: child of command
```

In Python string templates:

```python
# ❌ Wrong
fast_line = f'  fast: "{fast_cmd}"'    # 2 spaces

# ✅ Fixed
fast_line = f'    fast: "{fast_cmd}"'  # 4 spaces
```

## Prevention

- **Always validate hand-crafted YAML by round-tripping it**: after generating a YAML string, parse it and assert the nested structure is what you expect before returning it.
- Write a unit test that parses the generated config and asserts `cfg["pipeline"]["command"]["fast"]` is a string — this would have caught the bug immediately.
- Use Python's `yaml.dump()` to generate YAML from a dict rather than crafting template strings manually. The library handles indentation correctly.

```python
# Preferred approach for generated YAML
import yaml

config = {
    "pipeline": {
        "command": {
            "fast": fast_cmd,
            "full": full_cmd,
            "tests": tests_cmd,
        }
    }
}
return yaml.dump(config, default_flow_style=False)
```

## Test Case Pattern

```python
def test_bootstrap_config_pipeline_command_is_dict():
    """Generated config must have pipeline.command as a dict, not None."""
    result = bootstrap_config(project_root)
    cfg = load_config_from_string(result)
    assert isinstance(cfg["pipeline"]["command"], dict)
    assert isinstance(cfg["pipeline"]["command"]["fast"], str)
```
