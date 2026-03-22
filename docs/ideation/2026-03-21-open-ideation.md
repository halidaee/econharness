---
date: 2026-03-21
topic: open-ideation
focus: (open-ended)
---

# Ideation: econharness Improvements

## Codebase Context

- **Project shape:** Python 3.11+, pure stdlib, zero runtime dependencies, v0.1.1. CLI tool (`econharness`) with commands: scan, status, next, verify (--from-scratch, --check-clean-tree), init, review, scorecard.
- **Architecture:** detectors → findings → scoring → scorecard (SVG/HTML output). 16 modules.
- **Primary users:** LLM agents in automated repair loops (explicitly stated in README) AND economics researchers (non-engineers).
- **Key extension points:** detectors.py, stages.py, slow_stages.py, scoring.py, scorecard.py.
- **Notable gaps:** No README, no CI, no dev env file at root, placeholder author in pyproject.toml, sparse module-level docs.
- **Core constraint:** Zero runtime dependencies — any idea that requires a new library dependency is a non-starter.

## Ranked Ideas

### 1. Agent-native JSON output
**Description:** Add a `--format json` flag to `scan`, `next`, and `status` that emits `Finding` data as machine-readable JSON. The `Finding` dataclass is already fully structured — this is a thin output layer, ~30 lines in `cli.py`.
**Rationale:** The primary use case (per README) is LLM agents in repair loops. Agents currently parse human prose from `next`, which is fragile and wastes tokens. A structured JSON response is the difference between a brittle repair loop and a reliable one.
**Downsides:** None material. Adds a CLI flag and a serialization path.
**Confidence:** 95%
**Complexity:** Low
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-agent-json-output-requirements.md`

### 2. First-class deviation tracking with expiry
**Description:** Extend `state.json` with a `suppressions` map: per-finding suppression with a `reason` string and optional `expires` date. `findings_from_state` filters suppressed findings. `next` respects suppressions. New command: `econharness suppress <finding-id> --reason "..." --expires 90d`.
**Rationale:** Without suppression, `next` permanently recycles false positives and legitimate deviations — the repair loop stalls. Expiry prevents suppressions from becoming a permanent-override junk drawer. Addresses both agent use (filter known non-issues) and researcher use (document principled deviations, e.g. no lockfile because raw data is proprietary).
**Downsides:** State schema change required; suppressions can mask real problems if misused.
**Confidence:** 82%
**Complexity:** Medium
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-deviation-tracking-requirements.md`

### 3. Quarantine rollback on failed from-scratch runs
**Description:** Store a manifest of moved artifacts when quarantining in `quarantine.py`. In `verify.py`, if the pipeline subprocess returns non-zero, call `restore_quarantine(manifest)` before exiting. Add a `restore-quarantine` CLI command for manual recovery.
**Rationale:** Correctness hole, not a feature request. If `verify --from-scratch` fails mid-rebuild, artifacts are quarantined and not restored — leaving the project in a broken state. Atomic rollback is a requirement for any file-moving operation.
**Downsides:** Rollback logic adds code to quarantine.py; edge cases around partial restores.
**Confidence:** 80%
**Complexity:** Low-Medium
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-quarantine-rollback-requirements.md`

### 4. Scan history & delta tracking
**Description:** Append scan results to `.econharness/history/` as timestamped JSON snapshots (keyed by timestamp + git commit hash). Add `econharness status --diff` to show: score delta, new findings, and resolved findings since the previous scan.
**Rationale:** A repair loop with no memory can't detect regressions or confirm progress. `state.json` is a single-file overwrite — zero history. Delta output turns a static report into a feedback signal that directly serves the agent repair loop.
**Downsides:** History grows unboundedly; needs a pruning strategy. Meaningful commit-keyed diffs require git integration.
**Confidence:** 78%
**Complexity:** Medium
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-scan-history-requirements.md`

### 5. Smart config bootstrapping on `init`
**Description:** When `econharness init` runs, introspect the project before writing config: detect `Makefile`/`run_all.R`/`run_all.sh` for pipeline command candidates; detect `pixi.toml`/`renv.lock`/`requirements.txt` for environment type; detect existing directory structure for stage paths. Emit a pre-populated config instead of a blank template.
**Rationale:** `init` currently writes a static default with empty pipeline commands. Any agent or researcher calling `init` then `verify` immediately gets `ValueError: No 'fast' verification command is configured`. The cold-start problem blocks every new project.
**Downsides:** Introspection can be wrong; user needs to verify suggestions.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-smart-init-requirements.md`

### 6. Config validation / lint command
**Description:** Add `econharness check-config` that parses `.econharness.yml`, validates required fields, type-checks stage `match` patterns, and warns on silently-defaulted values. Also run validation during `scan` and emit a distinct error if the config is malformed (rather than silently falling back to defaults).
**Rationale:** `load_config` silently falls back to defaults on malformed YAML. Stage contracts produce zero findings when `match` patterns are wrong. Agents produce bad YAML. The tool cannot distinguish "clean project" from "broken config, nothing ran." This is a reliability gap that undermines the entire scan signal.
**Downsides:** Requires specifying the config schema clearly and completely.
**Confidence:** 75%
**Complexity:** Low
**Status:** Explored — brainstormed 2026-03-21, requirements at `docs/brainstorms/2026-03-21-config-validation-requirements.md`

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| — | Clarify scan/status/review hierarchy | Docs/help text fix, not a capability gap |
| — | Context-aware remediation text | Cosmetic per-detector polish, low leverage |
| — | Better scorecard surfacing | Documentation padding; path already printed |
| — | Multi-path finding reporting | Downgraded: data model patch (`paths: list[str]`), not a standalone feature |
| — | In-CLI onboarding / interactive help | Antithetical to agent-native primary use case |
| — | Finding dependency chain analysis | Speculative; maintaining inter-finding dependency graph is expensive |
| — | Dataset lineage visualization | Requires data provenance tracking far beyond heuristic path patterns |
| — | Multi-project portfolio comparison | Product pivot; requires storage/aggregation layer |
| — | Auto-remediation / fix mode | Actively harmful for agent use case — agent IS the remediation layer |
| — | Pre-commit hook integration | Blocking gate misaligned with research workflow and agent use |
| — | Scaffolding command | Agent should create structure; linter risks clobbering real project |
| — | Pipeline command suggestion engine | Downgraded: 10-line UX fix in verify.py when command is missing |
| — | Watch mode | Breaks zero-dependency constraint; agents don't need it |
| — | Paper-to-code reverse traceability | Requires NLP/semantic LaTeX parsing; out of scope for stdlib linter |
| — | Swappable scoring backends | Architecture astronautics; current linear model is adequate |
| — | Cohort benchmarking | Requires curated benchmark dataset that doesn't exist |
| — | Stage contracts as first-class core | Refactor with no user-visible effect |
| — | Extensible detector plugin system | Premature; detector surface not yet stable |
| — | Finding severity recalibration | Downgraded: document weights + expose as config override |
| — | Batch portfolio scanning | Wrong product, wrong scale |
| — | Incremental file-hash caching | Negligible runtime benefit for research-project file counts |
| — | Language-specific detector config | High complexity, low value |
| — | Live repair session (TUI) | TUI dependency antithetical to agent-native use case |

## Session Log
- 2026-03-21: Initial ideation — ~48 raw candidates generated across 6 frames, 6 survived adversarial filtering
- 2026-03-21: All 6 survivors brainstormed, requirements docs written in `docs/brainstorms/`
