"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from econharness.config import config_path_for, render_default_config
from econharness.scanner import scan_project
from econharness.state import findings_from_state, load_state, save_scan_result
from econharness.verify import verify_project


def _resolve_path(path: str | None) -> Path:
    return Path(path or ".").resolve()


def _print_scan(result) -> None:
    print(f"Project: {result.project_root}")
    print(f"Strict score: {result.overall_score:.1f}")
    print(f"Findings: {result.summary['findings']} ({result.summary['high_severity']} high)")
    print("Dimensions:")
    for key, score in result.dimension_scores.items():
        print(f"  {key}: {score:.1f}")
    if result.findings:
        print("Top findings:")
        for finding in result.findings[:5]:
            location = f" [{finding.path}]" if finding.path else ""
            print(f"  - ({finding.severity}) {finding.title}{location}")


def _print_status(state: dict) -> None:
    print(f"Project: {state['project_root']}")
    print(f"Strict score: {state['overall_score']:.1f}")
    print("Dimensions:")
    for key, score in state.get("dimension_scores", {}).items():
        print(f"  {key}: {score:.1f}")
    print(f"Open findings: {len(state.get('findings', []))}")


def _print_next(path: Path) -> None:
    findings = findings_from_state(path)
    if not findings:
        print("No findings. Run `econharness scan` first.")
        return
    finding = findings[0]
    print(f"{finding.title} [{finding.severity}]")
    print(f"Dimension: {finding.dimension}")
    if finding.path:
        print(f"Path: {finding.path}")
    print(f"Detail: {finding.detail}")
    print(f"Fix: {finding.remediation}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="econharness")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="Scan a project and persist findings")
    scan.add_argument("--path", default=".")

    status = subparsers.add_parser("status", help="Show persisted project status")
    status.add_argument("--path", default=".")

    next_cmd = subparsers.add_parser("next", help="Show the next highest-priority finding")
    next_cmd.add_argument("--path", default=".")

    verify = subparsers.add_parser("verify", help="Run a configured fast or full verification command")
    verify.add_argument("--path", default=".")
    verify.add_argument("--profile", choices=["fast", "full"], default="fast")

    init = subparsers.add_parser("init", help="Write a default config file")
    init.add_argument("--path", default=".")
    init.add_argument("--force", action="store_true")

    review = subparsers.add_parser("review", help="Emit a heuristic research-structure review summary")
    review.add_argument("--path", default=".")

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    project_root = _resolve_path(getattr(args, "path", "."))

    if args.command == "scan":
        result = scan_project(project_root)
        save_scan_result(project_root, result)
        _print_scan(result)
        return

    if args.command == "status":
        state = load_state(project_root)
        if not state:
            print("No scan state found. Run `econharness scan` first.")
            return
        _print_status(state)
        return

    if args.command == "next":
        _print_next(project_root)
        return

    if args.command == "verify":
        try:
            result = verify_project(project_root, args.profile)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        print(f"Profile: {result.profile}")
        print(f"Command: {result.command}")
        print(f"Return code: {result.returncode}")
        if result.stdout.strip():
            print("--- stdout ---")
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print("--- stderr ---")
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            sys.exit(result.returncode)
        return

    if args.command == "init":
        config_path = config_path_for(project_root)
        if config_path.exists() and not args.force:
            print(f"{config_path} already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(2)
        config_path.write_text(render_default_config(), encoding="utf-8")
        print(f"Wrote {config_path}")
        return

    if args.command == "review":
        result = scan_project(project_root)
        print("Research workflow review")
        print(f"Strict score: {result.overall_score:.1f}")
        if not result.findings:
            print("The project looks structurally disciplined on the current heuristics.")
            return
        top = result.findings[:5]
        for finding in top:
            print(f"- {finding.title}: {finding.detail}")
        return
