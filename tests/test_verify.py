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


    def test_from_scratch_rollback_on_pipeline_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            config = default_config()
            config["pipeline"]["command"]["full"] = "python3 fail.py"
            config["pipeline"]["command"]["fast"] = "python3 fail.py"
            (project / ".econharness.yml").write_text(json.dumps(config) + "\n", encoding="utf-8")
            # fail.py writes one file then exits non-zero
            (project / "fail.py").write_text(
                "from pathlib import Path\n"
                "Path('derived').mkdir(parents=True, exist_ok=True)\n"
                "Path('derived/partial.txt').write_text('partial\\n', encoding='utf-8')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )
            (project / "derived").mkdir(parents=True)
            (project / "derived" / "original.txt").write_text("original\n", encoding="utf-8")

            result = verify_project(project, "full", from_scratch=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.rolled_back)
            # Original file should be restored
            self.assertTrue((project / "derived" / "original.txt").exists())
            self.assertEqual((project / "derived" / "original.txt").read_text(encoding="utf-8"), "original\n")
            # Quarantine dir should be cleaned up after rollback
            if result.quarantine_dir:
                self.assertFalse(Path(result.quarantine_dir).exists())

    def test_from_scratch_no_rollback_flag_leaves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            config = default_config()
            config["pipeline"]["command"]["full"] = "python3 fail.py"
            config["pipeline"]["command"]["fast"] = "python3 fail.py"
            (project / ".econharness.yml").write_text(json.dumps(config) + "\n", encoding="utf-8")
            (project / "fail.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
            (project / "derived").mkdir(parents=True)
            (project / "derived" / "original.txt").write_text("original\n", encoding="utf-8")

            result = verify_project(project, "full", from_scratch=True, no_rollback=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(result.rolled_back)
            # Original file should still be in quarantine, not restored
            self.assertFalse((project / "derived" / "original.txt").exists())

    def test_from_scratch_success_deletes_quarantine_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            self._write_build_project(project, writes_output=True)
            (project / "derived").mkdir(parents=True)
            (project / "output").mkdir(parents=True)
            (project / "derived" / "model.txt").write_text("old\n", encoding="utf-8")
            (project / "output" / "table.csv").write_text("old\n", encoding="utf-8")

            result = verify_project(project, "full", from_scratch=True)

            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.rolled_back)
            # Quarantine dir should be cleaned up on success
            if result.quarantine_dir:
                self.assertFalse(Path(result.quarantine_dir).exists())


if __name__ == "__main__":
    unittest.main()
