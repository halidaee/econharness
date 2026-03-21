from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
from econharness.detectors import detect_version_control_discipline, iter_project_files


class VersionControlTests(unittest.TestCase):
    def test_manual_versioned_filename_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "clean_data_v2.R").write_text("value <- 1\n", encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_version_control_discipline(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Filename appears to encode manual version history", titles)

    def test_parallel_filename_variants_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "clean_data_v2.R").write_text("value <- 1\n", encoding="utf-8")
            (project / "analysis" / "clean_data_final.R").write_text("value <- 2\n", encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_version_control_discipline(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Parallel filename variants suggest manual versioning", titles)

    def test_raw_inputs_and_paper_drafts_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "raw").mkdir(parents=True)
            (project / "paper").mkdir(parents=True)
            (project / "raw" / "raw_input_20240131.csv").write_text("id\n1\n", encoding="utf-8")
            (project / "paper" / "paper_draft.qmd").write_text("# Draft\n", encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_version_control_discipline(project, config, files)

            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
