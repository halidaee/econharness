from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.config import bootstrap_config, load_config
from econharness.detectors import detect_ambiguous_pipeline
from econharness.scanner import scan_project


class BootstrapConfigTests(unittest.TestCase):
    def _project(self) -> Path:
        return Path(tempfile.mkdtemp())

    def test_single_makefile_populates_commands(self) -> None:
        project = self._project()
        (project / "Makefile").touch()
        result = bootstrap_config(project)
        self.assertIn('fast: "make fast"', result)
        self.assertIn('full: "make"', result)
        self.assertIn('tests: "make test"', result)
        self.assertIn("detected: Makefile", result)

    def test_run_all_r_populates_commands(self) -> None:
        project = self._project()
        (project / "run_all.R").touch()
        result = bootstrap_config(project)
        self.assertIn('fast: "Rscript run_all.R"', result)
        self.assertIn("detected: run_all.R", result)

    def test_multiple_entry_points_leaves_commands_blank(self) -> None:
        project = self._project()
        (project / "Makefile").touch()
        (project / "run_all.R").touch()
        result = bootstrap_config(project)
        self.assertIn('fast: ""', result)
        self.assertIn('full: ""', result)
        self.assertIn("WARNING: multiple pipeline entry points detected", result)

    def test_no_entry_point_leaves_commands_blank(self) -> None:
        project = self._project()
        result = bootstrap_config(project)
        self.assertIn('fast: ""', result)
        self.assertIn("no pipeline entry point detected", result)

    def test_pixi_toml_detected(self) -> None:
        project = self._project()
        (project / "pixi.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
        result = bootstrap_config(project)
        self.assertIn("manager: pixi", result)
        self.assertIn("detected: pixi.toml", result)

    def test_renv_lock_detected(self) -> None:
        project = self._project()
        (project / "renv.lock").write_text("{}", encoding="utf-8")
        result = bootstrap_config(project)
        self.assertIn("manager: renv", result)
        self.assertIn("detected: renv.lock", result)

    def test_existing_stage_dir_annotated(self) -> None:
        project = self._project()
        (project / "derived").mkdir()
        result = bootstrap_config(project)
        self.assertIn("derived: derived  # directory exists", result)

    def test_missing_stage_dir_annotated(self) -> None:
        project = self._project()
        result = bootstrap_config(project)
        self.assertIn("raw: raw  # directory not found", result)

    def test_data_subdir_variant_detected(self) -> None:
        project = self._project()
        (project / "data" / "raw").mkdir(parents=True)
        result = bootstrap_config(project)
        self.assertIn("raw: data/raw  # directory exists", result)

    def test_bootstrap_config_is_valid_yaml_loadable(self) -> None:
        """bootstrap_config output should be loadable by load_config."""
        project = self._project()
        (project / "Makefile").touch()
        yaml_text = bootstrap_config(project)
        (project / ".econharness.yml").write_text(yaml_text, encoding="utf-8")
        config = load_config(project)
        self.assertEqual(config["pipeline"]["command"]["fast"], "make fast")


class DetectAmbiguousPipelineTests(unittest.TestCase):
    def test_single_entry_point_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "Makefile").touch()
            findings = detect_ambiguous_pipeline(project, {})
            self.assertEqual(findings, [])

    def test_multiple_entry_points_high_severity_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "Makefile").touch()
            (project / "run_all.R").touch()
            findings = detect_ambiguous_pipeline(project, {})
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "high")
            self.assertEqual(findings[0].dimension, "automation")
            self.assertIn("Makefile", findings[0].detail)
            self.assertIn("run_all.R", findings[0].detail)

    def test_no_entry_points_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = detect_ambiguous_pipeline(Path(tmpdir), {})
            self.assertEqual(findings, [])

    def test_scan_includes_ambiguous_pipeline_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "Makefile").touch()
            (project / "run_all.R").touch()
            result = scan_project(project)
            titles = {f.title for f in result.findings}
            self.assertIn("Ambiguous authoritative pipeline", titles)


if __name__ == "__main__":
    unittest.main()
