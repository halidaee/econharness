---
name: shutil.copytree fixture state pollution in history tests
description: Copying project fixtures with shutil.copytree carries accumulated .econharness/history.jsonl state into tests, causing non-deterministic failures in tests that expect a clean history
type: test-failures
tags: [testing, fixtures, state-pollution, history, copytree, non-deterministic]
date: 2026-03-21
---

# `shutil.copytree` Fixture State Pollution in History Tests

## Problem Symptom

Tests that assert `len(history) == 1` or `"Not enough scan history"` fail non-deterministically. On a fresh clone they pass; after several test runs locally they fail because history now contains 7+ entries.

```
AssertionError: 7 != 1
# or
AssertionError: "Not enough scan history" not in stdout
```

## Investigation Steps Tried

- Checked test isolation — each test uses `tempfile.TemporaryDirectory()`
- Confirmed the scan correctly appends to history
- Added print of history length — showed 7+ entries on first scan in the test
- Discovered that `.econharness/history.jsonl` existed **before** the first scan in the test

## Root Cause

`shutil.copytree(FIXTURES / "good_project", tmpdir)` copies the **entire fixture directory**, including any `.econharness/` subdirectory that accumulated in the fixture from previous test runs. If `tests/fixtures/good_project/.econharness/history.jsonl` exists (written by a prior run), the "fresh" tmpdir already has 6 history entries before the first test scan.

The fixture directory lives in the repo and is modified in place by tests that use `copytree` into it. This creates a feedback loop: each test run adds entries to the fixture's history file.

## Working Solution

For tests that care about history state, **do not copy the fixture directory**. Instead, create a minimal config in a fresh `tempfile.TemporaryDirectory()`:

```python
def _fresh_project(self) -> str:
    """Create a fresh project dir with a minimal valid config. Returns tmpdir path."""
    tmpdir = tempfile.mkdtemp()
    cfg = default_config()
    cfg["pipeline"]["command"]["fast"] = "echo ok"
    cfg["pipeline"]["command"]["full"] = "echo ok"
    (Path(tmpdir) / ".econharness.yml").write_text(json.dumps(cfg), encoding="utf-8")
    return tmpdir
```

This gives a directory with:
- A valid config file (so scan proceeds)
- No `.econharness/` directory (so history starts empty)
- No inherited fixture state of any kind

## Prevention

- **Never use `shutil.copytree` on fixture directories for tests that check scan-derived state** (history, state.json, suppressions). The fixture accumulates state across runs.
- Use fixture directories **read-only** for reference data (expected findings, input file content). Use `tempfile.TemporaryDirectory()` as the project root where the tool writes state.
- For integration tests that need a project with specific files: copy only the files needed (not `copytree`), or use `dirs_exist_ok=True` to a fresh tmpdir and immediately delete any `.econharness/` subdirectory after copying.
- Add `.econharness/` to the fixture's `.gitignore` to prevent accidental commitment of accumulated state.

## Test Case Pattern

```python
# ❌ Fragile — inherits .econharness/ state from fixture
def test_history(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copytree(FIXTURES / "good_project", tmpdir, dirs_exist_ok=True)
        self._run("scan", "--path", tmpdir)
        history = load_history(Path(tmpdir))
        self.assertEqual(len(history), 1)  # Fails if fixture has history

# ✅ Robust — always starts with clean state
def test_history(self):
    tmpdir = self._fresh_project()  # minimal config, no .econharness/
    self._run("scan", "--path", tmpdir)
    history = load_history(Path(tmpdir))
    self.assertEqual(len(history), 1)  # Always correct
```
