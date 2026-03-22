from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from econharness.config import default_config
from econharness.scanner import scan_project
from econharness.state import findings_from_state, save_scan_result, scan_result_from_state, load_state
from econharness.suppressions import (
    active_suppressed_ids,
    is_active,
    load_suppressions,
    parse_duration,
    save_suppressions,
)


FIXTURES = Path(__file__).parent / "fixtures"


class SuppressionUnitTests(unittest.TestCase):
    def test_is_active_no_expiry(self) -> None:
        self.assertTrue(is_active({"suppressed_at": "2026-01-01"}))

    def test_is_active_future_expiry(self) -> None:
        future = (date.today() + timedelta(days=10)).isoformat()
        self.assertTrue(is_active({"expires": future}))

    def test_is_active_past_expiry(self) -> None:
        past = (date.today() - timedelta(days=1)).isoformat()
        self.assertFalse(is_active({"expires": past}))

    def test_parse_duration_days(self) -> None:
        result = parse_duration("90d")
        self.assertEqual(result, date.today() + timedelta(days=90))

    def test_parse_duration_year(self) -> None:
        result = parse_duration("1y")
        self.assertEqual(result, date.today() + timedelta(days=365))

    def test_parse_duration_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("invalid")

    def test_active_suppressed_ids_filters_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            past = (date.today() - timedelta(days=1)).isoformat()
            future = (date.today() + timedelta(days=1)).isoformat()
            save_suppressions(project, {
                "dim:active-id:project": {"suppressed_at": "2026-01-01"},
                "dim:expired-id:project": {"suppressed_at": "2026-01-01", "expires": past},
                "dim:future-id:project": {"suppressed_at": "2026-01-01", "expires": future},
            })
            ids = active_suppressed_ids(project)
            self.assertIn("dim:active-id:project", ids)
            self.assertNotIn("dim:expired-id:project", ids)
            self.assertIn("dim:future-id:project", ids)


class SuppressionIntegrationTests(unittest.TestCase):
    def test_suppressed_finding_excluded_from_findings_from_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            result = scan_project(FIXTURES / "bad_project")
            save_scan_result(project, result)
            findings_before = findings_from_state(project)
            self.assertGreater(len(findings_before), 0)

            # Suppress the top finding
            target_id = findings_before[0].id
            save_suppressions(project, {target_id: {"suppressed_at": date.today().isoformat()}})

            findings_after = findings_from_state(project)
            ids_after = {f.id for f in findings_after}
            self.assertNotIn(target_id, ids_after)
            self.assertEqual(len(findings_after), len(findings_before) - 1)

    def test_suppression_survives_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Scan, suppress, rescan
            result = scan_project(FIXTURES / "bad_project")
            save_scan_result(project, result)
            target_id = findings_from_state(project)[0].id
            save_suppressions(project, {target_id: {"suppressed_at": date.today().isoformat()}})

            result2 = scan_project(FIXTURES / "bad_project")
            save_scan_result(project, result2)

            # Suppression file should be unchanged
            suppressions = load_suppressions(project)
            self.assertIn(target_id, suppressions)

            # Suppressed finding should still be excluded
            findings = findings_from_state(project)
            self.assertNotIn(target_id, {f.id for f in findings})

    def test_score_excludes_suppressed_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Scan project directly so project_root in state matches tmpdir
            import shutil
            shutil.copytree(str(FIXTURES / "bad_project"), tmpdir, dirs_exist_ok=True)
            result = scan_project(project)
            save_scan_result(project, result)
            state = load_state(project)
            assert state is not None
            unsuppressed_result = scan_result_from_state(state)
            base_score = unsuppressed_result.overall_score

            # Suppress a high-impact finding
            high_impact = max(result.findings, key=lambda f: f.score_impact)
            save_suppressions(project, {high_impact.id: {"suppressed_at": date.today().isoformat()}})

            state2 = load_state(project)
            assert state2 is not None
            suppressed_result = scan_result_from_state(state2)
            # Score should be higher (less penalized) after suppression
            self.assertGreaterEqual(suppressed_result.overall_score, base_score)
            self.assertEqual(suppressed_result.summary.get("suppressed"), 1)

    def test_expired_suppression_reappears_in_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            result = scan_project(FIXTURES / "bad_project")
            save_scan_result(project, result)
            target_id = findings_from_state(project)[0].id
            past = (date.today() - timedelta(days=1)).isoformat()
            save_suppressions(project, {target_id: {"suppressed_at": "2026-01-01", "expires": past}})

            # Should reappear since expiry is in the past
            findings = findings_from_state(project)
            self.assertIn(target_id, {f.id for f in findings})


class SuppressCLITests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "econharness", *args],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_suppress_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run("suppress", "test:finding-id:project", "--path", tmpdir, "--reason", "false positive")
            self.assertEqual(result.returncode, 0, result.stderr)

            result2 = self._run("suppress", "--list", "--path", tmpdir)
            self.assertEqual(result2.returncode, 0)
            self.assertIn("test:finding-id:project", result2.stdout)

    def test_suppress_list_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run("suppress", "test:finding:project", "--path", tmpdir)
            result = self._run("suppress", "--list", "--path", tmpdir, "--json")
            self.assertEqual(result.returncode, 0)
            items = json.loads(result.stdout)
            self.assertIsInstance(items, list)
            self.assertEqual(items[0]["id"], "test:finding:project")
            self.assertEqual(items[0]["status"], "active")

    def test_suppress_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run("suppress", "test:finding:project", "--path", tmpdir)
            result = self._run("suppress", "--remove", "test:finding:project", "--path", tmpdir)
            self.assertEqual(result.returncode, 0)
            suppressions = load_suppressions(Path(tmpdir))
            self.assertNotIn("test:finding:project", suppressions)

    def test_suppress_with_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run("suppress", "test:finding:project", "--path", tmpdir, "--expires", "30d")
            self.assertEqual(result.returncode, 0)
            suppressions = load_suppressions(Path(tmpdir))
            self.assertIn("expires", suppressions["test:finding:project"])

    def test_suppress_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run("suppress", "test:finding:project", "--path", tmpdir, "--json")
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["suppressed"], "test:finding:project")


if __name__ == "__main__":
    unittest.main()
