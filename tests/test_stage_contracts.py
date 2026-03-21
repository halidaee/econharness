from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
from econharness.detectors import detect_stage_contracts, iter_project_files


class StageContractTests(unittest.TestCase):
    def test_read_violation_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "main.py").write_text(
                "\n".join(
                    [
                        "import pandas as pd",
                        'df = pd.read_csv("raw/input.csv")',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = default_config()
            config["stages"] = [
                {
                    "name": "main_analysis",
                    "match": ["analysis/**"],
                    "read_roots": ["derived"],
                    "write_roots": ["output"],
                    "slow": False,
                    "command": "",
                    "inputs": [],
                    "outputs": [],
                }
            ]
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_stage_contracts(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Stage reads outside declared roots", titles)

    def test_write_violation_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "main.R").write_text(
                "\n".join(
                    [
                        "df <- readRDS('derived/input.rds')",
                        "saveRDS(df, 'temp/output.rds')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = default_config()
            config["stages"] = [
                {
                    "name": "main_analysis",
                    "match": ["analysis/**"],
                    "read_roots": ["derived"],
                    "write_roots": ["output"],
                    "slow": False,
                    "command": "",
                    "inputs": [],
                    "outputs": [],
                }
            ]
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_stage_contracts(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Stage writes outside declared roots", titles)

    def test_unmatched_code_file_is_flagged_when_stage_contracts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "scripts").mkdir(parents=True)
            (project / "scripts" / "helper.py").write_text("value = 1\n", encoding="utf-8")

            config = default_config()
            config["stages"] = [
                {
                    "name": "main_analysis",
                    "match": ["analysis/**"],
                    "read_roots": ["derived"],
                    "write_roots": ["output"],
                    "slow": False,
                    "command": "",
                    "inputs": [],
                    "outputs": [],
                }
            ]
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_stage_contracts(project, config, files)

            titles = {finding.title for finding in findings}
            self.assertIn("Code file is not assigned to a configured stage", titles)

    def test_compliant_stage_contracts_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "main.py").write_text(
                "\n".join(
                    [
                        "import pandas as pd",
                        'df = pd.read_csv("derived/input.csv")',
                        'df.to_csv("output/table.csv", index=False)',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = default_config()
            config["stages"] = [
                {
                    "name": "main_analysis",
                    "match": ["analysis/**"],
                    "read_roots": ["derived"],
                    "write_roots": ["output"],
                    "slow": False,
                    "command": "",
                    "inputs": [],
                    "outputs": [],
                }
            ]
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_stage_contracts(project, config, files)

            self.assertEqual(findings, [])

    def test_no_stage_contracts_means_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "analysis").mkdir(parents=True)
            (project / "analysis" / "main.py").write_text('print("ok")\n', encoding="utf-8")

            config = default_config()
            files = list(iter_project_files(project, config.get("exclude", [])))
            findings = detect_stage_contracts(project, config, files)

            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
