---
date: 2026-03-21
topic: scan-history
---

# Scan History & Delta Tracking

## Problem Frame

`state.json` is a single-file overwrite — every `scan` replaces the prior result entirely.
An agent running multiple repair iterations has no way to confirm it made progress, detect
regressions, or know which findings it resolved. Researchers have no feedback signal
between scans. Delta tracking gives both agents and humans a progress signal with near-zero
extra complexity.

## Requirements

- R1. Every `scan` appends the current result as a timestamped snapshot to a history store.
  The history retains the **last 10 snapshots** per project; older snapshots are pruned
  automatically when a new one is added (oldest-first).
- R2. After writing state, `scan` automatically computes a delta against the previous snapshot
  (if one exists) and prints it. If no prior snapshot exists, nothing extra is printed.
- R3. The delta output shows:
  - Overall score change: e.g. `Score: 72.3 → 74.1 (+1.8)`
  - Per-dimension score changes for any dimension whose score changed (skip unchanged)
  - New findings: titles of findings that appear in the new scan but not the previous one
  - Resolved findings: titles of findings that appeared in the previous scan but not the new one
- R4. `econharness status --diff` prints the same delta output as R3, computed on demand from
  the two most recent snapshots. Exits with a message if fewer than 2 snapshots exist.
- R5. `--json` (from the agent JSON output feature) applied to `scan` and `status --diff`
  includes the delta as a structured object:
  `{"score_delta": 1.8, "dimension_deltas": {...}, "new_findings": [...], "resolved_findings": [...]}`
- R6. Finding identity for delta computation is based on finding `id`. A finding is "resolved"
  if its `id` is absent from the new scan; "new" if its `id` is absent from the previous scan.
- R7. History snapshots include a `scanned_at` ISO 8601 timestamp recorded at write time.

## Success Criteria

- After two consecutive scans, `scan` (second run) prints a delta showing what changed.
- `econharness status --diff` shows the same delta on demand.
- An agent repair loop can read `scan --json` and parse `delta.score_delta` and
  `delta.resolved_findings` to confirm it made progress.
- History never exceeds 10 entries per project.

## Scope Boundaries

- Delta is always "previous scan vs. current scan" — no `--since` flag or named baselines.
- No cross-project delta.
- History snapshots are append-only (no editing or tagging of past snapshots).
- No trend graphs or visualizations — plain text and JSON delta only.

## Key Decisions

- **Previous scan only**: Simplest useful delta. A repair loop always cares about the most
  recent change, not a distant baseline.
- **Auto-print delta on scan**: Agents and users see progress without an extra command.
  Zero-cost to add alongside existing scan output.
- **Retain last 10**: Bounded, predictable disk usage; enough history for an active repair loop.
- **ID-based finding identity**: Finding IDs are the stable key for "same finding." If IDs
  change across scans for the same logical issue, resolution tracking will be noisy.
  [See also deviation-tracking requirements: same ID stability dependency]

## Dependencies / Assumptions

- Finding IDs must be stable across rescans for the same logical violation. Delta resolution
  tracking is noisy if IDs change for the same logical finding. [Shared dependency with
  deviation-tracking feature; planner should verify in detectors.py.]

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] Where is history stored — appended to a single `history.jsonl` file
  or as individual timestamped JSON files in `.econharness/history/`? Planner to decide based
  on read/write simplicity and pruning mechanics.
- [Affects R6][Needs research] Verify that finding IDs are deterministically generated per
  logical issue across rescans (detectors.py / scanner.py). If not, ID-based identity
  will need a fallback (e.g. title + dimension + path tuple).

## Next Steps
→ `/ce:plan` for structured implementation planning
