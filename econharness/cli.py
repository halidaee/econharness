"""CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from econharness.config import config_path_for, render_default_config
from econharness.scanner import scan_project
from econharness.scorecard import generate_scorecard
from econharness.state import findings_from_state, load_state, save_scan_result, scan_result_from_state
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
    scan.add_argument("--json", action="store_true", help="Emit JSON output")

    status = subparsers.add_parser("status", help="Show persisted project status")
    status.add_argument("--path", default=".")
    status.add_argument("--json", action="store_true", help="Emit JSON output")

    next_cmd = subparsers.add_parser("next", help="Show the next highest-priority finding")
    next_cmd.add_argument("--path", default=".")
    next_cmd.add_argument("--json", action="store_true", help="Emit JSON output")

    verify = subparsers.add_parser("verify", help="Run a configured fast or full verification command")
    verify.add_argument("--path", default=".")
    verify.add_argument("--profile", choices=["fast", "full"], default="fast")
    verify.add_argument("--from-scratch", action="store_true")
    verify.add_argument("--check-clean-tree", action="store_true")
    verify.add_argument("--no-rollback", action="store_true", help="Skip automatic rollback on pipeline failure")

    init = subparsers.add_parser("init", help="Write a default config file")
    init.add_argument("--path", default=".")
    init.add_argument("--force", action="store_true")

    restore_q = subparsers.add_parser("restore-quarantine", help="Restore artifacts from a quarantine directory")
    restore_q.add_argument("--path", default=".")
    restore_q.add_argument("--quarantine-dir", default=None, help="Quarantine directory timestamp to restore")

    review = subparsers.add_parser("review", help="Emit a heuristic research-structure review summary")
    review.add_argument("--path", default=".")

    scorecard = subparsers.add_parser("scorecard", help="Generate an SVG and HTML scorecard from scan state")
    scorecard.add_argument("--path", default=".")
    scorecard.add_argument("--svg-path")
    scorecard.add_argument("--html-path")

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
        svg_path, html_path = generate_scorecard(result, project_root)
        if args.json:
            payload = {
                "project_root": result.project_root,
                "overall_score": result.overall_score,
                "dimension_scores": result.dimension_scores,
                "findings": [asdict(f) for f in result.findings],
                "summary": result.summary,
            }
            print(json.dumps(payload))
        else:
            _print_scan(result)
            print(f"Scorecard SVG: {svg_path}")
            print(f"Scorecard HTML: {html_path}")
        return

    if args.command == "status":
        state = load_state(project_root)
        if not state:
            if args.json:
                print(json.dumps({"error": "No scan state found. Run econharness scan first."}))
                sys.exit(1)
            print("No scan state found. Run `econharness scan` first.")
            return
        if args.json:
            payload = {
                "project_root": state["project_root"],
                "overall_score": state["overall_score"],
                "dimension_scores": state.get("dimension_scores", {}),
                "findings": len(state.get("findings", [])),
                "scanned_at": state.get("scanned_at"),
            }
            print(json.dumps(payload))
        else:
            _print_status(state)
        return

    if args.command == "next":
        findings = findings_from_state(project_root)
        if args.json:
            if not findings:
                print(json.dumps({"error": "No findings. Run econharness scan first."}))
                sys.exit(1)
            finding = findings[0]
            payload = asdict(finding)
            payload["remaining"] = len(findings)
            print(json.dumps(payload))
        else:
            _print_next(project_root)
        return

    if args.command == "verify":
        if getattr(args, "no_rollback", False):
            print("Warning: rollback disabled. Project may be left in a broken state on pipeline failure.", file=sys.stderr)
        try:
            result = verify_project(
                project_root,
                args.profile,
                from_scratch=args.from_scratch,
                check_clean_tree=args.check_clean_tree,
                no_rollback=getattr(args, "no_rollback", False),
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        print(f"Profile: {result.profile}")
        print(f"Command: {result.command}")
        print(f"Return code: {result.returncode}")
        if result.rolled_back:
            print("Pipeline failed — artifacts restored from quarantine.")
        if result.from_scratch:
            print("From scratch: yes")
            if result.quarantine_dir:
                print(f"Quarantine dir: {result.quarantine_dir}")
            print(f"Moved artifacts: {len(result.moved_paths)}")
            print(f"Regenerated artifacts: {len(result.regenerated_paths)}")
            print(f"Missing regenerated artifacts: {len(result.missing_paths)}")
        if args.check_clean_tree:
            before = "unavailable" if result.clean_tree_before is None else ("yes" if result.clean_tree_before else "no")
            after = "unavailable" if result.clean_tree_after is None else ("yes" if result.clean_tree_after else "no")
            print(f"Clean tree before: {before}")
            print(f"Clean tree after: {after}")
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

    if args.command == "restore-quarantine":
        from econharness.quarantine import QuarantineResult, delete_quarantine_dir, restore_quarantine
        from econharness.state import state_dir
        quarantine_base = state_dir(project_root) / "quarantine"
        quarantine_dir_name = getattr(args, "quarantine_dir", None)
        if not quarantine_dir_name:
            if not quarantine_base.exists():
                print("No quarantine directories found.", file=sys.stderr)
                sys.exit(1)
            dirs = sorted(d.name for d in quarantine_base.iterdir() if d.is_dir())
            if not dirs:
                print("No quarantine directories found.", file=sys.stderr)
                sys.exit(1)
            print("Available quarantine directories:")
            for d in dirs:
                print(f"  {d}")
            print("\nSpecify one with --quarantine-dir <timestamp>")
            sys.exit(0)
        target_dir = quarantine_base / quarantine_dir_name
        if not target_dir.exists():
            print(f"Quarantine directory not found: {target_dir}", file=sys.stderr)
            sys.exit(1)
        moved_paths = tuple(
            p.relative_to(target_dir).as_posix()
            for p in target_dir.rglob("*")
            if p.is_file()
        )
        qr = QuarantineResult(quarantine_dir=target_dir, moved_paths=moved_paths)
        restore_quarantine(qr, project_root)
        print(f"Restored {len(moved_paths)} artifact(s) from {quarantine_dir_name}")
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

    if args.command == "scorecard":
        state = load_state(project_root)
        if not state:
            result = scan_project(project_root)
            save_scan_result(project_root, result)
        else:
            result = scan_result_from_state(state)
        svg_path = Path(args.svg_path).resolve() if args.svg_path else None
        html_path = Path(args.html_path).resolve() if args.html_path else None
        written_svg, written_html = generate_scorecard(result, project_root, svg_path=svg_path, html_path=html_path)
        print(f"Scorecard SVG: {written_svg}")
        print(f"Scorecard HTML: {written_html}")
        return
