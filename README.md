# econharness

`econharness` is a Gentzkow/Shapiro-oriented research-project harness for economics workflows.

It scores and surfaces findings around:

- one-command automation
- elimination of manual steps
- reproducible environments (`renv`, `pixi`, or other declared lockfile-backed tools)
- portable project-root-relative paths
- stage-based project structure
- relational intermediate datasets with explicit keys and units
- artifact traceability into the paper/output layer
- dead code, unused imports, redundancy, and other software slop

The implementation in this repository is a dependency-light CLI focused on mixed `R`, `Python`, and `Quarto` projects.

## Commands

```bash
python -m econharness scan --path tests/fixtures/good_project
python -m econharness status --path tests/fixtures/good_project
python -m econharness next --path tests/fixtures/good_project
python -m econharness verify --path tests/fixtures/good_project --profile fast
python -m econharness init --path /path/to/project
```

## Config

`econharness` looks for `.econharness.yml` in the project root. To stay dependency-light, the default config file written by `init` uses JSON-compatible YAML.

## Tests

```bash
python -m unittest discover -s tests -v
```
