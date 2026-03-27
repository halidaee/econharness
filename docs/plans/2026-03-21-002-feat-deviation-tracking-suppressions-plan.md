---
title: "feat: Add finding suppression with expiry for deviation tracking"
type: feat
status: completed
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-deviation-tracking-requirements.md
---

# feat: Finding Suppression with Expiry (Deviation Tracking)

## Overview

`econharness next` permanently recycles false positives and legitimate deviations, stalling
agent repair loops. This feature lets agents and researchers suppress specific findings by ID
with an optional reason and expiry date. Suppressed findings are excluded from `next`,
excluded from scoring, and tracked separately so the intent is visible.

## Problem Statement / Motivation

Without suppression, any finding the agent decides not to fix (false positive, principled
deviation, out-of-scope item) permanently appears at the top of `next`. The repair loop
stalls. Researchers also need a way to document *why* they deviate (e.g. "no lockfile —
raw data is proprietary") without the tool treating it as an open violation.

## Proposed Solution

Add a `suppressions.json` file alongside `state.json` in `.econharness/`. Suppressions
survive rescans because they are stored independently. `findings_from_state` and
`scan_result_from_state` filter active suppressions at read time, so scores reflect only
genuine open violations.

A new `suppress` CLI command manages the suppressions file.

## Technical Considerations

### Finding ID Stability
Finding IDs are deterministic: `{dimension}:{title-slug}:{path_or_"project"}` generated
in `detectors.py:make_finding` (line 117–119). The same logical finding produces the same
ID on every rescan, making ID-based suppression stable.

### Storage: Separate `suppressions.json`
`save_scan_result` in `state.py:21` overwrites `state.json` entirely on every scan.
Suppressions **must not** live in `state.json` — they would be wiped on every scan.
They live in `.econharness/suppressions.json` as a dict keyed by finding ID.

### Score Recalculation at Read Time
The scan always produces a complete `ScanResult` with all findings and full scores.
Suppression filtering happens at read time in `findings_from_state` and
`scan_result_from_state`. The score shown to the user is recomputed from the
non-suppressed findings. This requires calling scoring logic at read time, not just
at scan time.

### Expiry Storage
`--expires 90d` is parsed as a duration at command time and stored as an absolute ISO 8601
date (`"expires": "2026-06-19"`). No duration strings in the file.

## System-Wide Impact

- **`findings_from_state` (state.py:41)**: Must load suppressions and filter before
  returning. All callers (`next`, `status`, scan delta) automatically get filtered results.
- **`scan_result_from_state` (state.py:51)**: Must rebuild scores after filtering suppressed
  findings. Requires calling `score_findings` (or equivalent) from `scoring.py`.
- **`scan` output**: The scan prose/JSON output should show suppressed count
  ("Suppressed findings: N (not counted in score)") so the user knows the score excludes them.
- **`--json` flag**: All `suppress` subcommands support `--json` consistent with the
  agent JSON output feature (plan 001).

## Acceptance Criteria

- [ ] `econharness suppress <finding-id> [--path .] [--reason "..."] [--expires 90d]`
  writes a suppression entry to `.econharness/suppressions.json`. Exits with helpful error
  if the finding ID is not found in the current state.
- [ ] `econharness suppress --list [--path .]` prints all suppressions with: ID, reason
  (if set), expiry date (if set), status (`active` / `expired`).
- [ ] `econharness suppress --remove <finding-id> [--path .]` removes a suppression entry.
- [ ] Suppressions survive `econharness scan` — rescan does not clear suppressions.
- [ ] `econharness next` never returns a finding with an active (non-expired) suppression.
- [ ] `econharness status` score and `econharness scan` score exclude suppressed findings.
- [ ] `scan` and `status` prose output includes: `Suppressed findings: N (not counted in score)`
  when N > 0.
- [ ] Expired suppressions appear in `--list` with status `expired` and are treated as
  unsuppressed — the finding reappears in `next` and in scoring automatically.
- [ ] `--expires 90d` is the supported duration format. Stored as an absolute ISO 8601 date.
  `1y` and `30d` also supported. Stored at time of suppression creation.
- [ ] `suppress`, `--list`, `--remove` all support `--json` returning structured objects.
- [ ] If finding ID does not exist in current state when suppressing, print a warning but
  still write the suppression (the finding may appear after next scan).
- [ ] Tests cover: add suppression, list suppressions, remove suppression, rescan survival,
  score exclusion, expiry behavior.

## Dependencies & Risks

- **Depends on plan 001 (agent JSON output)** for the `--json` flag interface convention.
  Can be implemented independently but `--json` on suppress commands should follow the same
  pattern.
- **Finding ID stability**: Confirmed deterministic. Risk: if a future detector renames a
  finding's title, suppressions become orphaned. Orphaned suppressions are harmless (they
  filter a finding that no longer exists) but may accumulate silently. `--list` will show
  them as active suppressions for unknown IDs.
- **Score recalculation at read time**: `scan_result_from_state` currently just sums
  persisted scores. After this change, it must recompute scores from filtered findings.
  Verify `scoring.py` exposes a function callable with a `list[Finding]` without needing
  a full rescan.

## Implementation Notes

### New file: `econharness/suppressions.py`
Handles load/save/filter for suppressions. Format:
```json
{
  "automation:no-fast-rebuild-command-declared:project": {
    "reason": "manual pipeline is intentional for this project",
    "expires": "2026-06-19",
    "suppressed_at": "2026-03-21"
  }
}
```

### Modified files
- `econharness/state.py` — `findings_from_state` and `scan_result_from_state` load
  suppressions and filter before returning; recompute scores from filtered findings
- `econharness/cli.py` — new `suppress` command with `--list`, `--remove` subactions;
  add `--json` support; update `scan`/`status` output to show suppressed count
- `tests/test_suppressions.py` (new) — full test coverage for suppression lifecycle

### Duration parsing
Parse `90d`, `30d`, `1y` → compute absolute date using `datetime.date.today() + timedelta`.
`1y` = 365 days. Store as `YYYY-MM-DD` string.

### CLI interface for `suppress`
```
econharness suppress <finding-id>            # add suppression (no expiry, no reason)
econharness suppress <finding-id> --reason "..." --expires 90d
econharness suppress --list
econharness suppress --remove <finding-id>
```
All with optional `--path .` and `--json`.

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-deviation-tracking-requirements.md](../brainstorms/2026-03-21-deviation-tracking-requirements.md)
  — Key decisions: suppressions excluded from score; duration-based expiry stored as ISO date;
  expired suppressions reappear in `next` automatically; suppressions survive rescan.
- `econharness/detectors.py:107-129` — `make_finding`, ID generation pattern
- `econharness/state.py:21-31` — `save_scan_result` overwrites state.json (why separate file)
- `econharness/state.py:41-58` — `findings_from_state`, `scan_result_from_state` (filter hooks)
- `econharness/scoring.py` — score computation (verify callable with `list[Finding]`)
