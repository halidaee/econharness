"""Narrow naming clarity checks."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CODE_SUFFIXES = {".py", ".r", ".sh", ".do"}
GENERIC_FILENAME_PATTERNS = [
    re.compile(r"^(?:tmp|temp)\d*$"),
    re.compile(r"^script\d*$"),
    re.compile(r"^analysis\d*$"),
    re.compile(r"^(?:misc|notes|file|untitled)\d*$"),
]
GENERIC_FUNCTION_PATTERNS = [
    re.compile(r"^helper\d*$"),
    re.compile(r"^run\d*$"),
    re.compile(r"^process\d*$"),
    re.compile(r"^foo\d*$"),
    re.compile(r"^bar\d*$"),
    re.compile(r"^(?:tmp|temp)(?:_func(?:tion)?)?\d*$"),
    re.compile(r"^my_function\d*$"),
]
IGNORED_FUNCTION_NAMES = {"main"}


@dataclass(slots=True)
class NamingIssue:
    path: str
    subject: str
    reason: str


def iter_vague_filename_issues(project_root: Path, files: Iterable[Path]) -> list[NamingIssue]:
    issues: list[NamingIssue] = []
    for path in files:
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        rel = path.relative_to(project_root).as_posix()
        stem = path.stem.lower()
        if any(pattern.fullmatch(stem) for pattern in GENERIC_FILENAME_PATTERNS):
            issues.append(
                NamingIssue(
                    path=rel,
                    subject=path.name,
                    reason="generic filename stem",
                )
            )
    return issues


def iter_vague_function_name_issues(project_root: Path, files: Iterable[Path]) -> list[NamingIssue]:
    issues: list[NamingIssue] = []
    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if _is_test_like_path(rel):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            issues.extend(_python_function_issues(project_root, path))
        elif suffix == ".r":
            issues.extend(_r_function_issues(project_root, path))
    return issues


def _python_function_issues(project_root: Path, path: Path) -> list[NamingIssue]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    issues: list[NamingIssue] = []
    rel = path.relative_to(project_root).as_posix()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if _is_generic_function_name(node.name):
            issues.append(
                NamingIssue(
                    path=rel,
                    subject=node.name,
                    reason="generic top-level function name",
                )
            )
    return issues


def _r_function_issues(project_root: Path, path: Path) -> list[NamingIssue]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    issues: list[NamingIssue] = []
    rel = path.relative_to(project_root).as_posix()
    for name in re.findall(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*<-\s*function\s*\(", text, flags=re.MULTILINE):
        if _is_generic_function_name(name):
            issues.append(
                NamingIssue(
                    path=rel,
                    subject=name,
                    reason="generic top-level function name",
                )
            )
    return issues


def _is_generic_function_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in IGNORED_FUNCTION_NAMES or lowered.startswith("test_"):
        return False
    return any(pattern.fullmatch(lowered) for pattern in GENERIC_FUNCTION_PATTERNS)


def _is_test_like_path(rel_path: str) -> bool:
    parts = set(rel_path.split("/"))
    return (
        "tests" in parts
        or rel_path.startswith("tests/")
        or rel_path.endswith("_test.py")
        or rel_path.endswith("_test.R")
    )
