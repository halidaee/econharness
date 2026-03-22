---
date: 2026-03-21
topic: deviation-tracking
---

# First-Class Deviation Tracking

## Problem Frame

`econharness next` always returns the highest-priority open finding. When a finding is a false
positive or a deliberate, principled deviation (e.g. no lockfile because raw data is proprietary),
it permanently pollutes the repair loop — the same finding appears on every `next` call, stalling
progress. There is no way to say "we know about this and accept it."

Suppressions let agents and researchers mark specific findings as acknowledged, with an optional
reason and expiry date. Suppressed findings are excluded from `next` output and from scoring until
they expire or are removed.

## Requirements

- R1. A new `suppress` command allows adding a suppression for a finding by ID:
  `econharness suppress <finding-id> [--path .] [--reason "..."] [--expires 90d]`.
  `--reason` and `--expires` are optional.
- R2. Suppressions persist independently of scan results — a rescan does not remove or overwrite
  existing suppressions.
- R3. `findings_from_state` (used by `next` and `status`) filters out findings whose IDs have
  an active (non-expired) suppression. Active means: no expiry set, or expiry date is today
  or later.
- R4. Suppressed findings are excluded from dimension score calculation and overall score.
  The score reflects only genuine open violations.
- R5. When `scan` or `status` output includes suppressed findings, the prose and JSON output
  includes a suppression note: e.g. `Suppressed findings: 3 (not counted in score)`.
- R6. `econharness suppress --list [--path .]` prints all suppressions with: finding ID,
  reason (if set), expiry date (if set), and status (active / expired).
- R7. `econharness suppress --remove <finding-id> [--path .]` removes a suppression, restoring
  the finding to the active pool.
- R8. Expired suppressions are not automatically deleted — they remain visible in `--list` with
  status `expired` and can be removed or renewed. An expired suppression is treated as no
  suppression: the finding reappears in `next` and in scoring.
- R9. `--expires` accepts a duration string (`90d`, `30d`, `1y`). It is stored internally as an
  absolute ISO 8601 date (computed at time of suppression creation).
- R10. `suppress`, `--list`, and `--remove` all support `--json` consistent with R1–R4 of the
  agent JSON output feature (findings listed as objects, suppressions listed as objects).

## Success Criteria

- An agent can suppress a false-positive finding by ID, and subsequent `next` calls never return
  it again until the suppression expires or is removed.
- A rescan does not clear suppressions.
- `econharness suppress --list` gives a complete picture of all acknowledged deviations, their
  reasons, and their status.
- Suppressed findings do not inflate or deflate the score in a misleading direction — they are
  simply not counted.

## Scope Boundaries

- Suppression is by finding ID only. No bulk suppression by dimension, severity, or pattern.
- No suppression inheritance across projects.
- No suppression of entire dimensions.
- Suppressions are local to `.econharness/` — not committed or shared by default (that is a
  user/team convention decision, not a tool decision).

## Key Decisions

- **Excluded from score**: Suppressed findings don't count against the score. Rationale: the score
  should reflect genuine open violations. A score penalized by acknowledged deviations loses
  credibility as a signal.
- **Duration-based expiry (`--expires 90d`)**: Easier to reason about than absolute dates.
  Stored as an ISO date internally.
- **Expired suppressions stay visible**: Don't auto-delete. Expired suppressions reappear in
  `next` automatically; users can renew or remove them explicitly.
- **Suppressions survive rescan**: State is overwritten on scan; suppressions must be stored
  separately and merged at read time.

## Dependencies / Assumptions

- Depends on finding IDs being stable across rescans for the same logical issue. If a rescan
  assigns a different ID to the same finding, the suppression is silently orphaned.
  [Deferred to planning: verify ID stability in detectors.py]

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] Where are suppressions stored — separate `.econharness/suppressions.json`
  or a `suppressions` key inside `state.json`? (Separate file is safer for surviving rescan
  overwrites; confirm during planning.)
- [Affects R4][Technical] Score recalculation: does `save_scan_result` need to accept active
  suppressions at scan time, or is score adjusted at read time in `scan_result_from_state`?
- [Affects R1][Needs research] Are finding IDs stable across rescans for the same logical
  violation? Check detector ID assignment in `detectors.py` and `scanner.py`.

## Next Steps
→ `/ce:plan` for structured implementation planning
