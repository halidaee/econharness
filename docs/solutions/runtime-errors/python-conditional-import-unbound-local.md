---
name: Python conditional import causes UnboundLocalError across function
description: Adding a local import inside one branch of a function makes that name local to the entire function, causing UnboundLocalError in unrelated branches that previously worked
type: runtime-errors
tags: [python, scoping, imports, unbound-local, cli]
date: 2026-03-21
---

# Python Conditional Import Causes UnboundLocalError Across Function

## Problem Symptom

Running a CLI subcommand (`status`, `scorecard`) that previously worked raises:

```
UnboundLocalError: local variable 'load_state' referenced before assignment
```

The error appears in a branch of `main()` that is completely unrelated to any recent change.

## Investigation Steps Tried

- Checked for syntax errors in the affected branch — none found
- Read the `status` branch line by line — the call to `load_state` looked correct
- Searched for import of `load_state` — found it at module level, appeared fine

## Root Cause

Python compiles the entire function body at once to determine which names are local vs. global. If **any** `from module import name` or `name = ...` assignment appears **anywhere** in the function body — even inside an `if` branch that never executes for this code path — Python marks `name` as a local variable for the **entire function**.

In `cli.py`, adding a local import inside the `suppress` branch:

```python
if args.command == "suppress":
    from econharness.state import load_state  # ← makes load_state LOCAL for all of main()
    ...
```

…caused every other branch that used `load_state` (imported at module level) to fail with `UnboundLocalError`, because Python now expected to find a local binding that never occurred in those branches.

## Working Solution

**Remove the local import.** The module-level import is sufficient and correct. Local imports inside `if` branches only work safely when the name is **not** imported anywhere else in the same function scope.

```python
# ❌ Wrong — creates local scope collision with module-level import
if args.command == "suppress":
    from econharness.state import load_state
    state = load_state(project_root)

# ✅ Correct — rely on the module-level import
# (at top of cli.py)
from econharness.state import load_state
...
if args.command == "suppress":
    state = load_state(project_root)
```

If the import is only needed in one branch and does not exist at module level, the local import is fine — but it must not duplicate a module-level name.

## Prevention

- **Never add a local `from module import name` inside a function branch when `name` is already imported at module or function scope.** Python's scoping rules are function-wide, not block-wide.
- When adding new functionality to a large dispatch function (`main()`, `dispatch()`), add any new imports at the **top of the file** (or top of the function, before the if-chain), not inside the new branch.
- The error appears in the **unrelated** branch, not the branch with the local import — making it extremely confusing. If you see `UnboundLocalError` on a line that looks fine, search the entire function for any other binding of that name.

## Test Case Pattern

```python
def test_status_still_works_after_suppress_added():
    """Regression: adding suppress branch must not break status branch."""
    result = run("status", "--path", tmpdir)
    assert result.returncode == 0  # Would fail with UnboundLocalError before fix
```
