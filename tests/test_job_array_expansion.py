"""Tests for detect_job_array_expansion — output collision and undocumented mapping."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import detect_job_array_expansion


def _make_project(files: dict[str, str]) -> Path:
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _scan(root: Path) -> list:
    files = list(root.rglob("*"))
    return detect_job_array_expansion(root, files)


def _titles(findings: list) -> list[str]:
    return [f.title for f in findings]


# ── Trigger conditions ──────────────────────────────────────────────────────

class TriggerTests(unittest.TestCase):

    def test_no_sbatch_not_checked(self) -> None:
        """Plain shell scripts without #SBATCH are not batch scripts."""
        root = _make_project({
            "run.sh": "#!/bin/bash\nOUT=results.csv\necho $SLURM_ARRAY_TASK_ID > $OUT\n"
        })
        self.assertEqual(_scan(root), [])

    def test_sbatch_without_task_id_not_checked(self) -> None:
        """Non-array batch scripts are ignored."""
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\npython run.py > results.csv\n"
        })
        self.assertEqual(_scan(root), [])

    def test_py_file_ignored(self) -> None:
        root = _make_project({
            "run.py": "#SBATCH --job-name=x\nimport os; tid = os.environ['SLURM_ARRAY_TASK_ID']\n"
        })
        self.assertEqual(_scan(root), [])


# ── Collision check ─────────────────────────────────────────────────────────

class CollisionTests(unittest.TestCase):

    def test_fixed_output_path_flagged(self) -> None:
        """Output path with no task ID → medium collision finding."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# runs models\n"
                "python run.py $SLURM_ARRAY_TASK_ID > results/output.csv\n"
            )
        })
        findings = _scan(root)
        collision = [f for f in findings if "same output path" in f.title]
        self.assertEqual(len(collision), 1)
        self.assertEqual(collision[0].severity, "medium")

    def test_task_id_in_output_path_not_flagged(self) -> None:
        """Output path directly includes task ID → no collision finding."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# index = model specification\n"
                "python run.py $SLURM_ARRAY_TASK_ID > results/output_${SLURM_ARRAY_TASK_ID}.csv\n"
            )
        })
        findings = _scan(root)
        collision = [f for f in findings if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_sbatch_o_line_not_collision(self) -> None:
        """#SBATCH -o lines use Slurm %a substitution — must not be flagged as collision."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n#SBATCH -o slurm-%a.out\n"
                "# index = dataset\n"
                "python run.py $SLURM_ARRAY_TASK_ID\n"
            )
        })
        findings = _scan(root)
        collision = [f for f in findings if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_braced_task_id_in_path_not_flagged(self) -> None:
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-4\n"
                "# index = country\n"
                "python run.py > out_${SLURM_ARRAY_TASK_ID}/result.csv\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_variable_path_not_flagged_as_collision(self) -> None:
        """Output path is a $VAR reference — may be derived from task ID, trust it."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# index = model spec\n"
                "export OUT_DIR=\"results/${SLURM_ARRAY_TASK_ID}\"\n"
                "python run.py > $OUT_DIR/output.csv\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_braced_variable_path_not_flagged_as_collision(self) -> None:
        """${VAR} form of variable reference — must also be suppressed."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-4\n"
                "# index = country\n"
                "A2_OUTPUT_DIR=\"results/${SCOPE}\"\n"
                "Rscript model.R $SLURM_ARRAY_TASK_ID > ${A2_OUTPUT_DIR}/result.csv\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_hyphenated_word_with_e_prefix_not_matched(self) -> None:
        """'-e' inside a hyphenated word (e.g. r-env) must not be treated as -e flag."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# index = model spec\n"
                "# conda activate r-env\n"
                "python run.py $SLURM_ARRAY_TASK_ID\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(collision, [])

    def test_literal_path_still_flagged(self) -> None:
        """A completely literal path (no $ at all) is the true positive case."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# index = spec\n"
                "python run.py $SLURM_ARRAY_TASK_ID > results/output.csv\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(len(collision), 1)

    def test_job_suffix_scanned(self) -> None:
        root = _make_project({
            "run.job": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# index = spec\n"
                "Rscript model.R $SLURM_ARRAY_TASK_ID > output.csv\n"
            )
        })
        collision = [f for f in _scan(root) if "same output path" in f.title]
        self.assertEqual(len(collision), 1)


# ── Undocumented mapping check ──────────────────────────────────────────────

class UndocumentedMappingTests(unittest.TestCase):

    def test_no_comment_near_task_id_flagged(self) -> None:
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "python run.py $SLURM_ARRAY_TASK_ID > out_${SLURM_ARRAY_TASK_ID}.csv\n"
            )
        })
        findings = _scan(root)
        advisory = [f for f in findings if "undocumented" in f.title]
        self.assertEqual(len(advisory), 1)
        self.assertEqual(advisory[0].severity, "low")

    def test_comment_within_window_satisfies_requirement(self) -> None:
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "# Index N = country N in params/countries.csv\n"
                "python run.py $SLURM_ARRAY_TASK_ID > out_${SLURM_ARRAY_TASK_ID}.csv\n"
            )
        })
        advisory = [f for f in _scan(root) if "undocumented" in f.title]
        self.assertEqual(advisory, [])

    def test_comment_below_task_id_within_window_satisfies(self) -> None:
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-4\n"
                "python run.py $SLURM_ARRAY_TASK_ID > out_${SLURM_ARRAY_TASK_ID}.csv\n"
                "# above: array index maps to model specification in specs.csv\n"
            )
        })
        advisory = [f for f in _scan(root) if "undocumented" in f.title]
        self.assertEqual(advisory, [])

    def test_sbatch_directive_alone_does_not_satisfy_documentation(self) -> None:
        """#SBATCH lines are not documentation comments."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n#SBATCH --job-name=x\n"
                "python run.py $SLURM_ARRAY_TASK_ID > out_${SLURM_ARRAY_TASK_ID}.csv\n"
            )
        })
        advisory = [f for f in _scan(root) if "undocumented" in f.title]
        self.assertEqual(len(advisory), 1)

    def test_both_collision_and_advisory_can_fire_together(self) -> None:
        """A script with a fixed path AND no comment gets both findings."""
        root = _make_project({
            "run.slurm": (
                "#!/bin/bash\n#SBATCH --array=0-9\n"
                "python run.py $SLURM_ARRAY_TASK_ID > output.csv\n"
            )
        })
        findings = _scan(root)
        collision = [f for f in findings if "same output path" in f.title]
        advisory = [f for f in findings if "undocumented" in f.title]
        self.assertEqual(len(collision), 1)
        self.assertEqual(len(advisory), 1)


if __name__ == "__main__":
    unittest.main()
