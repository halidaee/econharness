"""Tests for module load as environment reproducibility evidence."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from econharness.detectors import detect_environment_reproducibility


def _make_project(files: dict[str, str]) -> Path:
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _scan(root: Path, config: dict | None = None) -> list:
    files = list(root.rglob("*"))
    return detect_environment_reproducibility(root, config or {}, files)


def _titles(findings: list) -> list[str]:
    return [f.title for f in findings]


class ModuleLoadRLockfileTests(unittest.TestCase):
    """Cluster env reproducibility and local lockfile findings score independently."""

    def test_r_files_no_renv_no_modules_gives_medium(self) -> None:
        """Existing behavior unchanged when no submission scripts present."""
        root = _make_project({"analysis.R": "x <- 1\n"})
        findings = _scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "medium")
        self.assertIn("Missing R environment lockfile", findings[0].title)

    def test_r_files_no_renv_pinned_module_lockfile_still_medium(self) -> None:
        """Pinned module load does NOT downgrade the missing lockfile finding.

        The lockfile (local reproducibility) and module load (cluster reproducibility)
        are independent concerns. A pinned module load does not substitute for renv.lock.
        """
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1\nRscript analysis.R\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        self.assertEqual(len(lockfile_f), 1)
        self.assertEqual(lockfile_f[0].severity, "medium")
        self.assertEqual(lockfile_f[0].dimension, "environment_reproducibility")

    def test_r_files_no_renv_pinned_module_cluster_advisory_is_low(self) -> None:
        """A low cluster advisory fires in cluster_environment when renv.lock is absent."""
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1\nRscript analysis.R\n",
        })
        findings = _scan(root)
        cluster_f = [f for f in findings if f.dimension == "cluster_environment"]
        self.assertTrue(any(f.severity == "low" for f in cluster_f))

    def test_r_files_renv_present_no_finding(self) -> None:
        """R6: renv.lock + pinned module = no lockfile finding."""
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "renv.lock": '{"R": {"Version": "4.3.1"}}\n',
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1\nRscript analysis.R\n",
        })
        findings = _scan(root)
        lockfile_findings = [f for f in findings if "lockfile" in f.title.lower() or "R environment" in f.title]
        self.assertEqual(lockfile_findings, [])

    def test_r_files_no_renv_unpinned_module_gives_medium_lockfile(self) -> None:
        """Unpinned module → medium lockfile in environment_reproducibility + medium unpinned in cluster_environment."""
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R\nRscript analysis.R\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        unpinned_f = [f for f in findings if "without version pin" in f.title]
        self.assertEqual(len(lockfile_f), 1)
        self.assertEqual(lockfile_f[0].severity, "medium")
        self.assertEqual(lockfile_f[0].dimension, "environment_reproducibility")
        self.assertEqual(len(unpinned_f), 1)
        self.assertEqual(unpinned_f[0].severity, "medium")
        self.assertEqual(unpinned_f[0].dimension, "cluster_environment")


class PixiCondaManagesRTests(unittest.TestCase):
    """pixi.lock or conda-lock.yml with r-base is an acceptable substitute for renv.lock."""

    def test_pixi_lock_with_r_base_suppresses_r_lockfile_finding(self) -> None:
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "pixi.lock": "- name: r-base\n  version: 4.3.3\n- name: r-ggplot2\n  version: 3.4.0\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        self.assertEqual(lockfile_f, [])

    def test_pixi_lock_python_only_still_fires_r_finding(self) -> None:
        """pixi.lock present but only tracking Python — R is still untracked."""
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "pixi.lock": "- name: python\n  version: 3.11.0\n- name: numpy\n  version: 1.26.0\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        self.assertEqual(len(lockfile_f), 1)
        self.assertEqual(lockfile_f[0].severity, "medium")

    def test_conda_lock_with_r_base_suppresses_r_lockfile_finding(self) -> None:
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "conda-lock.yml": "package:\n- name: r-base\n  version: 4.3.1\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        self.assertEqual(lockfile_f, [])

    def test_no_lock_file_at_all_still_fires(self) -> None:
        root = _make_project({"analysis.R": "x <- 1\n"})
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        self.assertEqual(len(lockfile_f), 1)


class ModuleLoadUnpinnedTests(unittest.TestCase):
    """R4: unpinned module load raises a distinct medium finding."""

    def test_unpinned_r_module_flagged(self) -> None:
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R\nRscript run.R\n",
        })
        findings = _scan(root)
        unpinned = [f for f in findings if "without version pin" in f.title]
        self.assertEqual(len(unpinned), 1)
        self.assertEqual(unpinned[0].severity, "medium")
        self.assertIn("R", unpinned[0].title)
        self.assertEqual(unpinned[0].dimension, "cluster_environment")

    def test_ml_shorthand_parsed(self) -> None:
        """ml is the shorthand for module load."""
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nml R/4.3.1\nRscript run.R\n",
        })
        findings = _scan(root)
        unpinned = [f for f in findings if "without version pin" in f.title]
        self.assertEqual(unpinned, [])

    def test_multi_module_line_parsed(self) -> None:
        """module load R/4.3.1 gcc/12.2 → two pinned loads detected."""
        root = _make_project({
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1 gcc/12.2\nRscript run.R\n",
        })
        findings = _scan(root)
        unpinned = [f for f in findings if "without version pin" in f.title]
        self.assertEqual(unpinned, [])


class ModuleLoadVersionInconsistencyTests(unittest.TestCase):
    """R5: different versions across scripts → high finding."""

    def test_r_version_inconsistency_flagged(self) -> None:
        root = _make_project({
            "script_a.slurm": "#!/bin/bash\n#SBATCH --job-name=a\nmodule load R/4.2\nRscript a.R\n",
            "script_b.slurm": "#!/bin/bash\n#SBATCH --job-name=b\nmodule load R/4.3.1\nRscript b.R\n",
        })
        findings = _scan(root)
        inconsistent = [f for f in findings if "inconsistent" in f.title]
        self.assertEqual(len(inconsistent), 1)
        self.assertEqual(inconsistent[0].severity, "high")
        self.assertIn("R", inconsistent[0].title)
        self.assertIn("4.2", inconsistent[0].detail)
        self.assertIn("4.3.1", inconsistent[0].detail)
        self.assertEqual(inconsistent[0].dimension, "cluster_environment")

    def test_gcc_version_inconsistency_flagged(self) -> None:
        """R7: version inconsistency applies to any module, not just R/Python."""
        root = _make_project({
            "script_a.slurm": "#!/bin/bash\n#SBATCH --job-name=a\nmodule load gcc/11.3\nRscript a.R\n",
            "script_b.slurm": "#!/bin/bash\n#SBATCH --job-name=b\nmodule load gcc/12.2\nRscript b.R\n",
        })
        findings = _scan(root)
        inconsistent = [f for f in findings if "inconsistent" in f.title]
        self.assertEqual(len(inconsistent), 1)
        self.assertIn("gcc", inconsistent[0].title)
        self.assertEqual(inconsistent[0].dimension, "cluster_environment")

    def test_consistent_versions_no_inconsistency_finding(self) -> None:
        root = _make_project({
            "script_a.slurm": "#!/bin/bash\n#SBATCH --job-name=a\nmodule load R/4.3.1\nRscript a.R\n",
            "script_b.slurm": "#!/bin/bash\n#SBATCH --job-name=b\nmodule load R/4.3.1\nRscript b.R\n",
        })
        findings = _scan(root)
        inconsistent = [f for f in findings if "inconsistent" in f.title]
        self.assertEqual(inconsistent, [])

    def test_no_submission_scripts_no_module_findings(self) -> None:
        """Projects with no submission scripts behave exactly as before."""
        root = _make_project({"analysis.R": "x <- 1\n"})
        findings = _scan(root)
        module_findings = [f for f in findings if "module" in f.title.lower()]
        self.assertEqual(module_findings, [])


if __name__ == "__main__":
    unittest.main()
