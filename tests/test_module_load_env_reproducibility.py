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
    """R2: version-pinned R module load downgrades medium → low."""

    def test_r_files_no_renv_no_modules_gives_medium(self) -> None:
        """Existing behavior unchanged when no submission scripts present."""
        root = _make_project({"analysis.R": "x <- 1\n"})
        findings = _scan(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "medium")
        self.assertIn("Missing R environment lockfile", findings[0].title)

    def test_r_files_no_renv_pinned_module_gives_low(self) -> None:
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1\nRscript analysis.R\n",
        })
        findings = [f for f in _scan(root) if "R environment" in f.title or "lockfile" in f.title]
        r_lockfile_findings = [f for f in findings if "renv" in f.title.lower() or "R environment" in f.title]
        self.assertTrue(any(f.severity == "low" for f in _scan(root) if "module load" in f.detail.lower() or "renv" in f.title.lower() or "R environment" in f.title))

    def test_r_files_no_renv_pinned_module_downgraded_not_medium(self) -> None:
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R/4.3.1\nRscript analysis.R\n",
        })
        findings = _scan(root)
        r_findings = [f for f in findings if "R environment" in f.title or "renv" in f.title.lower()]
        self.assertTrue(all(f.severity != "medium" for f in r_findings))

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
        """Unpinned module load → medium lockfile finding (no downgrade) + medium unpinned finding."""
        root = _make_project({
            "analysis.R": "x <- 1\n",
            "run.slurm": "#!/bin/bash\n#SBATCH --job-name=x\nmodule load R\nRscript analysis.R\n",
        })
        findings = _scan(root)
        lockfile_f = [f for f in findings if "Missing R" in f.title]
        unpinned_f = [f for f in findings if "without version pin" in f.title]
        self.assertEqual(len(lockfile_f), 1)
        self.assertEqual(lockfile_f[0].severity, "medium")
        self.assertEqual(len(unpinned_f), 1)
        self.assertEqual(unpinned_f[0].severity, "medium")


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
