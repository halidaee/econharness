---
date: 2026-03-21
topic: agent-json-output
---

# Agent-Native JSON Output

## Problem Frame

`econharness` is primarily used by LLM agents in automated repair loops. All three read
commands (`scan`, `status`, `next`) currently write human-readable prose to stdout. Agents
must parse that prose to extract findings, scores, and paths — which is fragile, token-wasteful,
and brittle across output changes. A `--json` flag on each command emits the same data as
structured JSON, making the repair loop reliable.

## Requirements

- R1. `econharness scan --json` emits a single JSON object to stdout containing: `project_root`,
  `overall_score`, `dimension_scores` (object), `findings` (array of Finding objects), and
  `summary` (`findings` count, `high_severity` count). No human-readable prose is written to
  stdout when `--json` is active.
- R2. `econharness status --json` emits a single JSON object to stdout with the same shape as
  the persisted state: `project_root`, `overall_score`, `dimension_scores`, `findings` count,
  and `scanned_at` timestamp if present.
- R3. `econharness next --json` emits a single JSON object containing the top-priority Finding
  (`id`, `dimension`, `severity`, `title`, `detail`, `remediation`, `score_impact`, `path`)
  plus a `remaining` count (total open findings including this one). Returns the same top-1
  finding as the prose `next` command.
- R4. When `--json` is active and an error occurs (no state file, no findings, invalid path),
  the command emits `{"error": "<message>"}` to stdout and exits non-zero. No mixing of prose
  and JSON on stdout.
- R5. `--json` is available on `scan`, `status`, and `next` only. `verify`, `init`, `review`,
  and `scorecard` are out of scope.
- R6. When `--json` is not passed, all existing prose output is unchanged.

## Success Criteria

- An agent calling `econharness next --json` can extract the top finding's `id`, `remediation`,
  and `path` with a single JSON parse — no string matching required.
- An agent calling `econharness scan --json` can read `overall_score` and iterate `findings`
  without parsing prose.
- All existing CLI tests continue to pass (prose output unchanged).

## Scope Boundaries

- No `--format` flag or format ecosystem. `--json` is a boolean flag. YAGNI.
- `next --json` returns top 1 finding only, not all findings in priority order.
- Scorecard SVG/HTML generation is unaffected.
- No changes to the `Finding` or `ScanResult` data models.

## Key Decisions

- **`--json` not `--format json`**: Zero-dependency constraint and YAGNI. No other output formats
  are planned.
- **`next --json` returns top 1**: Consistent with existing `next` behavior. Agents call `next`,
  act, repeat — they do not need the full list.
- **Error output on stdout not stderr**: Agents typically capture stdout. A JSON error object on
  stdout with non-zero exit is more reliably handled than a stderr message.

## Next Steps
→ `/ce:plan` for structured implementation planning
