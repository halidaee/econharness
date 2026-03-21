"""Generated-artifact quarantine helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class QuarantineResult:
    quarantine_dir: Path
    moved_paths: tuple[str, ...]


def quarantine_generated_artifacts(project_root: Path, config: dict) -> QuarantineResult:
    _validate_generated_roots(project_root, config)
    roots = [
        str(config.get("paths", {}).get(key, "")).strip().strip("/")
        for key in ("derived", "output", "temp")
    ]
    roots = [root for root in roots if root]
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    quarantine_dir = project_root / ".econharness" / "quarantine" / timestamp
    moved_files: set[str] = set()

    for root in roots:
        root_path = project_root / root
        if not root_path.exists():
            continue

        if root_path.is_file():
            moved_files.add(root)
            target = quarantine_dir / root
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root_path), str(target))
            continue

        moved_files.update(
            path.relative_to(project_root).as_posix()
            for path in root_path.rglob("*")
            if path.is_file()
        )
        for child in list(root_path.iterdir()):
            target = quarantine_dir / root / child.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(target))
        root_path.mkdir(parents=True, exist_ok=True)

    quarantine_dir.mkdir(parents=True, exist_ok=True)
    return QuarantineResult(quarantine_dir=quarantine_dir, moved_paths=tuple(sorted(moved_files)))


def _validate_generated_roots(project_root: Path, config: dict) -> None:
    paths_cfg = config.get("paths", {})
    raw_root = str(paths_cfg.get("raw", "")).strip().strip("/")
    if not raw_root:
        return

    raw_path = project_root / raw_root
    for key in ("derived", "output", "temp"):
        root = str(paths_cfg.get(key, "")).strip().strip("/")
        if not root:
            continue
        root_path = project_root / root
        if _paths_overlap(root_path, raw_path):
            raise ValueError(
                f"Configured generated root `{root}` overlaps raw-data root `{raw_root}`; "
                "refusing from-scratch quarantine."
            )


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False
