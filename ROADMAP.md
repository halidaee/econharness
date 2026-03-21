# econharness Roadmap

This roadmap tracks the next set of `econharness` features needed to better align the harness with the reproducibility and project-discipline standards it is modeled after.

The intent is not to turn `econharness` into a generic software-quality linter.
The intent is to make it a stronger project-quality harness for empirical research workflows, especially when an LLM agent is being used as the primary coding assistant.

## Current Direction

These decisions are settled for the next phase:

- Add stronger checks for version-control discipline.
- Add a from-scratch rebuild verification mode, but do not delete prior outputs.
- Add explicit stage objects in `.econharness.yml` for stage-level read/write contracts.
- Add narrow self-documenting-code checks based on filenames and vague function names.
- Add strong hidden-global-write detection.
- Add soft outer-scope dependency detection inside functions.
- Add config-backed slow-stage discipline.
- Add test-command and test-presence checks.

These items are explicitly deferred:

- relational keyed-table / foreign-key / normalization analysis
- guard detection around joins and other risky operations
- task-tracking or project-management checks

These are roadmap ideas for later product expansion:

- LLM-assisted naming-quality analysis
- stronger LLM-assisted function dependency analysis
- richer relational-data reasoning

## Phase 1

### 1. Version-Control Discipline

Goal:
Detect when the repo is using filenames as a substitute for version control.

Planned checks:

- flag filenames containing patterns like `final`, `new`, `old`, `copy`, `rev`, `v2`, `v3`, dated suffixes, or author initials
- flag clusters of near-duplicate filenames in the same directory
- add a verification check for a clean/stable post-run tree

Notes:

- this should be a real detector, not just README guidance
- filename heuristics should stay conservative to avoid punishing legitimate draft paper names or archival raw files

### 2. From-Scratch Rebuild Integrity

Goal:
Verify that the project can rebuild without relying on stale derived or output artifacts.

Planned implementation:

- add a `verify` mode that quarantines declared generated artifacts before the run
- quarantine means moving files into a gitignored `.econharness/quarantine/<timestamp>/` area
- run the authoritative build after quarantine
- report which artifacts were regenerated, which were missing, and which stale artifacts appear to have been required

Important constraint:

- never delete project artifacts as part of this verification mode

Why quarantine instead of deletion:

- users need the old artifacts on hand if the rebuild fails
- it makes debugging hidden dependencies much easier

### 3. Stage Contracts

Goal:
Make directory and stage structure enforceable rather than purely descriptive.

Chosen design:

- use explicit stage objects in `.econharness.yml`

Proposed schema:

```yaml
stages:
  - name: main_analysis
    match: ["analysis/code/main/**"]
    read_roots: ["raw", "derived"]
    write_roots: ["derived", "temp/main_analysis"]

  - name: exhibits
    match: ["analysis/code/exhibits/**"]
    read_roots: ["derived", "output/tables"]
    write_roots: ["output/figures", "temp/exhibits"]
```

Planned checks:

- resolve which stage a file belongs to based on `match`
- flag explicit path reads outside `read_roots`
- flag writes outside `write_roots`
- keep this path-based and structural rather than trying to infer semantic intent

Open implementation question:

- whether unmatched files should be ignored or surfaced as configuration gaps

Current leaning:

- unmatched code files should produce a low-severity finding if stage contracts are enabled

### 4. Narrow Self-Documenting-Code Checks

Goal:
Improve project legibility without pretending to judge code semantics.

Scope for v1:

- vague or low-information filenames such as `tmp`, `script2`, `analysis_new`, `final_final`
- clusters of duplicate-version filenames
- vague reusable function names such as `helper`, `run`, `temp_func`, `foo`, `bar`

Out of scope for v1:

- judging whether variable names are conceptually clear
- grading overall readability or abstraction quality
- requiring higher comment density

Reason for narrow scope:

- these signals can be detected reliably without an LLM
- broader readability scoring would likely create noise

### 5. Function State Discipline

Goal:
Detect hidden state and hidden dependencies in reusable code.

#### 5a. Strong hidden-global-write detection

Examples to catch:

- Python `global`
- writes to module-level mutable state from inside functions
- R `<<-`
- `assign(..., envir = .GlobalEnv)`
- other direct writes to `.GlobalEnv`

This should be a strong detector because these patterns create real hidden behavior.

#### 5b. Soft outer-scope dependency detection

Goal:
Flag functions that quietly depend on names from outer scope instead of explicit arguments.

Planned approach:

- collect names used inside a function
- subtract parameters, local assignments, imports, and builtins
- treat remaining free variables as hidden dependencies

This should remain soft because:

- some repos intentionally centralize constants in config modules
- free-variable detection will produce some false positives

Explicit non-goal:

- do not add a generic "function shyness" or "good function design" score

### 6. Test Command and Test Presence

Goal:
Make it easier for the harness to reward projects that automate correctness checks.

Planned checks:

- support an explicit `pipeline.command.tests`
- detect conventional test files/directories
- flag helper-heavy repos with no declared test path

Deferred to v2:

- more specific guard detection around joins, row counts, or risky transformations

## Phase 2

### 7. Slow-Stage Discipline

Goal:
Keep expensive computation separated from fast presentation and downstream iteration.

Chosen design:

- use pure config rather than heuristic detection

Reason:

- an LLM is already being instructed to create `.econharness.yml`
- config is more precise and less annoying than trying to guess what is computationally expensive

Proposed schema:

```yaml
pipeline:
  command:
    fast: "..."
    full: "..."
  stages:
    - name: estimate_models
      slow: true
      command: "..."
      outputs: ["derived/models", "derived/predictions"]

    - name: figures
      slow: false
      command: "..."
      inputs: ["derived/models", "derived/predictions"]
      outputs: ["output/figures"]
```

Planned checks:

- flag projects with no declared fast path when slow stages exist
- flag slow stages that do not declare reusable outputs
- flag downstream stages that appear to recompute slow work instead of consuming declared outputs

Implementation note:

- the overall agent instructions in the README should be updated so the LLM is expected to populate these fields rather than defaulting to a permissive config

## Deferred Items

### Relational Keyed-Table Analysis

This remains important, but it is intentionally deferred until after the easier structural features land.

Deferred subtopics:

- foreign-key declarations
- normalized vs. early-denormalized table structure
- join cardinality contracts
- stronger merge reasoning based on declared table structure

Reason for deferral:

- this is conceptually valuable but much harder to do well
- the risk of noisy or brittle implementation is higher than for the other roadmap items

### Guard Detection

Potential future checks:

- assertions before and after joins
- row-count explosion checks
- sample-size sanity checks
- required-column validation

Status:

- keep as a v2 or later item

### Task Tracking

This is intentionally out of scope.

## README / Prompt Follow-Up

After the above features land, the README guidance for agents should be tightened so the default prompt tells the LLM to:

- define explicit stage contracts in `.econharness.yml`
- declare slow computational stages
- avoid being overly lenient or under-specified in config

Without that, the harness will have the features but agents will not reliably configure them.
