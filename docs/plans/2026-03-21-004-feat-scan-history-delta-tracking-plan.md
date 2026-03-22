---
title: "feat: Add scan history and delta tracking to show progress between scans"
type: feat
status: completed
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-scan-history-requirements.md
---

# feat: Scan History & Delta Tracking

## Overview

`state.json` is a single-file overwrite — every scan erases prior results. An agent running
multiple repair iterations has no way to confirm progress, detect regressions, or know which
findings it resolved. This feature appends scan snapshots to a history file, computes a delta
after each scan, and exposes it via `scan` output and `status --diff`.

## Problem Statement / Motivation

Without history, a repair loop must externally track whether its changes improved the score.
A delta signal built into `scan` output makes progress visible immediately — new findings,
resolved findings, and score change — without any extra commands. `status --diff` provides
the same signal on demand.

## Proposed Solution

Append each scan result as a JSON line to `.econharness/history.jsonl`. Retain the last 10
snapshots, pruning on overflow. After `save_scan_result`, compute a delta against the previous
snapshot and print/include it in output. Add `status --diff` to expose the delta on demand.

## Technical Considerations

- **Storage: `history.jsonl`** — single newline-delimited JSON file. One line per snapshot.
  Append on scan; rewrite with last 10 lines after each append. Pure stdlib (`json`, file I/O).
  Simpler than individual timestamped files (no directory listing, no file-per-scan clutter).
- **Snapshot structure**: Same shape as `state.json` payload (already written by
  `save_scan_result`) plus `scanned_at` ISO 8601 timestamp. No new serialization needed.
- **Delta computation**: Compare current snapshot against snapshot at index -2 (second-to-last)
  after appending. Finding identity by `id` field (confirmed deterministic:
  `dimension:title-slug:path`). Resolved = ID in previous but not current. New = ID in
  current but not previous.
- **`--json` integration**: When `scan --json` or `status --json --diff` is used, delta is
  included as a nested object in the JSON output (see plan 001 for `--json` convention).

## System-Wide Impact

- **`save_scan_result` (state.py:21)**: Gains a sibling call to `append_scan_history` after
  writing state. History append always happens; delta is computed as a return value or
  side-read of the history file.
- **`scan` command (cli.py)**: After `save_scan_result`, reads the two most recent history
  snapshots and prints delta if both exist. No change to existing scan output — delta is
  appended after.
- **`status --diff` (cli.py)**: New flag on `status` subparser. Reads history, computes
  delta from last two snapshots. Errors gracefully if fewer than 2 exist.
- **`--json` flag (plan 001 dependency)**: `scan --json` output gains a `"delta"` key.
  `status --json --diff` output is the delta object directly.
- **State lifecycle**: `history.jsonl` is append-only (except pruning). A corrupted line
  does not break scans — history read is best-effort; parse errors on individual lines are
  skipped silently.

## Acceptance Criteria

- [ ] Every `scan` appends the current result as a JSON line to `.econharness/history.jsonl`
  with a `scanned_at` ISO 8601 timestamp.
- [ ] After appending, history is pruned to the last 10 snapshots. Pruning rewrites the file
  in place.
- [ ] After the second scan onwards, `scan` prose output includes a delta section:
  `Score: 72.3 → 74.1 (+1.8)`, per-dimension changes (changed dimensions only), new finding
  titles, resolved finding titles.
- [ ] If this is the first scan (no prior snapshot), the delta section is omitted from output.
- [ ] `econharness status --diff` prints the same delta as the second scan, computed from
  the two most recent history snapshots. If fewer than 2 snapshots exist, prints:
  `Not enough scan history for a diff. Run scan at least twice.`
- [ ] `scan --json` output includes a `"delta"` key: `{"score_delta": 1.8,
  "dimension_deltas": {"automation": 2.1, ...}, "new_findings": [...], "resolved_findings": [...]}`.
  `"delta"` is `null` on the first scan.
- [ ] `status --json --diff` emits the delta object directly as the top-level JSON output.
- [ ] Finding identity for delta uses `id` field. Resolved = ID absent from current scan.
  New = ID absent from previous scan.
- [ ] History survives rescan — appending does not truncate prior entries (only prunes oldest
  beyond 10).
- [ ] Tests: first scan (no delta), second scan (delta shown), pruning at 11th scan,
  `status --diff`, `--json` delta structure, corrupted line in history.jsonl is skipped.

## Dependencies & Risks

- **Depends on plan 001 (agent JSON output)** for `--json` flag availability on `scan` and
  `status`. The `"delta"` key is an addition to the plan 001 JSON shape.
- **Finding ID stability**: Confirmed deterministic. Shared dependency with plan 002
  (deviation tracking) — same note applies: title renames orphan history-based identity.
- **Pruning correctness**: Pruning rewrites the file. If a scan crashes between append and
  prune, the file may exceed 10 lines until the next scan. Acceptable — next scan will prune.

## Implementation Notes

### New module: `econharness/history.py`
```python
# history.py
def history_path(project_root: Path) -> Path: ...
def append_history(project_root: Path, snapshot: dict) -> None:
    # append line, prune to last 10, rewrite
def load_history(project_root: Path) -> list[dict]:
    # read all lines, skip malformed, return list newest-last
def compute_delta(previous: dict, current: dict) -> dict:
    # returns {score_delta, dimension_deltas, new_findings, resolved_findings}
```

### Changes to `state.py`
- `save_scan_result` calls `append_history(project_root, payload)` after writing state.json.
  The payload is the same dict already constructed (add `scanned_at` timestamp).

### Changes to `cli.py`
- After `save_scan_result` in the `scan` branch: load history, compute delta if len >= 2,
  print delta (prose) or include in JSON output.
- Add `--diff` flag to `status` subparser. In `status` branch: if `args.diff`, load history,
  compute delta, print/emit.

### Delta prose format
```
Delta since last scan:
  Score: 72.3 → 74.1 (+1.8)
  automation: 65.0 → 72.1 (+7.1)
  Resolved: no-fast-rebuild-command-declared, missing-renv-lock
  New:      oversized-script-analysis-run-r
```

### `history.jsonl` snapshot shape
```json
{"scanned_at": "2026-03-21T10:05:00", "project_root": "...", "overall_score": 74.1, "dimension_scores": {...}, "findings": [{"id": "...", ...}, ...], "summary": {...}}
```

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-scan-history-requirements.md](../brainstorms/2026-03-21-scan-history-requirements.md)
  — Key decisions: previous-scan-only delta; auto-print delta on scan; last 10 retention;
  ID-based finding identity.
- `econharness/state.py:21-31` — `save_scan_result`, payload construction (model for history snapshot)
- `econharness/cli.py:20-55` — scan and status dispatch (integration points)
- `econharness/detectors.py:117-119` — finding ID generation (identity basis for delta)
- Plan 001 (`2026-03-21-001`) — `--json` flag interface that `scan --json` and `status --json` depend on
