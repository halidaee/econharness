---
title: "feat: Add --json output flag to scan, status, and next commands"
type: feat
status: completed
date: 2026-03-21
origin: docs/brainstorms/2026-03-21-agent-json-output-requirements.md
---

# feat: Add `--json` Output Flag to scan, status, and next

The primary use case for econharness is LLM agents in automated repair loops. All three read
commands currently write human-readable prose to stdout, forcing agents to parse text —
fragile and token-wasteful. A `--json` flag on each command emits the same data as structured
JSON, making repair loops reliable.

## Acceptance Criteria

- [ ] `econharness scan --json` emits a single JSON object to stdout: `project_root`,
  `overall_score`, `dimension_scores`, `findings` (full array of Finding dicts),
  `summary` (`findings` count, `high_severity` count). No prose on stdout.
- [ ] `econharness status --json` emits a single JSON object: `project_root`,
  `overall_score`, `dimension_scores`, `findings` (count), and `scanned_at` if present.
- [ ] `econharness next --json` emits a single JSON object with the top Finding's fields
  (`id`, `dimension`, `severity`, `title`, `detail`, `remediation`, `score_impact`, `path`)
  plus `remaining` (total open finding count including this one).
- [ ] When `--json` is active and an error occurs (no state file, no findings, config error),
  the command emits `{"error": "<message>"}` to stdout and exits non-zero.
- [ ] Without `--json`, all existing prose output is unchanged.
- [ ] `--json` is available on `scan`, `status`, and `next` only. All other commands are
  unaffected.
- [ ] `scan --json`: scorecard SVG/HTML paths are suppressed from stdout (they are a
  side effect, not part of the JSON response).
- [ ] Tests added for all three commands using `subprocess.run` + `json.loads(result.stdout)`.

## Context

**Key patterns in the codebase:**
- `dataclasses.asdict` is already imported and used in `state.py:27` to serialize `Finding`
  objects — reuse this pattern in `cli.py`.
- `scan --json` payload structure mirrors what `save_scan_result` already writes to
  `state.json` (`state.py:22-31`).
- `status` raw `state` dict from `load_state()` is already JSON-compatible — can be emitted
  directly after excluding or stringifying any non-serializable fields.
- Argparse pattern: `--json` is `action="store_true"` added to each sub-parser, accessed
  as `args.json` in the dispatch branch (`cli.py:57-88`).
- All CLI integration tests use `subprocess.run(capture_output=True, text=True)` and assert
  on stdout/returncode (`tests/test_cli.py`).

**Scorecard side effect:** `scan` prints scorecard paths (`Scorecard SVG:`, `Scorecard HTML:`)
outside `_print_scan` at `cli.py:105-106`. These must be suppressed when `--json` is active —
`generate_scorecard` should still run (it writes files), just don't print the paths.

## Implementation Notes

### Files to change
- `econharness/cli.py` — add `--json` arg to `scan`, `status`, `next_cmd` sub-parsers; add
  JSON emission branch in each command's dispatch block
- `tests/test_cli.py` — add `--json` test cases for scan, status, next

### JSON payloads

**`scan --json`:**
```json
{
  "project_root": "...",
  "overall_score": 74.1,
  "dimension_scores": {"automation": 87.0, ...},
  "findings": [{"id": "...", "dimension": "...", ...}, ...],
  "summary": {"findings": 12, "high_severity": 3}
}
```

**`status --json`:**
```json
{
  "project_root": "...",
  "overall_score": 74.1,
  "dimension_scores": {...},
  "findings": 12,
  "scanned_at": "2026-03-21T10:00:00"
}
```

**`next --json`:**
```json
{
  "id": "detect_automation_001",
  "dimension": "automation",
  "severity": "high",
  "title": "No fast rebuild command declared",
  "detail": "...",
  "remediation": "...",
  "score_impact": 5.2,
  "path": null,
  "remaining": 7
}
```

**Error:**
```json
{"error": "No state file found. Run econharness scan first."}
```

## Sources

- **Origin document:** [docs/brainstorms/2026-03-21-agent-json-output-requirements.md](../brainstorms/2026-03-21-agent-json-output-requirements.md)
  — Key decisions: `--json` boolean flag (not `--format`); `next --json` returns top 1 + remaining count; errors as JSON on stdout with non-zero exit.
- `econharness/cli.py` — dispatch logic, `_print_scan`, `_print_status`, `_print_next`
- `econharness/models.py` — `Finding`, `ScanResult` dataclasses
- `econharness/state.py:6,27` — `asdict` import and usage pattern
- `tests/test_cli.py` — existing subprocess test pattern
