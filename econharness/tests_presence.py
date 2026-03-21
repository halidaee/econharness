"""Test command and test-presence heuristics."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CODE_SUFFIXES = {".py", ".r"}


@dataclass(slots=True)
class TestPresenceSummary:
    has_tests_command: bool
    test_paths: tuple[str, ...]
    helper_heavy: bool


def summarize_test_presence(project_root: Path, config: dict, files: Iterable[Path]) -> TestPresenceSummary:
    test_paths: list[str] = []
    helper_function_count = 0
    code_file_count = 0

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        suffix = path.suffix.lower()
        if _is_test_path(rel):
            test_paths.append(rel)
            continue
        if suffix not in CODE_SUFFIXES:
            continue
        code_file_count += 1
        helper_function_count += _count_top_level_functions(path, suffix)

    commands = config.get("pipeline", {}).get("command", {})
    tests_command = str(commands.get("tests", "")).strip()
    helper_heavy = helper_function_count >= 2 or (code_file_count >= 4 and helper_function_count >= 1)

    return TestPresenceSummary(
        has_tests_command=bool(tests_command),
        test_paths=tuple(sorted(test_paths)),
        helper_heavy=helper_heavy,
    )


def _is_test_path(rel_path: str) -> bool:
    parts = tuple(rel_path.split("/"))
    filename = parts[-1]
    suffix = Path(filename).suffix.lower()
    return (
        "tests" in parts
        or "testthat" in parts
        or (suffix == ".py" and (filename.startswith("test_") or filename.endswith("_test.py")))
        or (suffix == ".r" and filename.startswith("test-"))
    )


def _count_top_level_functions(path: Path, suffix: str) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return 0
        return sum(1 for node in tree.body if isinstance(node, ast.FunctionDef))

    return len(re.findall(r"^\s*[A-Za-z][A-Za-z0-9_]*\s*<-\s*function\s*\(", text, flags=re.MULTILINE))
