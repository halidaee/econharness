from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
from econharness.detectors import detect_tests_presence, iter_project_files


class TestsPresenceTests(unittest.TestCase):
    def test_helper_heavy_project_without_tests_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "helpers.py").write_text(
                "\n".join(
                    [
                        "def clean_data(df):",
                        "    return df",
                        "",
                        "def score_rows(df):",
                        "    return df",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_tests_presence(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Helper-heavy project has no automated tests", titles)

    def test_test_files_without_command_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "tests").mkdir(parents=True)
            (project / "tests" / "test_helpers.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_tests_presence(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Test files exist without configured test command", titles)

    def test_tests_command_and_test_files_clear_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "tests").mkdir(parents=True)
            (project / "analysis" / "helpers.py").write_text(
                "\n".join(
                    [
                        "def clean_data(df):",
                        "    return df",
                        "",
                        "def score_rows(df):",
                        "    return df",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (project / "tests" / "test_helpers.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

            config = default_config()
            config["pipeline"]["command"]["tests"] = "python3 -m unittest"
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_tests_presence(project, config, files)

            self.assertEqual(findings, [])

    def test_research_files_with_test_in_name_are_not_treated_as_unit_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "raw").mkdir(parents=True)
            (project / "analysis" / "a6_ushape_test.R").write_text("value <- 1\n", encoding="utf-8")
            (project / "raw" / "test_id=123.csv").write_text("id\n1\n", encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_tests_presence(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertNotIn("Test files exist without configured test command", titles)


if __name__ == "__main__":
    unittest.main()
