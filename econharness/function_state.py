"""Function state and hidden-dependency checks."""

from __future__ import annotations

import ast
import builtins
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


PYTHON_BUILTINS = set(dir(builtins))
R_STOPWORDS = {
    "else",
    "false",
    "function",
    "if",
    "in",
    "na",
    "next",
    "null",
    "repeat",
    "return",
    "true",
    "while",
}


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


def iter_outer_scope_dependency_issues(project_root: Path, files: Iterable[Path]) -> list[FunctionStateIssue]:
    issues: list[FunctionStateIssue] = []
    for path in files:
        rel = path.relative_to(project_root).as_posix()
        if _is_test_like_path(rel):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            issues.extend(_python_outer_scope_issues(project_root, path))
        elif suffix == ".r":
            issues.extend(_r_outer_scope_issues(project_root, path))
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


def _python_outer_scope_issues(project_root: Path, path: Path) -> list[FunctionStateIssue]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    rel = path.relative_to(project_root).as_posix()
    module_level_names = _python_module_level_assigned_names(tree)
    imported_names = _python_imported_names(tree)
    issues: list[FunctionStateIssue] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        params = {arg.arg for arg in node.args.args}
        params |= {arg.arg for arg in node.args.kwonlyargs}
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        local_names = {
            subnode.id
            for subnode in ast.walk(node)
            if isinstance(subnode, ast.Name) and isinstance(subnode.ctx, ast.Store)
        }
        call_names = {
            subnode.func.id
            for subnode in ast.walk(node)
            if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Name)
        }
        loaded_names = {
            subnode.id
            for subnode in ast.walk(node)
            if isinstance(subnode, ast.Name) and isinstance(subnode.ctx, ast.Load)
        }
        hidden_names = sorted(
            name
            for name in loaded_names
            if name in module_level_names
            and name not in params
            and name not in local_names
            and name not in call_names
            and name not in imported_names
            and name not in PYTHON_BUILTINS
        )
        if not hidden_names:
            continue
        if len(hidden_names) == 1 and _looks_like_constant(hidden_names[0]):
            continue
        issues.append(
            FunctionStateIssue(
                path=rel,
                function_name=node.name,
                detail=f"depends on module-level names `{', '.join(hidden_names[:4])}` inside `{node.name}`",
            )
        )
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


def _python_module_level_assigned_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _python_imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
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
    for function_name, _, body in _iter_r_function_bodies(text):
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


def _r_outer_scope_issues(project_root: Path, path: Path) -> list[FunctionStateIssue]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    rel = path.relative_to(project_root).as_posix()
    module_level_names = _r_top_level_assigned_names(text)
    issues: list[FunctionStateIssue] = []
    for function_name, params, body in _iter_r_function_bodies(text):
        local_names = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_.]*)\s*<-", body))
        call_names = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_.]*)\s*\(", body))
        loaded_names = {
            token
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.]*\b", body)
            if token not in R_STOPWORDS
        }
        hidden_names = sorted(
            name
            for name in loaded_names
            if name in module_level_names
            and name not in params
            and name not in local_names
            and name not in call_names
            and name != function_name
        )
        hidden_names = [name for name in hidden_names if _looks_like_constant(name)]
        if not hidden_names:
            continue
        issues.append(
            FunctionStateIssue(
                path=rel,
                function_name=function_name,
                detail=f"depends on module-level names `{', '.join(hidden_names[:4])}` inside `{function_name}`",
            )
        )
    return issues


def _iter_r_function_bodies(text: str) -> Iterable[tuple[str, set[str], str]]:
    pattern = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-\s*function\s*\(", flags=re.MULTILINE)
    for match in pattern.finditer(text):
        open_paren_index = text.find("(", match.end() - 1)
        if open_paren_index < 0:
            continue
        args_text, args_end = _extract_balanced_parentheses(text, open_paren_index)
        if args_text is None or args_end < 0:
            continue
        params = {
            token
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.]*\b", args_text)
            if token not in R_STOPWORDS
        }
        start = args_end + 1
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
                    yield match.group(1), params, text[body_start:index]
                    break


def _r_top_level_assigned_names(text: str) -> set[str]:
    names: set[str] = set()
    depth = 0
    in_string: str | None = None
    escaped = False
    line_start = 0
    for index, char in enumerate(text + "\n"):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        else:
            if char in {'"', "'"}:
                in_string = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
        if char == "\n":
            line = text[line_start:index]
            if depth == 0:
                match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-", line)
                if match:
                    names.add(match.group(1))
            line_start = index + 1
    return names


def _extract_balanced_parentheses(text: str, open_paren_index: int) -> tuple[str | None, int]:
    depth = 0
    in_string: str | None = None
    escaped = False
    for index in range(open_paren_index, len(text)):
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
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_index + 1 : index], index
    return None, -1


def _looks_like_constant(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9_]+", name))


def _is_test_like_path(rel_path: str) -> bool:
    parts = set(rel_path.split("/"))
    return (
        "tests" in parts
        or rel_path.startswith("tests/")
        or rel_path.endswith("_test.py")
        or rel_path.endswith("_test.R")
    )
