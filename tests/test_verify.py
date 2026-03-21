from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from econharness.config import default_config
from econharness.verify import verify_project


class VerifyTests(unittest.TestCase):
    def test_from_scratch_verify_quarantines_and_reports_regenerated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            self._write_build_project(project, writes_output=True)
            (project / "derived").mkdir(parents=True)
            (project / "output").mkdir(parents=True)
            (project / "derived" / "model.txt").write_text("old\n", encoding="utf-8")
            (project / "output" / "table.csv").write_text("old\n", encoding="utf-8")

            result = verify_project(project, "full", from_scratch=True)

            self.assertEqual(result.returncode, 0)
            self.assertIsNotNone(result.quarantine_dir)
            self.assertIn("derived/model.txt", result.moved_paths)
            self.assertIn("output/table.csv", result.moved_paths)
            self.assertIn("derived/model.txt", result.regenerated_paths)
            self.assertIn("output/table.csv", result.regenerated_paths)
            self.assertEqual(result.missing_paths, ())

    def test_from_scratch_verify_reports_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            self._write_build_project(project, writes_output=False)
            (project / "derived").mkdir(parents=True)
            (project / "output").mkdir(parents=True)
            (project / "derived" / "model.txt").write_text("old\n", encoding="utf-8")
            (project / "output" / "table.csv").write_text("old\n", encoding="utf-8")

            result = verify_project(project, "full", from_scratch=True)

            self.assertEqual(result.returncode, 0)
            self.assertIn("output/table.csv", result.missing_paths)

    def test_clean_tree_check_reports_tracked_file_modifications(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            self._write_build_project(project, writes_output=False, tracked_mutation=True)
            tracked = project / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")

            subprocess.run(["git", "init"], cwd=project, text=True, capture_output=True, check=True)
            subprocess.run(["git", "add", "."], cwd=project, text=True, capture_output=True, check=True)
            subprocess.run(
                ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test User", "commit", "-m", "init"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )

            result = verify_project(project, "full", check_clean_tree=True)

            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.clean_tree_before)
            self.assertFalse(result.clean_tree_after)
            self.assertTrue(result.git_status_after)

    def test_from_scratch_refuses_generated_roots_that_overlap_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            self._write_build_project(project, writes_output=False)

            config = default_config()
            config["paths"]["raw"] = "data"
            config["paths"]["derived"] = "data/derived"
            config["pipeline"]["command"]["full"] = "python3 build.py"
            config["pipeline"]["command"]["fast"] = "python3 build.py"
            (project / ".econharness.yml").write_text(json.dumps(config) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "overlaps raw-data root"):
                verify_project(project, "full", from_scratch=True)

    def _write_build_project(self, project: Path, *, writes_output: bool, tracked_mutation: bool = False) -> None:
        config = default_config()
        config["pipeline"]["command"]["full"] = "python3 build.py"
        config["pipeline"]["command"]["fast"] = "python3 build.py"
        (project / ".econharness.yml").write_text(json.dumps(config) + "\n", encoding="utf-8")

        lines = [
            "from pathlib import Path",
            "Path('derived').mkdir(parents=True, exist_ok=True)",
            "Path('derived/model.txt').write_text('fresh\\n', encoding='utf-8')",
        ]
        if writes_output:
            lines.extend(
                [
                    "Path('output').mkdir(parents=True, exist_ok=True)",
                    "Path('output/table.csv').write_text('fresh\\n', encoding='utf-8')",
                ]
            )
        if tracked_mutation:
            lines.append("Path('tracked.txt').write_text('changed\\n', encoding='utf-8')")
        (project / "build.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
