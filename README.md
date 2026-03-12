# econharness

`econharness` is an agent harness and project-checking tool for empirical economics workflows.

Current version: `0.1.0` (alpha)

It is built for the situation many economists are now in:

- you use Claude Code, Codex, or another LLM agent to help write code;
- the agent often produces useful work, but also leaves behind confusing project structure, redundant scripts, fragile paths, and undocumented steps;
- you want a way to check whether the project still looks like a reproducible economics project rather than an accumulating pile of AI-generated fixes;
- you want the agent itself to have a structured way to notice those problems and work through them systematically.

Its main value is not just that it tells you what is wrong with a research repo.
Its main value is that it gives Claude Code, Codex, or another coding agent a concrete standard and feedback loop for making the repo better over repeated passes.
In that sense, it is meant to help an agent gradually "self-heal" an economics project instead of just adding more ad hoc code.

It can also be used directly by a human, but most users will probably get the most value by giving it to their agent and letting the agent work through the findings.

## Two Ways To Use econharness

- `Hands-off (recommended)`: give the prompt below to Claude Code or Codex and let the agent use `econharness` as its repair loop.
- `Direct use`: run `econharness` yourself from the command line to inspect the project, review findings, and generate a scorecard.

If you are unsure which mode you want, start with the hands-off one.

## If You Want The Hands-Off Workflow

The intended model is simple:

1. your agent writes or edits code;
2. `econharness` checks what kind of project you now have;
3. the agent uses those findings to improve the repo;
4. the loop repeats until the project looks more like a reproducible economics workflow and less like an accumulation of ad hoc fixes.

## Instructions For Your Agent

If you want Claude Code or Codex to use `econharness` as a self-healing loop, give it instructions like this:

```text
Use econharness as the project-quality harness for this repository.

Your goal is not just to make the code run. Your goal is to improve the project so it looks like a reproducible empirical economics project.

Default workflow:
1. Run `python3 -m econharness scan --path .`
2. Read the strict score, dimension breakdown, and top findings.
3. Fix the highest-priority findings first.
4. Prefer improvements that strengthen reproducibility, portability, stage separation, and project clarity over generic refactoring.
5. Run `python3 -m econharness scan --path .` again after meaningful changes.
6. Repeat until the most important findings are resolved or you hit a clear stopping point.

When fixing issues, prioritize:
- authoritative rebuild commands
- removal of manual steps
- raw/build/analysis/output separation
- reproducible environments such as renv and pixi
- portable relative paths instead of absolute paths
- artifact traceability into the paper/output layer
- dead code, unused imports, duplicate logic, and orphaned scripts

Do not optimize for generic software-engineering elegance at the expense of transparency.
Do not hide research logic behind unnecessary abstractions.
Do not suppress findings just to improve the score.

If you make changes, explain which econharness findings you were addressing and what changed in the score or findings afterward.
```

That prompt is deliberately simple.
The point is to make the agent follow a repeatable discipline rather than improvising a new standard each session.

## What Problem This Solves

Many economists are now in a situation like this:

- they use Claude Code, Codex, or another LLM agent to help write code;
- the agent produces useful work, but also leaves behind confusing project structure, redundant scripts, fragile paths, and undocumented steps;
- over time the project still runs, but becomes harder for an RA, coauthor, or even the original author to understand and rerun.

In an economics project, the important questions are usually:

- can another RA or coauthor rerun this from raw data to final outputs;
- is there one clear way to rebuild the project;
- are raw, constructed, analysis, and output files separated cleanly;
- are there hidden manual steps;
- are paths portable across machines;
- are the environments reproducible;
- did the LLM help write code, but also create extra junk, duplicate logic, or scripts nobody can now interpret.

`econharness` is meant to check those things first.

## What It Checks

`econharness` scans a project and surfaces findings around:

- missing one-command rebuild workflows;
- manual steps and hand-edited intermediates;
- poor separation between raw data, derived data, analysis code, and outputs;
- non-portable or absolute file paths;
- missing reproducible environments such as `renv` or `pixi`;
- weak data lineage and poor artifact traceability into the paper layer;
- duplicate keys and other relational-data problems in important intermediate files;
- dead code, unused imports, redundancy, orphaned scripts, and other LLM mess.

The standard is closer to Gentzkow/Shapiro-style project discipline than to generic software-engineering polish.

## If You Want To Use It Yourself Directly

From the repository root:

```bash
python3 -m econharness scan --path tests/fixtures/good_project
python3 -m econharness status --path tests/fixtures/good_project
python3 -m econharness next --path tests/fixtures/good_project
python3 -m econharness verify --path tests/fixtures/good_project --profile fast
python3 -m econharness review --path tests/fixtures/good_project
python3 -m econharness scorecard --path tests/fixtures/good_project
python3 -m econharness init --path /path/to/project
```

What these do:

- `scan`: inspect the project, compute scores, save findings, and generate a scorecard;
- `status`: show the last saved project status;
- `next`: show the next highest-priority finding to fix;
- `verify`: run a configured fast or full rebuild check;
- `review`: print a short research-structure summary;
- `scorecard`: regenerate the SVG and HTML scorecard;
- `init`: write a starter `.econharness.yml`.

## How To Read The Output

Running `scan` gives you:

- a strict score;
- a breakdown by dimension;
- a ranked list of findings;
- a persisted state file;
- a scorecard in SVG and HTML form.

The score is only useful if you interpret it correctly.
It is not a grade on the paper.
It is a summary of project organization and reproducibility risk.

## Reproducible Environments

`econharness` strongly prefers projects that declare reproducible environments.

For example:

- `R` projects should usually use `renv`;
- `Python` projects should usually use `pixi` or another lockfile-backed environment;
- verification commands should ideally run through those declared environments.

This matters especially in economics projects because a lot of code “works on my machine” right until a coauthor or RA tries to rerun it.

## Configuration

`econharness` looks for `.econharness.yml` in the project root.

The config is where you tell it things like:

- what the authoritative rebuild command is;
- what the fast and full verification commands are;
- where raw, derived, analysis, output, and paper paths live;
- which datasets matter enough to declare keys and units of observation;
- which artifacts you expect the project to produce.

The default file written by `init` uses JSON-compatible YAML to keep parsing simple and dependency-light.

## What It Is Not

`econharness` is not:

- a replacement for your own judgment;
- a statistical referee;
- a proof that a project is correct;
- a general-purpose software quality platform;
- a fully autonomous research agent.

It is better to think of it as a structured project audit plus agent-repair loop for research code.

## Who This Is For

This tool is especially aimed at:

- economists using LLM agents for research coding;
- RAs cleaning up inherited or messy empirical projects;
- coauthors trying to impose structure on mixed `R`, `Python`, and `Quarto` workflows;
- researchers who care more about reproducibility and handoff than about software-engineering aesthetics.

If you mainly write production software, this project will probably feel oddly opinionated.
That is intentional.

## Current Scope

The current implementation is a dependency-light CLI focused on mixed:

- `R`
- `Python`
- `Quarto`

projects.

It is still early-stage and opinionated.
The point right now is to make research-project structure legible and auditable, especially in projects touched heavily by LLM agents.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
