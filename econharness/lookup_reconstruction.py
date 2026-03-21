"""Extraction and clustering for repeated lookup reconstruction."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from econharness.models import LookupCandidate

R_JOIN_FUNCTIONS = {"left_join", "right_join", "inner_join", "full_join", "merge"}
R_LOAD_FUNCTIONS = {"readRDS", "read_csv", "read_delim", "read_tsv", "fread", "read_dta"}
R_TRANSFORM_FUNCTIONS = {
    "mutate",
    "transmute",
    "summarise",
    "summarize",
    "rename",
    "pivot_longer",
    "pivot_wider",
    "separate",
    "separate_wider_delim",
    "unite",
    "group_by",
    "ungroup",
    "quantile",
    "ntile",
    "cut",
    "rowMeans",
    "scale",
    "across",
    "case_when",
    "transform",
    "within",
}
PYTHON_LOAD_FUNCTIONS = {"read_csv", "read_parquet", "read_pickle", "read_feather", "read_stata"}
PYTHON_TRANSFORM_FUNCTIONS = {
    "agg",
    "aggregate",
    "assign",
    "cut",
    "groupby",
    "melt",
    "pivot",
    "pivot_table",
    "qcut",
    "rank",
    "transform",
}
AGGREGATE_OPS = {"agg", "aggregate", "summarise", "summarize"}
RESHAPE_OPS = {"melt", "pivot", "pivot_longer", "pivot_table", "pivot_wider", "reshape", "separate", "separate_wider_delim", "unite"}
ROWWISE_OPS = {
    "across",
    "assign",
    "case_when",
    "cut",
    "groupby",
    "mutate",
    "ntile",
    "qcut",
    "quantile",
    "rank",
    "rowmeans",
    "scale",
    "transform",
    "transmute",
    "within",
}
IDENTIFIER_STOPWORDS = {
    "all_of",
    "any_of",
    "by",
    "c",
    "data",
    "desc",
    "drop",
    "ends_with",
    "everything",
    "false",
    "first",
    "function",
    "ifelse",
    "include_lowest",
    "join_by",
    "labels",
    "na",
    "na_rm",
    "na_real_",
    "names",
    "on",
    "right",
    "right_index",
    "select",
    "sort",
    "starts_with",
    "true",
    "where",
}


@dataclass(slots=True)
class RepeatedLookupCluster:
    source_artifact: str
    join_keys: tuple[str, ...]
    derivation_kind: str
    paths: tuple[str, ...]
    families: tuple[str, ...]
    languages: tuple[str, ...]
    severity: str
    score_impact: float


@dataclass(slots=True)
class _Summary:
    artifact: str | None
    created_columns: set[str]
    projected_columns: set[str]
    transform_ops: set[str]


@dataclass(slots=True)
class _RAssignmentEvent:
    line: int
    rhs: str


@dataclass(slots=True)
class _RColumnAssignmentEvent:
    line: int
    column: str
    expr: str


@dataclass(slots=True)
class _PythonAssignmentEvent:
    line: int
    value: ast.AST


@dataclass(slots=True)
class _PythonColumnAssignmentEvent:
    line: int
    column: str
    value: ast.AST


def canonicalize_artifact_path(raw: str) -> str | None:
    text = raw.strip().strip("'\"")
    if not text:
        return None
    text = text.replace("\\", "/")
    text = re.sub(r"^[A-Za-z]:/+", "", text)
    parts: list[str] = []
    for chunk in text.split("/"):
        part = chunk.strip()
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    if not parts:
        return None
    if len(parts) > 3:
        parts = parts[-3:]
    return "/".join(parts)


def classify_derivation_kind(transform_ops: set[str]) -> str:
    kinds: list[str] = []
    if transform_ops & AGGREGATE_OPS:
        kinds.append("aggregate")
    if transform_ops & RESHAPE_OPS:
        kinds.append("reshape")
    if transform_ops & ROWWISE_OPS:
        kinds.append("rowwise")
    if len(kinds) == 1:
        return kinds[0]
    if len(kinds) >= 2:
        return "mixed"
    return "mixed"


def is_trivial_projection(candidate: LookupCandidate) -> bool:
    non_key_columns = set(candidate.projected_columns) - set(candidate.join_keys)
    return not candidate.derived_columns and len(non_key_columns) <= 2


def extract_lookup_candidates(path: Path, text: str, *, project_root: Path | None = None) -> list[LookupCandidate]:
    try:
        rel = path.relative_to(project_root).as_posix() if project_root is not None else path.as_posix()
    except ValueError:
        rel = path.as_posix()
    suffix = path.suffix.lower()
    if suffix == ".r":
        return _extract_r_lookup_candidates(rel, text)
    if suffix == ".py":
        return _extract_python_lookup_candidates(rel, text)
    return []


def cluster_repeated_lookup_candidates(candidates: list[LookupCandidate]) -> list[RepeatedLookupCluster]:
    clusters: list[RepeatedLookupCluster] = []
    grouped: defaultdict[tuple[str, tuple[str, ...], str], list[LookupCandidate]] = defaultdict(list)
    for candidate in candidates:
        if not candidate.source_artifact:
            continue
        grouped[(candidate.source_artifact, candidate.join_keys, candidate.derivation_kind)].append(candidate)

    for (source_artifact, join_keys, derivation_kind), group_candidates in grouped.items():
        edges: dict[int, set[int]] = {index: set() for index in range(len(group_candidates))}
        for left_index, left in enumerate(group_candidates):
            for right_index in range(left_index + 1, len(group_candidates)):
                right = group_candidates[right_index]
                if left.derived_families & right.derived_families:
                    edges[left_index].add(right_index)
                    edges[right_index].add(left_index)

        seen: set[int] = set()
        for start in range(len(group_candidates)):
            if start in seen:
                continue
            stack = [start]
            component_indices: set[int] = set()
            while stack:
                current = stack.pop()
                if current in component_indices:
                    continue
                component_indices.add(current)
                stack.extend(edges[current] - component_indices)
            seen |= component_indices
            component = [group_candidates[index] for index in sorted(component_indices)]
            paths = sorted({candidate.path for candidate in component})
            if len(paths) < 2:
                continue

            family_counts: Counter[str] = Counter()
            for candidate in component:
                family_counts.update(candidate.derived_families)
            repeated_families = tuple(
                family for family, count in family_counts.most_common() if count >= 2
            ) or tuple(sorted(family_counts))
            severity, score_impact = _severity_for_path_count(len(paths))
            clusters.append(
                RepeatedLookupCluster(
                    source_artifact=source_artifact,
                    join_keys=join_keys,
                    derivation_kind=derivation_kind,
                    paths=tuple(paths),
                    families=repeated_families,
                    languages=tuple(sorted({candidate.language for candidate in component})),
                    severity=severity,
                    score_impact=score_impact,
                )
            )

    clusters.sort(key=lambda cluster: ({"high": 0, "medium": 1, "low": 2}[cluster.severity], cluster.paths))
    return clusters


def _severity_for_path_count(path_count: int) -> tuple[str, float]:
    if path_count >= 5:
        return "high", 12
    if path_count >= 3:
        return "medium", 8
    return "low", 4


def _empty_summary() -> _Summary:
    return _Summary(artifact=None, created_columns=set(), projected_columns=set(), transform_ops=set())


def _normalize_column_family(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    normalized = re.sub(r"_(global|overall|pooled)$", "", normalized)
    normalized = re.sub(r"_within_[a-z0-9_]+$", "", normalized)
    return normalized


def _families_from_summary(summary: _Summary, join_keys: tuple[str, ...]) -> set[str]:
    created = {_normalize_column_family(column) for column in summary.created_columns}
    projected = {_normalize_column_family(column) for column in summary.projected_columns}
    join_families = {_normalize_column_family(key) for key in join_keys}
    return {
        family
        for family in created & projected
        if family and family not in join_families
    }


def _identifier_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.]*\b", text)
        if token not in IDENTIFIER_STOPWORDS
    }


def _strings_from_text(text: str) -> list[str]:
    return re.findall(r"['\"]([^'\"]+)['\"]", text)


def _strings_from_ast(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            values.extend(_strings_from_ast(item))
        return values
    return []


def _column_names_from_text(text: str) -> set[str]:
    quoted = _strings_from_text(text)
    if quoted:
        return set(quoted)
    return _identifier_tokens(text)


def _mask_string_literals(text: str) -> str:
    return re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", '""', text, flags=re.DOTALL)


def _paren_delta(text: str) -> int:
    masked = _mask_string_literals(text)
    opens = sum(masked.count(char) for char in "([{")
    closes = sum(masked.count(char) for char in ")]}")
    return opens - closes


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


def _iter_r_function_calls(text: str, function_names: set[str]):
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
        yield match.group(1), args_text, match.start()


def _should_stop_r_block(next_line: str, depth: int) -> bool:
    stripped = next_line.strip()
    if depth > 0:
        return False
    if stripped == "":
        return True
    if re.match(r"^\s*[A-Za-z][A-Za-z0-9_.]*\s*(?:<-|\$|\[\[|\[\s*,?\s*['\"])", next_line):
        return True
    return (
        not next_line.startswith((" ", "\t"))
        and not re.match(r"^\s*(%>%|\|>|\)|\+|,)", next_line)
    )


def _collect_r_rhs_block(lines: list[str], index: int, first_rhs: str) -> tuple[str, int]:
    rhs_lines = [first_rhs]
    depth = _paren_delta(lines[index])
    next_index = index + 1
    while next_index < len(lines):
        next_line = lines[next_index]
        if _should_stop_r_block(next_line, depth):
            break
        rhs_lines.append(next_line)
        depth += _paren_delta(next_line)
        next_index += 1
    return "\n".join(rhs_lines).strip(), next_index


def _extract_r_assignments(text: str) -> defaultdict[str, list[_RAssignmentEvent]]:
    assignments: defaultdict[str, list[_RAssignmentEvent]] = defaultdict(list)
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-\s*(.*)$", line)
        if not match:
            index += 1
            continue
        rhs, next_index = _collect_r_rhs_block(lines, index, match.group(2))
        assignments[match.group(1)].append(_RAssignmentEvent(line=index + 1, rhs=rhs))
        index = next_index
    return assignments


def _extract_r_column_assignments(text: str) -> defaultdict[str, list[_RColumnAssignmentEvent]]:
    column_assignments: defaultdict[str, list[_RColumnAssignmentEvent]] = defaultdict(list)
    lines = text.splitlines()
    patterns = [
        re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*\$\s*([A-Za-z][A-Za-z0-9_.]*)\s*<-\s*(.*)$"),
        re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*\[\[\s*['\"]([^'\"]+)['\"]\s*\]\]\s*<-\s*(.*)$"),
        re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*\[\s*,\s*['\"]([^'\"]+)['\"]\s*\]\s*<-\s*(.*)$"),
    ]
    index = 0
    while index < len(lines):
        line = lines[index]
        match = None
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                break
        if not match:
            index += 1
            continue
        rhs, next_index = _collect_r_rhs_block(lines, index, match.group(3))
        column_assignments[match.group(1)].append(
            _RColumnAssignmentEvent(line=index + 1, column=match.group(2), expr=rhs)
        )
        index = next_index
    return column_assignments


def _extract_r_artifact(expr: str) -> str | None:
    for _, args_text, _ in _iter_r_function_calls(expr, R_LOAD_FUNCTIONS):
        args = _split_top_level_args(args_text)
        if not args:
            continue
        path = _extract_r_path_from_arg(args[0])
        if path:
            return path
    return None


def _extract_r_path_from_arg(arg_text: str) -> str | None:
    parts = _strings_from_text(arg_text)
    if not parts:
        return None
    if len(parts) == 1:
        return canonicalize_artifact_path(parts[0])
    return canonicalize_artifact_path("/".join(parts))


def _r_source_variable(expr: str) -> str | None:
    match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*(?:%>%|\|>|\[|$)", expr)
    if match:
        token = match.group(1)
        if token not in IDENTIFIER_STOPWORDS and token not in R_LOAD_FUNCTIONS:
            return token
    call_match = re.match(r"^\s*(?:[A-Za-z0-9_.]+::)?[A-Za-z][A-Za-z0-9_.]*\s*\(", expr)
    if not call_match:
        return None
    open_paren_index = expr.find("(", call_match.end() - 1)
    if open_paren_index < 0:
        return None
    extracted = _extract_balanced_call(expr, open_paren_index)
    if extracted is None:
        return None
    args_text, _ = extracted
    args = _split_top_level_args(args_text)
    if not args:
        return None
    first_arg = args[0].strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", first_arg):
        return first_arg
    subset_match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*\[", first_arg)
    if subset_match:
        return subset_match.group(1)
    return None


def _extract_r_projected_columns(expr: str) -> set[str]:
    columns: set[str] = set()
    for _, args_text, _ in _iter_r_function_calls(expr, {"select"}):
        for arg in _split_top_level_args(args_text):
            columns.update(
                token for token in _column_names_from_text(arg) if token not in {"across"}
            )
    for _, args_text, _ in _iter_r_function_calls(expr, {"subset"}):
        args = _split_top_level_args(args_text)
        for arg in args[1:]:
            select_match = re.match(r"^\s*select\s*=\s*(.*)$", arg, flags=re.DOTALL)
            if select_match:
                columns.update(_column_names_from_text(select_match.group(1)))
    stripped = expr.strip()
    if re.match(r"^[A-Za-z][A-Za-z0-9_.]*\s*\[", stripped):
        columns.update(_strings_from_text(stripped))
    return columns


def _extract_r_created_columns(expr: str) -> set[str]:
    columns: set[str] = set()
    for function_name, args_text, _ in _iter_r_function_calls(
        expr,
        {"mutate", "transmute", "summarise", "summarize", "rename", "transform"},
    ):
        args = _split_top_level_args(args_text)
        start = 1 if function_name == "transform" else 0
        for arg in args[start:]:
            match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*=", arg)
            if match:
                columns.add(match.group(1))
        if function_name in {"mutate", "transmute"}:
            for template in re.findall(r"\.names\s*=\s*['\"]([^'\"]+)['\"]", args_text):
                columns.add(template)
    for _, args_text, _ in _iter_r_function_calls(expr, {"within"}):
        args = _split_top_level_args(args_text)
        if len(args) >= 2:
            body = args[1]
            for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_.]*)\s*<-", body):
                columns.add(match.group(1))
    for _, args_text, _ in _iter_r_function_calls(expr, {"pivot_longer", "pivot_wider", "separate", "separate_wider_delim"}):
        for arg in _split_top_level_args(args_text):
            for parameter in {"names_to", "values_to", "names_from", "values_from"}:
                match = re.match(rf"^\s*{parameter}\s*=\s*['\"]([^'\"]+)['\"]", arg)
                if match:
                    columns.add(match.group(1))
    return columns


def _extract_r_transform_ops(expr: str) -> set[str]:
    return {function_name.lower() for function_name, _, _ in _iter_r_function_calls(expr, R_TRANSFORM_FUNCTIONS)}


def _latest_r_assignment_before(
    assignments: defaultdict[str, list[_RAssignmentEvent]],
    var_name: str,
    before_line: int,
) -> _RAssignmentEvent | None:
    for assignment in reversed(assignments.get(var_name, [])):
        if assignment.line < before_line:
            return assignment
    return None


def _resolve_r_variable(
    var_name: str,
    assignments: defaultdict[str, list[_RAssignmentEvent]],
    column_assignments: defaultdict[str, list[_RColumnAssignmentEvent]],
    before_line: int,
    seen: set[tuple[str, int]],
) -> _Summary:
    assignment = _latest_r_assignment_before(assignments, var_name, before_line)
    if assignment is None:
        return _empty_summary()
    identity = (var_name, assignment.line)
    if identity in seen:
        return _empty_summary()

    summary = _analyze_r_expression(assignment.rhs, assignments, column_assignments, assignment.line, seen | {identity})
    for event in column_assignments.get(var_name, []):
        if assignment.line < event.line < before_line:
            summary.created_columns.add(event.column)
            summary.transform_ops |= _extract_r_transform_ops(event.expr)
    return summary


def _analyze_r_expression(
    expr: str,
    assignments: defaultdict[str, list[_RAssignmentEvent]],
    column_assignments: defaultdict[str, list[_RColumnAssignmentEvent]],
    before_line: int,
    seen: set[tuple[str, int]] | None = None,
) -> _Summary:
    seen = seen or set()
    expr = expr.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", expr):
        return _resolve_r_variable(expr, assignments, column_assignments, before_line, seen)

    summary = _Summary(
        artifact=_extract_r_artifact(expr),
        created_columns=_extract_r_created_columns(expr),
        projected_columns=_extract_r_projected_columns(expr),
        transform_ops=_extract_r_transform_ops(expr),
    )
    source_var = _r_source_variable(expr)
    if source_var:
        parent = _resolve_r_variable(source_var, assignments, column_assignments, before_line, seen)
        summary.artifact = summary.artifact or parent.artifact
        summary.created_columns |= parent.created_columns
        summary.transform_ops |= parent.transform_ops
        if not summary.projected_columns:
            summary.projected_columns = set(parent.projected_columns)
    if not summary.projected_columns:
        summary.projected_columns = set(summary.created_columns)
    return summary


def _extract_r_join_keys(named_args: dict[str, str]) -> tuple[str, ...]:
    keys: set[str] = set()
    if "by" in named_args:
        keys |= _column_names_from_text(named_args["by"])
    for name in ("by.x", "by.y"):
        if name in named_args:
            keys |= _column_names_from_text(named_args[name])
    return tuple(sorted(keys))


def _extract_r_lookup_candidates(rel_path: str, text: str) -> list[LookupCandidate]:
    assignments = _extract_r_assignments(text)
    column_assignments = _extract_r_column_assignments(text)
    candidates: list[LookupCandidate] = []

    for function_name, args_text, position in _iter_r_function_calls(text, R_JOIN_FUNCTIONS):
        args = _split_top_level_args(args_text)
        if not args:
            continue
        positional: list[str] = []
        named: dict[str, str] = {}
        for arg in args:
            match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_.]*)\s*=\s*(.*)$", arg, flags=re.DOTALL)
            if match:
                named[match.group(1)] = match.group(2).strip()
            else:
                positional.append(arg)

        if function_name == "merge":
            lookup_expr = named.get("y")
            if lookup_expr is None and len(positional) >= 2:
                lookup_expr = positional[1]
        else:
            lookup_expr = named.get("y")
            if lookup_expr is None:
                if len(positional) >= 2:
                    lookup_expr = positional[1]
                elif len(positional) == 1:
                    lookup_expr = positional[0]
                else:
                    lookup_expr = None
        if not lookup_expr:
            continue

        join_keys = _extract_r_join_keys(named)
        if not join_keys:
            continue

        join_line = text.count("\n", 0, position) + 1
        summary = _analyze_r_expression(lookup_expr, assignments, column_assignments, join_line)
        families = _families_from_summary(summary, join_keys)
        candidate = LookupCandidate(
            path=rel_path,
            language="r",
            source_artifact=summary.artifact,
            join_keys=join_keys,
            projected_columns=frozenset(summary.projected_columns),
            derived_columns=frozenset(summary.created_columns),
            derived_families=frozenset(families),
            transform_ops=frozenset(summary.transform_ops),
            derivation_kind=classify_derivation_kind(set(summary.transform_ops)),
        )
        if not candidate.source_artifact or not candidate.derived_families or is_trivial_projection(candidate):
            continue
        candidates.append(candidate)
    return candidates


def _python_func_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_python_assignments(
    tree: ast.AST,
) -> tuple[defaultdict[str, list[_PythonAssignmentEvent]], defaultdict[str, list[_PythonColumnAssignmentEvent]]]:
    assignments: defaultdict[str, list[_PythonAssignmentEvent]] = defaultdict(list)
    column_assignments: defaultdict[str, list[_PythonColumnAssignmentEvent]] = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _register_python_assignment(target, node.value, node.lineno, assignments, column_assignments)
        elif isinstance(node, ast.AnnAssign):
            _register_python_assignment(node.target, node.value, node.lineno, assignments, column_assignments)
    for values in assignments.values():
        values.sort(key=lambda event: event.line)
    for values in column_assignments.values():
        values.sort(key=lambda event: event.line)
    return assignments, column_assignments


def _register_python_assignment(
    target: ast.AST,
    value: ast.AST | None,
    line: int,
    assignments: defaultdict[str, list[_PythonAssignmentEvent]],
    column_assignments: defaultdict[str, list[_PythonColumnAssignmentEvent]],
) -> None:
    if value is None:
        return
    if isinstance(target, ast.Name):
        assignments[target.id].append(_PythonAssignmentEvent(line=line, value=value))
        return
    column_target = _python_column_assignment_target(target)
    if column_target is None:
        return
    var_name, column_name = column_target
    column_assignments[var_name].append(
        _PythonColumnAssignmentEvent(line=line, column=column_name, value=value)
    )


def _python_column_assignment_target(target: ast.AST) -> tuple[str, str] | None:
    if not isinstance(target, ast.Subscript):
        return None
    base = target.value
    if isinstance(base, ast.Attribute) and base.attr == "loc":
        var_name = _python_name_from_expr(base.value)
        column_names = _columns_from_python_slice(target.slice)
        if var_name and len(column_names) == 1:
            return var_name, next(iter(column_names))
        return None
    var_name = _python_name_from_expr(base)
    column_names = _columns_from_python_slice(target.slice)
    if var_name and len(column_names) == 1:
        return var_name, next(iter(column_names))
    return None


def _python_name_from_expr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _extract_python_artifact(node: ast.AST) -> str | None:
    for subnode in ast.walk(node):
        if not isinstance(subnode, ast.Call):
            continue
        func_name = _python_func_name(subnode.func)
        if func_name not in PYTHON_LOAD_FUNCTIONS:
            continue
        path_node = subnode.args[0] if subnode.args else next(
            (keyword.value for keyword in subnode.keywords if keyword.arg in {"filepath_or_buffer", "path", "path_or_buf"}),
            None,
        )
        if path_node is None:
            continue
        path = _extract_python_path(path_node)
        if path:
            return path
    return None


def _extract_python_path(node: ast.AST) -> str | None:
    segments = _python_path_segments(node)
    if not segments:
        return None
    return canonicalize_artifact_path("/".join(segments))


def _python_path_segments(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
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
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"join", "joinpath"}:
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


def _extract_python_projected_columns(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "loc":
            if isinstance(node.slice, ast.Tuple) and len(node.slice.elts) >= 2:
                return _columns_from_python_slice(node.slice.elts[1])
            return set()
        return _columns_from_python_slice(node.slice)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "filter" and node.args:
        return set(_strings_from_ast(node.args[0]))
    return set()


def _columns_from_python_slice(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {value for value in _strings_from_ast(node) if value}
    return set()


def _extract_python_created_columns(node: ast.AST) -> set[str]:
    columns: set[str] = set()
    for subnode in ast.walk(node):
        if not isinstance(subnode, ast.Call):
            continue
        func_name = _python_func_name(subnode.func)
        if func_name == "assign":
            columns.update(keyword.arg for keyword in subnode.keywords if keyword.arg)
        elif func_name in {"agg", "aggregate"}:
            columns.update(keyword.arg for keyword in subnode.keywords if keyword.arg)
        elif func_name == "rename":
            for keyword in subnode.keywords:
                if keyword.arg == "columns" and isinstance(keyword.value, ast.Dict):
                    for value in keyword.value.values:
                        columns.update(_strings_from_ast(value))
        elif func_name == "melt":
            for keyword in subnode.keywords:
                if keyword.arg in {"var_name", "value_name"}:
                    columns.update(_strings_from_ast(keyword.value))
    return columns


def _extract_python_transform_ops(node: ast.AST) -> set[str]:
    transforms: set[str] = set()
    for subnode in ast.walk(node):
        if not isinstance(subnode, ast.Call):
            continue
        func_name = _python_func_name(subnode.func)
        if func_name in PYTHON_TRANSFORM_FUNCTIONS:
            transforms.add("agg" if func_name == "aggregate" else func_name)
    return transforms


def _latest_python_assignment_before(
    assignments: defaultdict[str, list[_PythonAssignmentEvent]],
    var_name: str,
    before_line: int,
) -> _PythonAssignmentEvent | None:
    for assignment in reversed(assignments.get(var_name, [])):
        if assignment.line < before_line:
            return assignment
    return None


def _python_source_variable(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "loc":
            return _python_source_variable(node.value.value)
        return _python_source_variable(node.value)
    if isinstance(node, ast.Call):
        func_name = _python_func_name(node.func)
        if func_name == "merge":
            if isinstance(node.func, ast.Attribute):
                return _python_source_variable(node.func.value)
            if node.args:
                return _python_source_variable(node.args[0])
        if isinstance(node.func, ast.Attribute):
            return _python_source_variable(node.func.value)
    if isinstance(node, ast.Attribute):
        return _python_source_variable(node.value)
    return None


def _resolve_python_variable(
    var_name: str,
    assignments: defaultdict[str, list[_PythonAssignmentEvent]],
    column_assignments: defaultdict[str, list[_PythonColumnAssignmentEvent]],
    before_line: int,
    seen: set[tuple[str, int]],
) -> _Summary:
    assignment = _latest_python_assignment_before(assignments, var_name, before_line)
    if assignment is None:
        return _empty_summary()
    identity = (var_name, assignment.line)
    if identity in seen:
        return _empty_summary()
    summary = _analyze_python_expression(assignment.value, assignments, column_assignments, assignment.line, seen | {identity})
    for event in column_assignments.get(var_name, []):
        if assignment.line < event.line < before_line:
            summary.created_columns.add(event.column)
            summary.transform_ops |= _extract_python_transform_ops(event.value)
    return summary


def _analyze_python_expression(
    node: ast.AST,
    assignments: defaultdict[str, list[_PythonAssignmentEvent]],
    column_assignments: defaultdict[str, list[_PythonColumnAssignmentEvent]],
    before_line: int,
    seen: set[tuple[str, int]] | None = None,
) -> _Summary:
    seen = seen or set()
    if isinstance(node, ast.Name):
        return _resolve_python_variable(node.id, assignments, column_assignments, before_line, seen)

    summary = _Summary(
        artifact=_extract_python_artifact(node),
        created_columns=_extract_python_created_columns(node),
        projected_columns=_extract_python_projected_columns(node),
        transform_ops=_extract_python_transform_ops(node),
    )
    source_var = _python_source_variable(node)
    if source_var:
        parent = _resolve_python_variable(source_var, assignments, column_assignments, before_line, seen)
        summary.artifact = summary.artifact or parent.artifact
        summary.created_columns |= parent.created_columns
        summary.transform_ops |= parent.transform_ops
        if not summary.projected_columns:
            summary.projected_columns = set(parent.projected_columns)
    if not summary.projected_columns:
        summary.projected_columns = set(summary.created_columns)
    return summary


def _extract_python_join_keys(node: ast.Call) -> tuple[str, ...]:
    keys: set[str] = set()
    for keyword in node.keywords:
        if keyword.arg in {"on", "left_on", "right_on"}:
            keys.update(value for value in _strings_from_ast(keyword.value) if value)
    return tuple(sorted(keys))


def _python_lookup_side(node: ast.Call) -> ast.AST | None:
    func_name = _python_func_name(node.func)
    if func_name == "merge":
        if isinstance(node.func, ast.Attribute):
            if node.args:
                return node.args[0]
            return next((keyword.value for keyword in node.keywords if keyword.arg == "right"), None)
        if len(node.args) >= 2:
            return node.args[1]
        return next((keyword.value for keyword in node.keywords if keyword.arg == "right"), None)
    if func_name == "join" and isinstance(node.func, ast.Attribute):
        if node.args:
            return node.args[0]
        return next((keyword.value for keyword in node.keywords if keyword.arg in {"other", "right"}), None)
    return None


def _extract_python_lookup_candidates(rel_path: str, text: str) -> list[LookupCandidate]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    assignments, column_assignments = _extract_python_assignments(tree)
    candidates: list[LookupCandidate] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _python_func_name(node.func)
        if func_name not in {"merge", "join"}:
            continue
        lookup_node = _python_lookup_side(node)
        if lookup_node is None:
            continue
        join_keys = _extract_python_join_keys(node)
        if not join_keys:
            continue
        summary = _analyze_python_expression(lookup_node, assignments, column_assignments, node.lineno)
        families = _families_from_summary(summary, join_keys)
        candidate = LookupCandidate(
            path=rel_path,
            language="python",
            source_artifact=summary.artifact,
            join_keys=join_keys,
            projected_columns=frozenset(summary.projected_columns),
            derived_columns=frozenset(summary.created_columns),
            derived_families=frozenset(families),
            transform_ops=frozenset(summary.transform_ops),
            derivation_kind=classify_derivation_kind(set(summary.transform_ops)),
        )
        if not candidate.source_artifact or not candidate.derived_families or is_trivial_projection(candidate):
            continue
        candidates.append(candidate)
    return candidates
