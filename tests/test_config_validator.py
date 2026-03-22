from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from econharness.config_validator import validate_config_path


class ConfigValidatorTests(unittest.TestCase):
    def _project_with_config(self, text: str) -> Path:
        tmpdir = tempfile.mkdtemp()
        path = Path(tmpdir)
        (path / ".econharness.yml").write_text(text, encoding="utf-8")
        return path

    def test_valid_config_returns_no_errors(self) -> None:
        from econharness.config import render_default_config
        project = self._project_with_config(render_default_config())
        errors, warnings = validate_config_path(project)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_config_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            errors, warnings = validate_config_path(Path(tmpdir))
            self.assertEqual(len(errors), 1)
            self.assertIn("No config file found", errors[0])

    def test_parse_error_json_returns_error(self) -> None:
        project = self._project_with_config("{invalid json")
        errors, warnings = validate_config_path(project)
        self.assertEqual(len(errors), 1)
        self.assertIn("Parse error", errors[0])

    def test_type_error_pipeline_command_fast(self) -> None:
        cfg = {"pipeline": {"command": {"fast": ["bad", "type"], "full": "", "tests": ""}}}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("pipeline.command.fast" in e for e in errors))

    def test_type_error_stages_not_list(self) -> None:
        cfg = {"stages": "should-be-list"}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("stages" in e for e in errors))

    def test_type_error_stages_match_entry_not_str(self) -> None:
        cfg = {"stages": [{"name": "clean", "match": [123]}]}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("stages[0].match[0]" in e for e in errors))

    def test_type_error_scorecard_generate_not_bool(self) -> None:
        cfg = {"scorecard": {"generate": "yes"}}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("scorecard.generate" in e for e in errors))

    def test_unknown_top_level_key_is_warning_not_error(self) -> None:
        cfg = {"unknown_key": "value"}
        project = self._project_with_config(json.dumps(cfg))
        errors, warnings = validate_config_path(project)
        self.assertEqual(errors, [])
        self.assertTrue(any("unknown_key" in w for w in warnings))

    def test_conventions_type_errors(self) -> None:
        cfg = {"conventions": {"authoritative_pipeline": "yes", "allow_notebooks": 1}}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("conventions.authoritative_pipeline" in e for e in errors))
        self.assertTrue(any("conventions.allow_notebooks" in e for e in errors))

    def test_exclude_list_of_str_violation(self) -> None:
        cfg = {"exclude": ["ok", 42]}
        project = self._project_with_config(json.dumps(cfg))
        errors, _ = validate_config_path(project)
        self.assertTrue(any("exclude[1]" in e for e in errors))


class CheckConfigCLITests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "econharness", *args],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_check_config_ok_on_valid_config(self) -> None:
        good = Path(__file__).parent / "fixtures" / "good_project"
        result = self._run("check-config", "--path", str(good))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Config OK", result.stdout)

    def test_check_config_json_valid(self) -> None:
        good = Path(__file__).parent / "fixtures" / "good_project"
        result = self._run("check-config", "--path", str(good), "--json")
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["errors"], [])

    def test_check_config_json_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".econharness.yml").write_text('{"scorecard": {"generate": "bad"}}', encoding="utf-8")
            result = self._run("check-config", "--path", tmpdir, "--json")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(len(payload["errors"]) > 0)

    def test_scan_exits_on_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".econharness.yml").write_text('{"pipeline": {"command": {"fast": 99}}}', encoding="utf-8")
            result = self._run("scan", "--path", tmpdir)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Config error", result.stdout)

    def test_scan_json_exits_on_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".econharness.yml").write_text('{"pipeline": {"command": {"fast": 99}}}', encoding="utf-8")
            result = self._run("scan", "--path", tmpdir, "--json")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
