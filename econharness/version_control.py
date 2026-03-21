"""Static checks for version-control discipline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TERMINAL_VERSION_TOKENS = {
    "backup",
    "copy",
    "draft",
    "final",
    "new",
    "old",
    "rev",
    "revised",
    "tmp",
    "temp",
}
DATE_PATTERNS = [
    re.compile(r"(?:^|[_-])(?:19|20)\d{2}[_-](?:0[1-9]|1[0-2])[_-](?:0[1-9]|[12]\d|3[01])(?:$|[_-])"),
    re.compile(r"(?:^|[_-])(?:19|20)\d{6}(?:$|[_-])"),
]


@dataclass(slots=True)
class VersionedFilenameIssue:
    path: str
    reason: str


@dataclass(slots=True)
class FilenameVariantCluster:
    canonical_name: str
    paths: tuple[str, ...]


def iter_versioned_filename_issues(
    project_root: Path,
    config: dict,
    files: Iterable[Path],
) -> list[VersionedFilenameIssue]:
    issues: list[VersionedFilenameIssue] = []
    raw_root = str(config.get("paths", {}).get("raw", "")).strip().strip("/")
    paper_root = str(config.get("paths", {}).get("paper", "")).strip().strip("/")
    generated_roots = {
        str(config.get("paths", {}).get(key, "")).strip().strip("/")
        for key in ("derived", "output", "temp")
    } - {""}

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if _should_skip_path(rel, raw_root, paper_root, generated_roots, path.suffix.lower()):
            continue
        stem = path.stem.lower()
        tokens = [token for token in re.split(r"[_\-. ]+", stem) if token]
        if not tokens:
            continue

        reason = ""
        if tokens[-1] in TERMINAL_VERSION_TOKENS:
            reason = f"terminal token `{tokens[-1]}`"
        elif re.fullmatch(r"v\d+", tokens[-1]) or re.fullmatch(r"ver(?:sion)?\d+", tokens[-1]):
            reason = f"terminal token `{tokens[-1]}`"
        elif any(pattern.search(stem) for pattern in DATE_PATTERNS):
            reason = "embedded date-like suffix"

        if reason:
            issues.append(VersionedFilenameIssue(path=rel, reason=reason))

    return issues


def iter_filename_variant_clusters(
    project_root: Path,
    config: dict,
    files: Iterable[Path],
) -> list[FilenameVariantCluster]:
    raw_root = str(config.get("paths", {}).get("raw", "")).strip().strip("/")
    paper_root = str(config.get("paths", {}).get("paper", "")).strip().strip("/")
    generated_roots = {
        str(config.get("paths", {}).get(key, "")).strip().strip("/")
        for key in ("derived", "output", "temp")
    } - {""}
    groups: dict[tuple[str, str, str], list[str]] = {}

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if _should_skip_path(rel, raw_root, paper_root, generated_roots, path.suffix.lower()):
            continue
        canonical = _canonicalize_stem(path.stem)
        if not canonical or canonical == path.stem.lower():
            continue
        key = (str(path.parent.relative_to(project_root).as_posix()), canonical, path.suffix.lower())
        groups.setdefault(key, []).append(rel)

    clusters: list[FilenameVariantCluster] = []
    for (_, canonical, _), paths in groups.items():
        unique_paths = tuple(sorted(set(paths)))
        if len(unique_paths) < 2:
            continue
        clusters.append(FilenameVariantCluster(canonical_name=canonical, paths=unique_paths))
    return clusters


def _should_skip_path(
    rel_path: str,
    raw_root: str,
    paper_root: str,
    generated_roots: set[str],
    suffix: str,
) -> bool:
    parts = tuple(rel_path.split("/"))
    if any(part.startswith(".") for part in parts):
        return True
    if raw_root and (rel_path == raw_root or rel_path.startswith(f"{raw_root}/")):
        return True
    if paper_root and (rel_path == paper_root or rel_path.startswith(f"{paper_root}/")):
        return True
    if suffix in {".py", ".r", ".sh", ".do"}:
        return False
    return not any(rel_path == root or rel_path.startswith(f"{root}/") for root in generated_roots)


def _canonicalize_stem(stem: str) -> str:
    text = stem.lower()
    original = text
    text = re.sub(r"[_-](?:v\d+|ver(?:sion)?\d+)$", "", text)
    text = re.sub(r"[_-](?:backup|copy|draft|final|new|old|rev|revised|tmp|temp)$", "", text)
    text = re.sub(r"[_-](?:19|20)\d{2}(?:[_-](?:0[1-9]|1[0-2])[_-](?:0[1-9]|[12]\d|3[01]))$", "", text)
    text = re.sub(r"[_-](?:19|20)\d{6}$", "", text)
    text = re.sub(r"[_-]+$", "", text)
    return text if text and text != original else text
