from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import detect_function_state_discipline, iter_project_files


class FunctionStateTests(unittest.TestCase):
    def test_python_global_writes_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "globals.py").write_text(
                "\n".join(
                    [
                        "CACHE = {}",
                        "",
                        "def update_cache(key, value):",
                        "    CACHE[key] = value",
                        "",
                        "def bump_counter():",
                        "    global RUN_COUNT",
                        "    RUN_COUNT = 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            self.assertEqual(len(findings), 2)
            self.assertTrue(all(finding.title == "Function writes to hidden global state" for finding in findings))

    def test_r_global_writes_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "globals.R").write_text(
                "\n".join(
                    [
                        "update_value <- function(x) {",
                        "  saved_value <<- x",
                        "}",
                        "",
                        "write_result <- function(x) {",
                        '  assign("result", x, envir = .GlobalEnv)',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            self.assertEqual(len(findings), 2)
            self.assertTrue(all(finding.title == "Function writes to hidden global state" for finding in findings))

    def test_local_mutation_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "locals.py").write_text(
                "\n".join(
                    [
                        "def build_local_state():",
                        "    cache = {}",
                        '    cache[\"x\"] = 1',
                        "    return cache",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            self.assertEqual(findings, [])

    def test_python_outer_scope_dependency_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "dependencies.py").write_text(
                "\n".join(
                    [
                        "threshold = 0.8",
                        "",
                        "def score_row(value):",
                        "    return value > threshold",
                        "",
                        "def keep_row(value):",
                        "    return value >= threshold",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Function depends on outer scope", titles)

    def test_r_outer_scope_dependency_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "dependencies.R").write_text(
                "\n".join(
                    [
                        "THRESHOLD <- 0.8",
                        "",
                        "score_row <- function(value) {",
                        "  value > THRESHOLD",
                        "}",
                        "",
                        "keep_row <- function(value) {",
                        "  value >= THRESHOLD",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Function depends on outer scope", titles)

    def test_explicit_arguments_and_single_constant_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "safe.py").write_text(
                "\n".join(
                    [
                        "SCALE = 2",
                        "",
                        "def scale_value(value, scale):",
                        "    return value * scale",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            files = list(iter_project_files(project, []))
            findings = detect_function_state_discipline(project, files)

            outer_scope_findings = [finding for finding in findings if finding.title == "Function depends on outer scope"]
            self.assertEqual(outer_scope_findings, [])


if __name__ == "__main__":
    unittest.main()
