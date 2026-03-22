"""Tests for detect_path_portability — local machine paths, HPC paths, and allowlist."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import detect_path_portability


def _make_project(files: dict[str, str]) -> Path:
    """Create a temp project with the given filename→content mapping."""
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


class HpcPathPortabilityTests(unittest.TestCase):
    def _scan(self, root: Path, config: dict | None = None) -> list:
        files = list(root.rglob("*"))
        return detect_path_portability(root, config or {}, files)

    # ── HPC path flagging ──────────────────────────────────────────────────

    def test_scratch_path_flagged(self) -> None:
        root = _make_project({"run.sh": 'data="/scratch/jsmith/data.csv"\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "high")
        self.assertIn("HPC cluster path", findings[0].title)

    def test_gpfs_path_flagged(self) -> None:
        root = _make_project({"run.slurm": '#!/bin/bash\n#SBATCH --job-name=x\nINPUT=/gpfs/pilab/data.csv\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("HPC cluster path", findings[0].title)

    def test_lustre_path_flagged(self) -> None:
        root = _make_project({"job.job": 'outdir=/lustre/scratch/user/out\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("HPC cluster path", findings[0].title)

    def test_beegfs_path_flagged(self) -> None:
        root = _make_project({"run.sh": 'f=/beegfs/data/input.csv\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("HPC cluster path", findings[0].title)

    def test_scratch_with_dollar_user_still_flagged(self) -> None:
        """R3: /scratch/$USER/ has a hardcoded cluster root — must be flagged."""
        root = _make_project({"run.sh": 'outdir=/scratch/$USER/myproject\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("HPC cluster path", findings[0].title)

    # ── Env-var paths NOT flagged ──────────────────────────────────────────

    def test_dollar_scratch_not_flagged(self) -> None:
        """R2: $SCRATCH/ is portable and must not produce a finding."""
        root = _make_project({"run.sh": 'outdir=$SCRATCH/data.csv\n'})
        findings = self._scan(root)
        self.assertEqual(findings, [])

    def test_brace_env_var_not_flagged(self) -> None:
        root = _make_project({"run.sh": 'outdir=${SLURM_TMPDIR}/output\n'})
        findings = self._scan(root)
        self.assertEqual(findings, [])

    # ── Allowlist ─────────────────────────────────────────────────────────

    def test_allowlist_suppresses_finding(self) -> None:
        """R5: allowed_prefixes in config suppresses matching paths."""
        root = _make_project({"run.sh": 'data=/project/pilab/input.csv\n'})
        # /project/ doesn't match HPC_PATH_ROOT_PATTERN, so no finding anyway —
        # test with /scratch/ to verify allowlist actually fires
        root2 = _make_project({"run.sh": 'data=/scratch/pilab/input.csv\n'})
        config = {"path_portability": {"allowed_prefixes": ["/scratch/pilab/"]}}
        findings = detect_path_portability(root2, config, list(root2.rglob("*")))
        self.assertEqual(findings, [])

    def test_allowlist_only_suppresses_matching_prefix(self) -> None:
        root = _make_project({"run.sh": 'data=/scratch/jsmith/input.csv\n'})
        config = {"path_portability": {"allowed_prefixes": ["/scratch/pilab/"]}}
        findings = detect_path_portability(root, config, list(root.rglob("*")))
        self.assertEqual(len(findings), 1)

    # ── .slurm and .job file scanning ─────────────────────────────────────

    def test_slurm_file_scanned(self) -> None:
        root = _make_project({"submit.slurm": '#SBATCH --job-name=x\nOUT=/scratch/jsmith/out.csv\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)

    def test_job_file_scanned(self) -> None:
        root = _make_project({"submit.job": '#SBATCH --job-name=x\nOUT=/gpfs/pilab/out.csv\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)

    # ── Existing local-machine path detection unchanged ────────────────────

    def test_users_path_still_flagged(self) -> None:
        root = _make_project({"run.sh": 'f="/Users/jsmith/project/data.csv"\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].title, "Absolute path embedded in project source")

    def test_home_path_still_flagged(self) -> None:
        root = _make_project({"run.R": 'path <- "/home/jsmith/data.csv"\n'})
        findings = self._scan(root)
        self.assertEqual(len(findings), 1)

    def test_clean_script_no_findings(self) -> None:
        root = _make_project({"run.sh": 'data=$SCRATCH/input.csv\nout=$(pwd)/output.csv\n'})
        findings = self._scan(root)
        self.assertEqual(findings, [])

    # ── Config schema ──────────────────────────────────────────────────────

    def test_default_config_has_path_portability_key(self) -> None:
        from econharness.config import default_config
        config = default_config()
        self.assertIn("path_portability", config)
        self.assertEqual(config["path_portability"]["allowed_prefixes"], [])


if __name__ == "__main__":
    unittest.main()
