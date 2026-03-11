from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from econharness.scanner import scan_project


FIXTURES = Path(__file__).parent / "fixtures"


class HarnessTests(unittest.TestCase):
    def test_good_project_scores_higher_than_bad_project(self) -> None:
        good = scan_project(FIXTURES / "good_project")
        bad = scan_project(FIXTURES / "bad_project")
        self.assertGreater(good.overall_score, bad.overall_score)
        self.assertLess(len(good.findings), len(bad.findings))

    def test_bad_project_flags_absolute_paths_and_manual_steps(self) -> None:
        bad = scan_project(FIXTURES / "bad_project")
        titles = {finding.title for finding in bad.findings}
        self.assertIn("Absolute path embedded in project source", titles)
        self.assertIn("Manual project step documented in source", titles)

    def test_good_project_passes_key_environment_checks(self) -> None:
        good = scan_project(FIXTURES / "good_project")
        titles = {finding.title for finding in good.findings}
        self.assertNotIn("Missing R environment lockfile", titles)
        self.assertNotIn("Missing Python reproducible environment metadata", titles)

    def test_relational_dataset_duplicates_are_detected(self) -> None:
        bad = scan_project(FIXTURES / "bad_project")
        titles = {finding.title for finding in bad.findings}
        self.assertIn("Dataset primary key is not unique", titles)

    def test_writes_into_raw_paths_are_detected(self) -> None:
        bad = scan_project(FIXTURES / "bad_project")
        titles = {finding.title for finding in bad.findings}
        self.assertIn("Code appears to write into raw-data paths", titles)

    def test_research_workflow_specific_findings_are_detected(self) -> None:
        bad = scan_project(FIXTURES / "bad_project")
        titles = {finding.title for finding in bad.findings}
        self.assertIn("Early merged dataset has many upstream parents", titles)
        self.assertIn("Analysis script performs repeated merges", titles)
        self.assertIn("Repeated sample-construction logic across scripts", titles)
        self.assertIn("Paper references non-output artifacts directly", titles)
        self.assertIn("Stata script changes directory explicitly", titles)

    def test_scan_command_persists_state(self) -> None:
        project = FIXTURES / "good_project"
        result = subprocess.run(
            [sys.executable, "-m", "econharness", "scan", "--path", str(project)],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        state_path = project / ".econharness" / "state.json"
        self.assertTrue(state_path.exists())
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("overall_score", payload)

    def test_verify_fast_and_full_commands(self) -> None:
        project = FIXTURES / "good_project"
        fast = subprocess.run(
            [sys.executable, "-m", "econharness", "verify", "--path", str(project), "--profile", "fast"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(fast.returncode, 0, fast.stderr)
        self.assertIn("FAST_OK", fast.stdout)

        full = subprocess.run(
            [sys.executable, "-m", "econharness", "verify", "--path", str(project), "--profile", "full"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("FULL_OK", full.stdout)


if __name__ == "__main__":
    unittest.main()
