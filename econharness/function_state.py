"""Function state and hidden-dependency checks."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "remove",
    "setdefault",
    "update",
}


@dataclass(slots=True)
class FunctionStateIssue:
    path: str
    function_name: str
    detail: str


def iter_global_write_issues(project_root: Path, files: Iterable[Path]) -> list[FunctionStateIssue]:
    issues: list[FunctionStateIssue] = []
    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if _is_test_like_path(rel):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            issues.extend(_python_global_write_issues(project_root, path))
        elif suffix == ".r":
            issues.extend(_r_global_write_issues(project_root, path))
    return issues


def _python_global_write_issues(project_root: Path, path: Path) -> list[FunctionStateIssue]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    rel = path.relative_to(project_root).as_posix()
    module_mutables = _python_module_level_mutables(tree)
    issues: list[FunctionStateIssue] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue

        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Global):
                for name in subnode.names:
                    issues.append(
                        FunctionStateIssue(
                            path=rel,
                            function_name=node.name,
                            detail=f"declares `global {name}` inside `{node.name}`",
                        )
                    )
            elif isinstance(subnode, ast.Assign):
                for target in subnode.targets:
                    issues.extend(_python_mutable_target_issues(rel, node.name, target, module_mutables))
            elif isinstance(subnode, ast.AugAssign):
                issues.extend(_python_mutable_target_issues(rel, node.name, subnode.target, module_mutables))
            elif isinstance(subnode, ast.Call):
                call_issue = _python_mutating_call_issue(rel, node.name, subnode, module_mutables)
                if call_issue is not None:
                    issues.append(call_issue)
    return issues


def _python_module_level_mutables(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if not _is_mutable_initializer(node.value):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _is_mutable_initializer(node: ast.AST) -> bool:
    if isinstance(node, (ast.Dict, ast.List, ast.Set)):
        return True
    if isinstance(node, ast.Call):
        func_name = _python_func_name(node.func)
        return func_name in {"defaultdict", "dict", "list", "set"}
    return False


def _python_mutable_target_issues(
    rel_path: str,
    function_name: str,
    target: ast.AST,
    module_mutables: set[str],
) -> list[FunctionStateIssue]:
    issue: FunctionStateIssue | None = None
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id in module_mutables:
        issue = FunctionStateIssue(
            path=rel_path,
            function_name=function_name,
            detail=f"mutates module-level mutable `{target.value.id}` inside `{function_name}`",
        )
    elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id in module_mutables:
        issue = FunctionStateIssue(
            path=rel_path,
            function_name=function_name,
            detail=f"writes through module-level mutable `{target.value.id}` inside `{function_name}`",
        )
    return [issue] if issue else []


def _python_mutating_call_issue(
    rel_path: str,
    function_name: str,
    node: ast.Call,
    module_mutables: set[str],
) -> FunctionStateIssue | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in MUTATING_METHODS:
        return None
    if not isinstance(node.func.value, ast.Name):
        return None
    if node.func.value.id not in module_mutables:
        return None
    return FunctionStateIssue(
        path=rel_path,
        function_name=function_name,
        detail=f"calls mutating method `{node.func.attr}` on module-level mutable `{node.func.value.id}` inside `{function_name}`",
    )


def _python_func_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _r_global_write_issues(project_root: Path, path: Path) -> list[FunctionStateIssue]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    rel = path.relative_to(project_root).as_posix()
    issues: list[FunctionStateIssue] = []
    for function_name, body in _iter_r_function_bodies(text):
        for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_.]*)\s*<<-", body):
            issues.append(
                FunctionStateIssue(
                    path=rel,
                    function_name=function_name,
                    detail=f"uses `<<-` for `{match.group(1)}` inside `{function_name}`",
                )
            )
        if re.search(r"assign\s*\([^)]*envir\s*=\s*\.GlobalEnv", body, flags=re.DOTALL):
            issues.append(
                FunctionStateIssue(
                    path=rel,
                    function_name=function_name,
                    detail=f"uses `assign(..., envir = .GlobalEnv)` inside `{function_name}`",
                )
            )
        if re.search(r"assign\s*\([^)]*pos\s*=\s*['\"]?\.GlobalEnv['\"]?", body, flags=re.DOTALL):
            issues.append(
                FunctionStateIssue(
                    path=rel,
                    function_name=function_name,
                    detail=f"uses `assign(..., pos = .GlobalEnv)` inside `{function_name}`",
                )
            )
    return issues


def _iter_r_function_bodies(text: str) -> Iterable[tuple[str, str]]:
    pattern = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-\s*function\s*\(", flags=re.MULTILINE)
    for match in pattern.finditer(text):
        start = match.end() - 1
        depth = 0
        body_start = None
        in_string: str | None = None
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
                continue
            if char in {'"', "'"}:
                in_string = char
                continue
            if char == "{":
                depth += 1
                if body_start is None:
                    body_start = index + 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0 and body_start is not None:
                    yield match.group(1), text[body_start:index]
                    break


def _is_test_like_path(rel_path: str) -> bool:
    parts = set(rel_path.split("/"))
    return (
        "tests" in parts
        or rel_path.startswith("tests/")
        or rel_path.endswith("_test.py")
        or rel_path.endswith("_test.R")
    )
