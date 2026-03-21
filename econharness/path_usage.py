"""Extract explicit path reads and writes from source files."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


R_READ_FUNCS = {"readRDS", "read_csv", "read_delim", "read_tsv", "fread", "read_dta"}
R_WRITE_FUNCS = {"saveRDS", "write_csv", "write.csv", "write_tsv", "fwrite", "ggsave"}
PYTHON_READ_FUNCS = {"open", "read_csv", "read_parquet", "read_pickle", "read_feather", "read_stata", "read_text", "read_bytes"}
PYTHON_WRITE_FUNCS = {"open", "to_csv", "to_parquet", "to_pickle", "to_feather", "to_json", "to_excel", "savefig", "write_text", "write_bytes"}


@dataclass(slots=True)
class PathUse:
    kind: str
    path: str
    line: int


def extract_path_uses(path: Path, text: str) -> list[PathUse]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _extract_python_path_uses(text)
    if suffix == ".r":
        return _extract_r_path_uses(text)
    return []


def _extract_python_path_uses(text: str) -> list[PathUse]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    path_uses: list[PathUse] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _python_func_name(node.func)
        if func_name in PYTHON_READ_FUNCS:
            path_use = _python_read_path_use(node, func_name)
            if path_use is not None:
                path_uses.append(path_use)
        if func_name in PYTHON_WRITE_FUNCS:
            path_use = _python_write_path_use(node, func_name)
            if path_use is not None:
                path_uses.append(path_use)
    return path_uses


def _python_read_path_use(node: ast.Call, func_name: str | None) -> PathUse | None:
    if func_name == "open":
        mode = _python_open_mode(node)
        if any(flag in mode for flag in ("w", "a", "+")):
            return None
        path = _python_extract_path(node.args[0] if node.args else None)
    else:
        path = _python_extract_path(node.args[0] if node.args else _keyword_value(node, {"filepath_or_buffer", "path", "path_or_buf"}))
    if not path:
        return None
    return PathUse(kind="read", path=path, line=node.lineno)


def _python_write_path_use(node: ast.Call, func_name: str | None) -> PathUse | None:
    if func_name == "open":
        mode = _python_open_mode(node)
        if not any(flag in mode for flag in ("w", "a", "+")):
            return None
        path = _python_extract_path(node.args[0] if node.args else None)
    elif func_name in {"write_text", "write_bytes", "savefig"}:
        if isinstance(node.func, ast.Attribute):
            path = _python_extract_path(node.func.value)
        else:
            path = _python_extract_path(node.args[0] if node.args else None)
    else:
        path = _python_extract_path(node.args[0] if node.args else _keyword_value(node, {"path", "path_or_buf", "fname"}))
    if not path:
        return None
    return PathUse(kind="write", path=path, line=node.lineno)


def _python_open_mode(node: ast.Call) -> str:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        return node.args[1].value
    keyword = _keyword_value(node, {"mode"})
    if isinstance(keyword, ast.Constant) and isinstance(keyword.value, str):
        return keyword.value
    return "r"


def _keyword_value(node: ast.Call, names: set[str]) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg in names:
            return keyword.value
    return None


def _python_func_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _python_extract_path(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    segments = _python_path_segments(node)
    if not segments:
        return None
    return _normalize_literal_path("/".join(segments))


def _python_path_segments(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left = _python_path_segments(node.left)
        right = _python_path_segments(node.right)
        if left and right:
            return left + right
        return None
    if isinstance(node, ast.Call):
        func_name = _python_func_name(node.func)
        if func_name in {"Path", "PurePath", "PurePosixPath", "PureWindowsPath"}:
            segments: list[str] = []
            for arg in node.args:
                arg_segments = _python_path_segments(arg)
                if not arg_segments:
                    return None
                segments.extend(arg_segments)
            return segments
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"joinpath"}:
            base = _python_path_segments(node.func.value)
            if not base:
                return None
            segments = list(base)
            for arg in node.args:
                arg_segments = _python_path_segments(arg)
                if not arg_segments:
                    return None
                segments.extend(arg_segments)
            return segments
    return None


def _extract_r_path_uses(text: str) -> list[PathUse]:
    path_uses: list[PathUse] = []
    for function_name, args_text, line in _iter_r_function_calls(text, R_READ_FUNCS | R_WRITE_FUNCS):
        args = _split_top_level_args(args_text)
        named_args = {}
        positional_args: list[str] = []
        for arg in args:
            match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*=\s*(.*)$", arg, flags=re.DOTALL)
            if match:
                named_args[match.group(1)] = match.group(2).strip()
            else:
                positional_args.append(arg)
        kind = "read" if function_name in R_READ_FUNCS else "write"
        target = _r_path_arg(function_name, positional_args, named_args)
        if not target:
            continue
        literal_path = _r_extract_path(target)
        if literal_path:
            path_uses.append(PathUse(kind=kind, path=literal_path, line=line))
    return path_uses


def _r_path_arg(function_name: str, positional_args: list[str], named_args: dict[str, str]) -> str | None:
    if function_name in R_READ_FUNCS:
        return named_args.get("file") or (positional_args[0] if positional_args else None)
    if function_name == "saveRDS":
        return named_args.get("file") or (positional_args[1] if len(positional_args) >= 2 else None)
    if function_name == "ggsave":
        return named_args.get("filename") or (positional_args[0] if positional_args else None)
    return named_args.get("file") or (positional_args[1] if len(positional_args) >= 2 else None)


def _r_extract_path(text: str) -> str | None:
    strings = re.findall(r"['\"]([^'\"]+)['\"]", text)
    if not strings:
        return None
    return _normalize_literal_path("/".join(strings))


def _normalize_literal_path(value: str) -> str:
    text = value.replace("\\", "/").strip()
    text = re.sub(r"^\./", "", text)
    text = re.sub(r"/+", "/", text)
    return text.strip("/")


def _iter_r_function_calls(text: str, function_names: set[str]) -> Iterable[tuple[str, str, int]]:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_.]+::)?({'|'.join(sorted(map(re.escape, function_names), key=len, reverse=True))})\s*\(",
    )
    for match in pattern.finditer(text):
        open_paren_index = text.find("(", match.end() - 1)
        if open_paren_index < 0:
            continue
        extracted = _extract_balanced_call(text, open_paren_index)
        if extracted is None:
            continue
        args_text, _ = extracted
        yield match.group(1), args_text, text.count("\n", 0, match.start()) + 1


def _extract_balanced_call(text: str, open_paren_index: int) -> tuple[str, int] | None:
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
    return None


def _split_top_level_args(text: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth = 0
    in_string: str | None = None
    escaped = False
    for index, char in enumerate(text):
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
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            depth -= 1
            continue
        if char == "," and depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        args.append(tail)
    return args
