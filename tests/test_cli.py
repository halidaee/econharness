from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
from econharness.detectors import detect_software_hygiene
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
        self.assertTrue((project / ".econharness" / "scorecard.svg").exists())
        self.assertTrue((project / ".econharness" / "scorecard.html").exists())
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

    def test_verify_command_supports_from_scratch_and_clean_tree_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            config = default_config()
            config["pipeline"]["command"]["full"] = "python3 build.py"
            config["pipeline"]["command"]["fast"] = "python3 build.py"
            (project / ".econharness.yml").write_text(json.dumps(config) + "\n", encoding="utf-8")
            (project / "build.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "Path('derived').mkdir(parents=True, exist_ok=True)",
                        "Path('derived/model.txt').write_text('fresh\\n', encoding='utf-8')",
                        "Path('output').mkdir(parents=True, exist_ok=True)",
                        "Path('output/table.csv').write_text('fresh\\n', encoding='utf-8')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (project / "derived").mkdir(parents=True)
            (project / "output").mkdir(parents=True)
            (project / "derived" / "model.txt").write_text("old\n", encoding="utf-8")
            (project / "output" / "table.csv").write_text("old\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "econharness",
                    "verify",
                    "--path",
                    str(project),
                    "--profile",
                    "full",
                    "--from-scratch",
                    "--check-clean-tree",
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("From scratch: yes", result.stdout)
            self.assertIn("Moved artifacts: 2", result.stdout)
            self.assertIn("Regenerated artifacts: 2", result.stdout)
            self.assertIn("Missing regenerated artifacts: 0", result.stdout)
            self.assertIn("Clean tree before: unavailable", result.stdout)
            self.assertIn("Clean tree after: unavailable", result.stdout)

    def test_scorecard_command_supports_custom_paths(self) -> None:
        project = FIXTURES / "good_project"
        svg_path = project / ".econharness" / "custom-scorecard.svg"
        html_path = project / ".econharness" / "custom-scorecard.html"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "econharness",
                "scorecard",
                "--path",
                str(project),
                "--svg-path",
                str(svg_path),
                "--html-path",
                str(html_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(svg_path.exists())
        self.assertTrue(html_path.exists())

    def test_default_excludes_skip_environment_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".pixi" / "envs" / "default" / "lib").mkdir(parents=True)
            (project / "renv" / "library").mkdir(parents=True)
            (project / "analysis").mkdir(parents=True)

            (project / ".pixi" / "envs" / "default" / "lib" / "noise.py").write_text(
                "# edit this manually\nimport os\n", encoding="utf-8"
            )
            (project / "renv" / "library" / "noise.R").write_text(
                "# run this manually\n", encoding="utf-8"
            )
            (project / "analysis" / "main.py").write_text(
                "from pathlib import Path\nprint(Path('ok'))\n", encoding="utf-8"
            )

            result = scan_project(project)

            scanned_paths = {finding.path for finding in result.findings if finding.path}
            self.assertNotIn(".pixi/envs/default/lib/noise.py", scanned_paths)
            self.assertNotIn("renv/library/noise.R", scanned_paths)

    def test_oversized_code_script_uses_tiered_severity_and_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            def write_script(name: str, line_count: int) -> Path:
                path = project / name
                lines = [f"value_{name.replace('.', '_')}_{i:04d} <- {i}" for i in range(line_count)]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return path

            files = [
                write_script("below_threshold.R", 249),
                write_script("low_threshold.R", 250),
                write_script("medium_threshold.R", 500),
                write_script("high_threshold.R", 1000),
            ]

            findings = [
                finding
                for finding in detect_software_hygiene(project, files)
                if finding.title == "Oversized code script"
            ]
            by_path = {finding.path: finding for finding in findings}

            self.assertNotIn("below_threshold.R", by_path)
            self.assertEqual(by_path["low_threshold.R"].severity, "low")
            self.assertEqual(by_path["low_threshold.R"].score_impact, 2)
            self.assertEqual(by_path["medium_threshold.R"].severity, "medium")
            self.assertEqual(by_path["medium_threshold.R"].score_impact, 4)
            self.assertEqual(by_path["high_threshold.R"].severity, "high")
            self.assertEqual(by_path["high_threshold.R"].score_impact, 8)

    def test_repeated_derived_lookup_reconstruction_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            analysis = project / "analysis"
            analysis.mkdir(parents=True)

            (analysis / "quality_a.R").write_text(
                "\n".join(
                    [
                        'prod_data <- readRDS("derived/data_production_restricted.rds")',
                        'cross_scored <- readRDS("output/production_cross_scored.rds")',
                        "prod_data <- prod_data %>%",
                        "  mutate(quality_index = rowMeans(across(all_of(COMPOSITE_SCORES)), na.rm = TRUE))",
                        "breaks <- quantile(prod_data$quality_index, probs = seq(0, 1, 0.2), na.rm = TRUE)",
                        "prod_data <- prod_data %>%",
                        "  mutate(quality_quint = cut(quality_index, breaks = breaks, include.lowest = TRUE, labels = 1:5))",
                        'cross_scored <- cross_scored %>% left_join(prod_data %>% select(application_id, quality_index, quality_quint), by = "application_id")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (analysis / "quality_b.R").write_text(
                "\n".join(
                    [
                        'group_out <- readRDS("output/shap_group_nsim500.rds")',
                        'prod_data_quality <- readRDS("derived/data_production_restricted.rds")',
                        "prod_data_quality <- prod_data_quality %>%",
                        "  mutate(quality_index = rowMeans(across(all_of(COMPOSITE_SCORES)), na.rm = TRUE))",
                        "quality_breaks <- quantile(prod_data_quality$quality_index, probs = seq(0, 1, 0.2), na.rm = TRUE)",
                        "prod_data_quality <- prod_data_quality %>%",
                        "  mutate(quality_quint = cut(quality_index, breaks = quality_breaks, include.lowest = TRUE, labels = 1:5))",
                        "quality_lookup <- prod_data_quality %>% select(application_id, quality_quint)",
                        'plot_data <- group_out %>% left_join(quality_lookup, by = "application_id")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = scan_project(project)
            findings = [finding for finding in result.findings if finding.title == "Repeated derived lookup reconstruction across scripts"]

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "low")
            self.assertIn("data_production_restricted.rds", findings[0].detail)
            self.assertIn("quality_quint", findings[0].detail)

    def test_base_r_repeated_lookup_reconstruction_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            analysis = project / "analysis"
            analysis.mkdir(parents=True)

            script_template = "\n".join(
                [
                    'plot_data <- readRDS("output/shap_group_nsim500.rds")',
                    'prod_data <- readRDS("derived/data_production_restricted.rds")',
                    'prod_data$quality_index <- rowMeans(prod_data[c("score_a", "score_b")], na.rm = TRUE)',
                    "breaks <- quantile(prod_data$quality_index, probs = seq(0, 1, 0.2), na.rm = TRUE)",
                    'prod_data$quality_quint <- cut(prod_data$quality_index, breaks = breaks, include.lowest = TRUE, labels = 1:5)',
                    'quality_lookup <- prod_data[c("application_id", "quality_quint")]',
                    'plot_data <- merge(plot_data, quality_lookup, by = "application_id", all.x = TRUE)',
                    "",
                ]
            )

            (analysis / "base_quality_a.R").write_text(script_template, encoding="utf-8")
            (analysis / "base_quality_b.R").write_text(script_template, encoding="utf-8")

            findings = [
                finding
                for finding in scan_project(project).findings
                if finding.title == "Repeated derived lookup reconstruction across scripts"
            ]

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "low")
            self.assertIn("data_production_restricted.rds", findings[0].detail)
            self.assertIn("quality_quint", findings[0].detail)

    def test_pandas_repeated_lookup_reconstruction_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            analysis = project / "analysis"
            analysis.mkdir(parents=True)

            (analysis / "quality_lookup_a.py").write_text(
                "\n".join(
                    [
                        "import pandas as pd",
                        "",
                        'scores = pd.read_parquet("output/production_scores.parquet")',
                        'prod = pd.read_parquet("derived/data_production_restricted.parquet")',
                        'prod["quality_index"] = prod[["score_a", "score_b"]].mean(axis=1)',
                        'prod["quality_quint"] = pd.qcut(prod["quality_index"], q=5, labels=False, duplicates="drop")',
                        'quality_lookup = prod[["application_id", "quality_quint"]]',
                        'scores = scores.merge(quality_lookup, on="application_id", how="left")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (analysis / "quality_lookup_b.py").write_text(
                "\n".join(
                    [
                        "import pandas as pd",
                        "",
                        'explain = pd.read_parquet("output/group_shap.parquet")',
                        'prod = pd.read_parquet("derived/data_production_restricted.parquet")',
                        'prod = prod.assign(quality_index=prod[["score_a", "score_b"]].mean(axis=1))',
                        'prod["quality_quint"] = pd.qcut(prod["quality_index"], q=5, labels=False, duplicates="drop")',
                        'explain = explain.merge(prod[["application_id", "quality_quint"]], on="application_id", how="left")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            findings = [
                finding
                for finding in scan_project(project).findings
                if finding.title == "Repeated derived lookup reconstruction across scripts"
            ]

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "low")
            self.assertIn("data_production_restricted.parquet", findings[0].detail)
            self.assertIn("quality_quint", findings[0].detail)

    def test_repeated_lookup_reconstruction_uses_structural_severity_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            analysis = project / "analysis"
            analysis.mkdir(parents=True)

            script_body = "\n".join(
                [
                    'plot_data <- readRDS("output/shap_group_nsim500.rds")',
                    'prod_data <- readRDS("derived/data_production_restricted.rds")',
                    'prod_data$quality_index <- rowMeans(prod_data[c("score_a", "score_b")], na.rm = TRUE)',
                    "breaks <- quantile(prod_data$quality_index, probs = seq(0, 1, 0.2), na.rm = TRUE)",
                    'prod_data$quality_quint <- cut(prod_data$quality_index, breaks = breaks, include.lowest = TRUE, labels = 1:5)',
                    'quality_lookup <- prod_data[c("application_id", "quality_quint")]',
                    'plot_data <- merge(plot_data, quality_lookup, by = "application_id", all.x = TRUE)',
                    "",
                ]
            )

            for index in range(5):
                (analysis / f"quality_{index}.R").write_text(script_body, encoding="utf-8")

            findings = [
                finding
                for finding in scan_project(project).findings
                if finding.title == "Repeated derived lookup reconstruction across scripts"
            ]

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "high")
            self.assertEqual(findings[0].score_impact, 12)

    def test_trivial_repeated_lookup_joins_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            analysis = project / "analysis"
            analysis.mkdir(parents=True)

            (analysis / "train_a.R").write_text(
                "\n".join(
                    [
                        'eval_data <- readRDS("derived/data_evaluation_restricted.rds")',
                        "feature_data <- prepare_features(eval_data, COMPOSITE_SCORES, include_questions = TRUE)",
                        'feature_data <- feature_data %>% left_join(eval_data %>% select(application_id, tenure_leq_90), by = "application_id")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (analysis / "train_b.R").write_text(
                "\n".join(
                    [
                        'data_eval <- readRDS("derived/data_evaluation_restricted.rds")',
                        "feature_data <- prepare_features(data_eval, COMPOSITE_SCORES, include_questions = TRUE)",
                        'feature_data <- feature_data %>% left_join(data_eval %>% select(application_id, tenure_leq_90), by = "application_id")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            titles = {finding.title for finding in scan_project(project).findings}
            self.assertNotIn("Repeated derived lookup reconstruction across scripts", titles)


    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "econharness", *args],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_scan_json_output(self) -> None:
        project = FIXTURES / "good_project"
        result = self._run("scan", "--path", str(project), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("project_root", payload)
        self.assertIn("overall_score", payload)
        self.assertIn("dimension_scores", payload)
        self.assertIsInstance(payload["findings"], list)
        self.assertIn("summary", payload)
        # Scorecard paths should not appear in stdout when --json
        self.assertNotIn("Scorecard SVG", result.stdout)

    def test_status_json_output(self) -> None:
        project = FIXTURES / "good_project"
        # Ensure state exists first
        self._run("scan", "--path", str(project))
        result = self._run("status", "--path", str(project), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("project_root", payload)
        self.assertIn("overall_score", payload)
        self.assertIn("dimension_scores", payload)
        self.assertIsInstance(payload["findings"], int)

    def test_status_json_no_state_emits_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run("status", "--path", tmpdir, "--json")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("error", payload)

    def test_next_json_output(self) -> None:
        project = FIXTURES / "bad_project"
        # Ensure state exists
        self._run("scan", "--path", str(project))
        result = self._run("next", "--path", str(project), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("id", payload)
        self.assertIn("dimension", payload)
        self.assertIn("severity", payload)
        self.assertIn("title", payload)
        self.assertIn("remaining", payload)
        self.assertIsInstance(payload["remaining"], int)


if __name__ == "__main__":
    unittest.main()
