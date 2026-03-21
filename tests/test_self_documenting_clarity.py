from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import (
    detect_self_documenting_clarity,
    iter_project_files,
)


class SelfDocumentingClarityTests(unittest.TestCase):
    def test_generic_code_filename_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "script2.py").write_text("value = 1\n", encoding="utf-8")

            files = list(iter_project_files(project, []))
            findings = detect_self_documenting_clarity(project, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Code filename is too generic", titles)

    def test_generic_top_level_function_names_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "helpers.py").write_text(
                "\n".join(
                    [
                        "def helper(df):",
                        "    return df",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (project / "analysis" / "transform.R").write_text(
                "\n".join(
                    [
                        "run <- function(df) {",
                        "  df",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_self_documenting_clarity(project, files)

            function_findings = [finding for finding in findings if finding.title == "Function name is too generic"]
            self.assertEqual(len(function_findings), 2)

    def test_main_and_test_helpers_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "tests").mkdir(parents=True)
            (project / "analysis" / "cli.py").write_text(
                "\n".join(
                    [
                        "def main():",
                        "    return 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (project / "tests" / "test_helpers.py").write_text(
                "\n".join(
                    [
                        "def helper(df):",
                        "    return df",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_self_documenting_clarity(project, files)

            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
