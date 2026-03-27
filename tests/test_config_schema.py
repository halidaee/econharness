from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config, load_config, render_default_config


class ConfigSchemaTests(unittest.TestCase):
    def test_default_config_uses_top_level_stages(self) -> None:
        config = default_config()
        self.assertIn("stages", config)
        self.assertEqual(config["stages"], [])
        self.assertNotIn("heavy_stages", config["pipeline"])

    def test_load_config_normalizes_legacy_heavy_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".econharness.yml").write_text(
                json.dumps(
                    {
                        "pipeline": {
                            "command": {"fast": "echo FAST", "full": "echo FULL"},
                            "heavy_stages": ["estimate_models", {"name": "bootstrap", "command": "run_bootstrap.sh"}],
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            config = load_config(project)
            by_name = {stage["name"]: stage for stage in config["stages"]}

            self.assertIn("estimate_models", by_name)
            self.assertTrue(by_name["estimate_models"]["slow"])
            self.assertEqual(by_name["estimate_models"]["match"], [])
            self.assertIn("bootstrap", by_name)
            self.assertTrue(by_name["bootstrap"]["slow"])
            self.assertEqual(by_name["bootstrap"]["command"], "run_bootstrap.sh")

    def test_render_default_config_emits_stages_schema(self) -> None:
        payload = json.loads(render_default_config())
        self.assertIn("stages", payload)
        self.assertEqual(payload["stages"], [])
        self.assertNotIn("heavy_stages", payload["pipeline"])

    def test_init_writes_config_with_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            result = subprocess.run(
                [sys.executable, "-m", "econharness", "init", "--path", str(project)],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            # init now writes YAML (loadable via load_config)
            from econharness.config import load_config
            config = load_config(project)
            self.assertIn("stages", config)
            self.assertEqual(config["stages"], [])
            self.assertNotIn("heavy_stages", config["pipeline"])


if __name__ == "__main__":
    unittest.main()
