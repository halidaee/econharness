from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
import json
from econharness.history import (
    append_history,
    compute_delta,
    load_history,
    make_snapshot,
)
from econharness.scanner import scan_project


FIXTURES = Path(__file__).parent / "fixtures"


def _make_fake_snapshot(score: float, findings: list[dict] | None = None) -> dict:
    return {
        "scanned_at": "2026-03-21T10:00:00+00:00",
        "project_root": "/fake/project",
        "overall_score": score,
        "dimension_scores": {"automation": score},
        "findings": findings or [],
        "summary": {"findings": len(findings or []), "high_severity": 0},
    }


class HistoryUnitTests(unittest.TestCase):
    def test_append_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            snap = _make_fake_snapshot(75.0)
            append_history(project, snap)
            history = load_history(project)
            self.assertEqual(len(history), 1)
            self.assertAlmostEqual(history[0]["overall_score"], 75.0)

    def test_pruning_at_11th_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            for i in range(11):
                snap = _make_fake_snapshot(float(i))
                append_history(project, snap)
            history = load_history(project)
            self.assertEqual(len(history), 10)
            # Oldest (score=0) should be pruned, newest (score=10) retained
            self.assertAlmostEqual(history[-1]["overall_score"], 10.0)
            self.assertAlmostEqual(history[0]["overall_score"], 1.0)

    def test_corrupted_line_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            append_history(project, _make_fake_snapshot(50.0))
            # Inject a corrupted line
            hist_path = project / ".econharness" / "history.jsonl"
            content = hist_path.read_text(encoding="utf-8")
            hist_path.write_text("{corrupted\n" + content, encoding="utf-8")
            history = load_history(project)
            self.assertEqual(len(history), 1)
            self.assertAlmostEqual(history[0]["overall_score"], 50.0)

    def test_compute_delta_score_and_dims(self) -> None:
        prev = _make_fake_snapshot(70.0)
        curr = _make_fake_snapshot(75.0)
        delta = compute_delta(prev, curr)
        self.assertAlmostEqual(delta["score_delta"], 5.0)
        self.assertIn("automation", delta["dimension_deltas"])

    def test_compute_delta_new_and_resolved_findings(self) -> None:
        f1 = {"id": "dim:old:project", "title": "Old"}
        f2 = {"id": "dim:new:project", "title": "New"}
        prev = _make_fake_snapshot(70.0, findings=[f1])
        curr = _make_fake_snapshot(72.0, findings=[f2])
        delta = compute_delta(prev, curr)
        self.assertEqual(len(delta["new_findings"]), 1)
        self.assertEqual(delta["new_findings"][0]["id"], "dim:new:project")
        self.assertEqual(len(delta["resolved_findings"]), 1)
        self.assertEqual(delta["resolved_findings"][0]["id"], "dim:old:project")

    def test_no_delta_on_identical_snapshots(self) -> None:
        snap = _make_fake_snapshot(80.0)
        delta = compute_delta(snap, snap)
        self.assertEqual(delta["score_delta"], 0.0)
        self.assertEqual(delta["dimension_deltas"], {})
        self.assertEqual(delta["new_findings"], [])
        self.assertEqual(delta["resolved_findings"], [])


class HistoryCLITests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "econharness", *args],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

    def _fresh_project(self) -> str:
        """Create a fresh project dir with a minimal valid config. Returns tmpdir path."""
        tmpdir = tempfile.mkdtemp()
        cfg = default_config()
        cfg["pipeline"]["command"]["fast"] = "echo ok"
        cfg["pipeline"]["command"]["full"] = "echo ok"
        (Path(tmpdir) / ".econharness.yml").write_text(json.dumps(cfg), encoding="utf-8")
        return tmpdir

    def test_scan_appends_to_history(self) -> None:
        tmpdir = self._fresh_project()
        self._run("scan", "--path", tmpdir)
        history = load_history(Path(tmpdir))
        self.assertEqual(len(history), 1)
        self.assertIn("overall_score", history[0])
        self.assertIn("scanned_at", history[0])

    def test_scan_json_includes_delta_null_on_first(self) -> None:
        tmpdir = self._fresh_project()
        result = self._run("scan", "--path", tmpdir, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("delta", payload)
        self.assertIsNone(payload["delta"])

    def test_scan_json_includes_delta_on_second_scan(self) -> None:
        tmpdir = self._fresh_project()
        self._run("scan", "--path", tmpdir)
        result = self._run("scan", "--path", tmpdir, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIsNotNone(payload["delta"])
        self.assertIn("score_delta", payload["delta"])
        self.assertIn("new_findings", payload["delta"])
        self.assertIn("resolved_findings", payload["delta"])

    def test_status_diff_requires_two_scans(self) -> None:
        tmpdir = self._fresh_project()
        self._run("scan", "--path", tmpdir)
        result = self._run("status", "--path", tmpdir, "--diff")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Not enough scan history", result.stdout)

    def test_status_diff_after_two_scans(self) -> None:
        tmpdir = self._fresh_project()
        self._run("scan", "--path", tmpdir)
        self._run("scan", "--path", tmpdir)
        result = self._run("status", "--path", tmpdir, "--diff")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Delta since last scan", result.stdout)

    def test_status_diff_json(self) -> None:
        tmpdir = self._fresh_project()
        self._run("scan", "--path", tmpdir)
        self._run("scan", "--path", tmpdir)
        result = self._run("status", "--path", tmpdir, "--diff", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("score_delta", payload)
        self.assertIn("dimension_deltas", payload)


if __name__ == "__main__":
    unittest.main()
