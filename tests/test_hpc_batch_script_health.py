"""Tests for detect_hpc_batch_script_health — missing set -e in batch scripts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import detect_hpc_batch_script_health


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
    return detect_hpc_batch_script_health(root, files)


class HpcBatchScriptHealthTests(unittest.TestCase):

    def test_slurm_without_set_e_flagged(self) -> None:
        root = _make_project({
            "submit.slurm": "#!/bin/bash\n#SBATCH --job-name=test\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "medium")
        self.assertIn("set -e", findings[0].title)

    def test_sh_without_set_e_flagged(self) -> None:
        root = _make_project({
            "run.sh": "#!/bin/bash\n#SBATCH --job-name=x\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(len(findings), 1)

    def test_job_without_set_e_flagged(self) -> None:
        root = _make_project({
            "run.job": "#!/bin/bash\n#SBATCH --ntasks=1\nRscript model.R\n"
        })
        findings = _scan(root)
        self.assertEqual(len(findings), 1)

    def test_set_e_in_body_passes(self) -> None:
        root = _make_project({
            "submit.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nset -e\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_set_e_after_sbatch_block_passes(self) -> None:
        """set -e anywhere in the file body is valid."""
        root = _make_project({
            "submit.slurm": (
                "#!/bin/bash\n#SBATCH --job-name=x\n#SBATCH --ntasks=4\n"
                "module load R/4.3.1\nset -e\nRscript model.R\n"
            )
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_shebang_bash_e_passes(self) -> None:
        """#!/bin/bash -e counts as satisfying the requirement."""
        root = _make_project({
            "run.sh": "#!/bin/bash -e\n#SBATCH --job-name=x\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_set_o_errexit_passes(self) -> None:
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nset -o errexit\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_set_xe_passes(self) -> None:
        """set -xe combines -x and -e; the -e flag is satisfied."""
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nset -xe\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_no_sbatch_not_checked(self) -> None:
        """Plain shell scripts without #SBATCH are not batch scripts."""
        root = _make_project({
            "run.sh": "#!/bin/bash\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_python_file_ignored(self) -> None:
        """Only .sh, .slurm, .job files are checked."""
        root = _make_project({
            "run.py": "#SBATCH --job-name=x\nimport os\n"
        })
        findings = _scan(root)
        self.assertEqual(findings, [])

    def test_set_u_alone_not_sufficient(self) -> None:
        """set -u without set -e must still be flagged."""
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nset -u\npython run.py\n"
        })
        findings = _scan(root)
        self.assertEqual(len(findings), 1)

    def test_remediation_message_present(self) -> None:
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nRscript run.R\n"
        })
        findings = _scan(root)
        self.assertIn("set -e", findings[0].remediation)


if __name__ == "__main__":
    unittest.main()
