from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config, load_config
from econharness.detectors import detect_slow_stage_discipline


class SlowStageTests(unittest.TestCase):
    def test_slow_stage_requires_fast_verification_path(self) -> None:
        config = default_config()
        config["pipeline"]["command"]["full"] = "python3 build.py"
        config["pipeline"]["command"]["fast"] = ""
        config["stages"] = [
            {
                "name": "estimate_models",
                "match": [],
                "read_roots": ["derived"],
                "write_roots": ["derived/models"],
                "slow": True,
                "command": "python3 models.py",
                "inputs": [],
                "outputs": ["derived/models"],
            }
        ]

        findings = detect_slow_stage_discipline(config)
        titles = {finding.title for finding in findings}

        self.assertIn("Slow stage is declared without a fast verification path", titles)
        self.assertNotIn("Missing fast verification command", titles)

    def test_slow_stage_requires_outputs(self) -> None:
        config = default_config()
        config["pipeline"]["command"]["full"] = "python3 build.py"
        config["pipeline"]["command"]["fast"] = "python3 smoke.py"
        config["stages"] = [
            {
                "name": "bootstrap",
                "match": [],
                "read_roots": ["derived"],
                "write_roots": ["temp/bootstrap"],
                "slow": True,
                "command": "python3 bootstrap.py",
                "inputs": [],
                "outputs": [],
            }
        ]

        findings = detect_slow_stage_discipline(config)
        titles = {finding.title for finding in findings}

        self.assertIn("Slow stage does not declare outputs", titles)

    def test_slow_stage_requires_reusable_outputs(self) -> None:
        config = default_config()
        config["pipeline"]["command"]["full"] = "python3 build.py"
        config["pipeline"]["command"]["fast"] = "python3 smoke.py"
        config["stages"] = [
            {
                "name": "simulation",
                "match": [],
                "read_roots": ["derived"],
                "write_roots": ["temp/simulation"],
                "slow": True,
                "command": "python3 simulate.py",
                "inputs": [],
                "outputs": ["temp/simulation"],
            }
        ]

        findings = detect_slow_stage_discipline(config)
        titles = {finding.title for finding in findings}

        self.assertIn("Slow stage has no reusable artifact roots", titles)

    def test_well_configured_slow_stage_has_no_findings(self) -> None:
        config = default_config()
        config["pipeline"]["command"]["full"] = "python3 build.py"
        config["pipeline"]["command"]["fast"] = "python3 smoke.py"
        config["stages"] = [
            {
                "name": "estimate_models",
                "match": [],
                "read_roots": ["derived"],
                "write_roots": ["derived/models"],
                "slow": True,
                "command": "python3 models.py",
                "inputs": ["derived/clean"],
                "outputs": ["derived/models", "output/model_summaries"],
            }
        ]

        findings = detect_slow_stage_discipline(config)

        self.assertEqual(findings, [])

    def test_legacy_heavy_stage_config_still_triggers_slow_stage_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".econharness.yml").write_text(
                json.dumps(
                    {
                        "pipeline": {
                            "command": {"full": "python3 build.py", "fast": ""},
                            "heavy_stages": [
                                {
                                    "name": "bootstrap",
                                    "command": "python3 bootstrap.py",
                                    "outputs": ["derived/bootstrap"],
                                }
                            ],
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            findings = detect_slow_stage_discipline(load_config(project))
            titles = {finding.title for finding in findings}

            self.assertIn("Slow stage is declared without a fast verification path", titles)


if __name__ == "__main__":
    unittest.main()
