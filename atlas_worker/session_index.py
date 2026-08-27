"""Private one-pass session indexing and deterministic project ownership mapping."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .models import ProjectRef, SessionEvent, SessionMapping, SessionTrace
from .sessions import map_project_path, normalize_codex_record, normalize_local_path


_PATCH_TARGET = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File:|Move to:) (.+?)\s*$", re.MULTILINE
)
_TOOL_TYPES = frozenset({"function_call", "function_call_output", "tool_call", "custom_tool_call"})
_PATH_KEYS = ("cwd", "workdir", "path")
_GIT_COMMON_DIR_KEYS = ("git_common_dir", "git_common_dirs")
_LOCATION_KEYS = ("cwd", "workdir")
_CUSTOM_WRAPPER_NAMES = frozenset({"exec_command"})


class GitOwner(Protocol):
    def __call__(self, path: Path, projects: Sequence[ProjectRef]) -> str | None:
        """Return a project ID only when Task 2 common-dir ownership is unique."""


def index_session(path: Path) -> SessionTrace:
    """Read one JSONL source once, retaining events and structured ownership evidence."""
    session_id = ""
    parent_session_id = ""
    cwd = ""
    changed_paths: list[str] = []
    git_common_dirs: list[str] = []
    events = []
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                events.append(
                    SessionEvent(
                        session_id=session_id,
                        timestamp="",
                        cwd=cwd,
                        role="system",
                        text="",
                        source_path=str(path),
                        line_number=line_number,
                        parse_error="invalid_json",
                    )
                )
                continue

            event, session_id, cwd = normalize_codex_record(raw, path, line_number, session_id, cwd)
            if event is not None:
                events.append(event)
            parent_session_id = _parent_session_id(raw) or parent_session_id
            tool_record = _tool_record(raw)
            if tool_record is None:
                continue
            locations, explicit_paths = _tool_path_evidence(tool_record, cwd)
            if locations:
                cwd = locations[-1]
            changed_paths.extend(explicit_paths)
            changed_paths.extend(_patch_targets(tool_record, cwd))
            git_common_dirs.extend(_structured_values(tool_record, _GIT_COMMON_DIR_KEYS))

    return SessionTrace(
        session_id=session_id,
        parent_session_id=parent_session_id,
        cwd=cwd,
        changed_paths=_unique_paths(changed_paths),
        git_common_dirs=_unique_paths(git_common_dirs),
        events=tuple(events),
    )


def map_session_trace(
    trace: SessionTrace,
    projects: Sequence[ProjectRef],
    aliases: Mapping[str, str],
    git_owner: GitOwner,
) -> SessionMapping:
    """Apply direct ownership evidence in strict priority order, failing closed on ties."""
    changed = _path_mapping(trace.changed_paths, projects, aliases, include_aliases=False)
    if changed is not None:
        return _mapping(trace.session_id, changed, "changed-path")

    common_dir_owners = _git_owners(
        (*trace.changed_paths, *trace.git_common_dirs), projects, git_owner
    )
    if common_dir_owners:
        return _mapping(trace.session_id, common_dir_owners, "git-common-dir")

    cwd = _path_mapping((trace.cwd,), projects, aliases, include_aliases=False)
    if cwd is not None:
        return _mapping(trace.session_id, cwd, "cwd")

    alias = _path_mapping((trace.cwd,), projects, aliases, include_roots=False)
    if alias is not None:
        return _mapping(trace.session_id, alias, "alias")
    return SessionMapping(session_id=trace.session_id, project_id=None, reason="unmapped")


def merge_child_evidence(
    traces: Sequence[SessionTrace], mappings: Sequence[SessionMapping]
) -> tuple[SessionMapping, ...]:
    """Inherit only unambiguous mapped parents and record children deterministically."""
    rows = tuple(zip(traces, mappings))
    session_id_counts: dict[str, int] = {}
    for trace, _ in rows:
        if trace.session_id:
            session_id_counts[trace.session_id] = session_id_counts.get(trace.session_id, 0) + 1
    duplicate_ids = {
        session_id for session_id, count in session_id_counts.items() if count > 1
    }
    by_id = {
        trace.session_id: (index, trace)
        for index, (trace, _) in enumerate(rows)
        if trace.session_id and trace.session_id not in duplicate_ids
    }
    cycle_ids = _parent_cycle_ids({session_id: trace for session_id, (_, trace) in by_id.items()})
    resolved = list(mappings)

    for index, (trace, mapping) in enumerate(rows):
        if trace.session_id in duplicate_ids or (
            trace.session_id in cycle_ids and mapping.reason == "unmapped"
        ):
            resolved[index] = SessionMapping(
                session_id=mapping.session_id,
                project_id=None,
                reason="ambiguous",
                child_session_ids=(),
            )

    children: dict[str, list[str]] = {}
    for trace, _ in rows:
        if (
            trace.session_id in by_id
            and trace.session_id not in cycle_ids
            and trace.parent_session_id in by_id
        ):
            children.setdefault(trace.parent_session_id, []).append(trace.session_id)

    changed = True
    while changed:
        changed = False
        for session_id in sorted(by_id):
            index, trace = by_id[session_id]
            current = resolved[index]
            parent_row = by_id.get(trace.parent_session_id)
            parent = resolved[parent_row[0]] if parent_row is not None else None
            if (
                current.reason != "unmapped"
                or parent is None
                or parent.project_id is None
                or session_id in cycle_ids
            ):
                continue
            resolved[index] = SessionMapping(
                session_id=current.session_id,
                project_id=parent.project_id,
                reason="parent-session",
                child_session_ids=current.child_session_ids,
            )
            changed = True

    result = []
    for index, (_, mapping) in enumerate(rows):
        current = resolved[index]
        result.append(
            SessionMapping(
                session_id=current.session_id,
                project_id=current.project_id,
                reason=current.reason,
                child_session_ids=tuple(
                    sorted(set(children.get(current.session_id, ())))
                ),
            )
        )
    return tuple(result)


def _parent_cycle_ids(traces: Mapping[str, SessionTrace]) -> set[str]:
    cycles: set[str] = set()
    for session_id in sorted(traces):
        positions: dict[str, int] = {}
        path: list[str] = []
        cursor = session_id
        while cursor in traces and cursor not in positions:
            positions[cursor] = len(path)
            path.append(cursor)
            cursor = traces[cursor].parent_session_id
        if cursor in positions:
            cycles.update(path[positions[cursor] :])
    return cycles


def _parent_session_id(raw: object) -> str:
    if not isinstance(raw, dict) or not isinstance(raw.get("payload"), dict):
        return ""
    payload = raw["payload"]
    for container in (payload, payload.get("item")):
        if not isinstance(container, dict):
            continue
        for key in ("parent_session_id", "parent_id"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _tool_record(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("payload"), dict):
        return None
    payload = raw["payload"]
    item = payload.get("item")
    candidate = item if isinstance(item, dict) else payload
    record_type = candidate.get("type")
    if isinstance(record_type, str) and record_type in _TOOL_TYPES:
        return candidate
    if raw.get("type") in _TOOL_TYPES:
        return payload
    return None


def _tool_path_evidence(
    record: Mapping[str, object], current_cwd: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values = (
        _custom_wrapper_values(record)
        if record.get("type") == "custom_tool_call"
        else _record_structured_values(record)
    )
    locations: list[str] = []
    explicit_paths: list[str] = []
    base = current_cwd
    for value in values:
        for key in _LOCATION_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                base = _resolve_path(candidate, base)
                if base:
                    locations.append(base)
        candidate = value.get("path")
        if isinstance(candidate, str) and candidate:
            resolved = _resolve_path(candidate, base)
            if resolved:
                explicit_paths.append(resolved)
    return _unique_paths(locations), _unique_paths(explicit_paths)


def _record_structured_values(record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    containers: list[object] = [record]
    for key in ("arguments", "input"):
        value = record.get(key)
        if isinstance(value, (dict, list)):
            containers.append(value)
        elif isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, (dict, list)):
                containers.append(decoded)
    return tuple(_walk_structured_mappings(containers))


def _custom_wrapper_values(record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = record.get("input")
    if not isinstance(value, str):
        return ()
    return _parse_custom_wrappers(value)


def _structured_values(record: Mapping[str, object], keys: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for value in _record_structured_values(record):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                values.append(candidate.strip())
            elif isinstance(candidate, list):
                values.extend(item.strip() for item in candidate if isinstance(item, str) and item.strip())
    return tuple(values)


def _walk_structured_mappings(values: Sequence[object]):
    pending = list(reversed(values))
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            yield value
            pending.extend(reversed(tuple(value.values())))
        elif isinstance(value, list):
            pending.extend(reversed(value))


def _parse_custom_wrappers(source: str) -> tuple[Mapping[str, object], ...]:
    tokens = _tokenize_javascript(source)
    if tokens is None:
        return ()
    values: list[Mapping[str, object]] = []
    for statement in _top_level_statements(tokens):
        values.extend(_parse_top_level_statement(statement))
    return tuple(values)


def _top_level_statements(
    tokens: Sequence[tuple[str, str]],
) -> tuple[tuple[tuple[str, str], ...], ...]:
    statements: list[tuple[tuple[str, str], ...]] = []
    openings = {"(": ")", "[": "]", "{": "}"}
    closings = set(openings.values())
    stack: list[str] = []
    start = 0
    for index, (_, value) in enumerate(tokens):
        if value in openings:
            stack.append(openings[value])
        elif value in closings:
            if not stack or value != stack[-1]:
                return tuple(statements)
            stack.pop()
        elif value == ";" and not stack:
            if index > start:
                statements.append(tuple(tokens[start:index]))
            start = index + 1
    if not stack and start < len(tokens):
        statements.append(tuple(tokens[start:]))
    return tuple(statements)


def _parse_top_level_statement(
    tokens: Sequence[tuple[str, str]],
) -> tuple[Mapping[str, object], ...]:
    index = _assignment_end(tokens)
    if index is None:
        return ()
    if index < len(tokens) and tokens[index][1] == "await":
        index += 1
    direct = _parse_allowlisted_call(tokens, index)
    if direct is not None and direct[1] == len(tokens):
        return (direct[0],)
    promise = _parse_promise_all(tokens, index)
    if promise is not None and promise[1] == len(tokens):
        return promise[0]
    return ()


def _assignment_end(tokens: Sequence[tuple[str, str]]) -> int | None:
    if not tokens:
        return None
    if tokens[0][1] in {"const", "let", "var"}:
        if len(tokens) < 3 or tokens[1][0] != "identifier" or tokens[2][1] != "=":
            return None
        return 3
    if len(tokens) >= 2 and tokens[0][0] == "identifier" and tokens[1][1] == "=":
        return 2
    return 0


def _parse_promise_all(
    tokens: Sequence[tuple[str, str]], start: int
) -> tuple[tuple[Mapping[str, object], ...], int] | None:
    if not _matches(tokens, start, ("Promise", ".", "all", "(", "[")):
        return None
    values: list[Mapping[str, object]] = []
    index = start + 5
    while index < len(tokens):
        call = _parse_allowlisted_call(tokens, index)
        if call is None:
            return None
        values.append(call[0])
        index = call[1]
        if index < len(tokens) and tokens[index][1] == ",":
            index += 1
            continue
        if index + 1 < len(tokens) and tokens[index][1] == "]" and tokens[index + 1][1] == ")":
            return tuple(values), index + 2
        return None
    return None


def _parse_allowlisted_call(
    tokens: Sequence[tuple[str, str]], start: int
) -> tuple[Mapping[str, object], int] | None:
    if not _matches(tokens, start, ("tools", ".")):
        return None
    name_index = start + 2
    if (
        name_index + 2 >= len(tokens)
        or tokens[name_index][0] != "identifier"
        or tokens[name_index][1] not in _CUSTOM_WRAPPER_NAMES
        or tokens[name_index + 1][1] != "("
        or tokens[name_index + 2][1] != "{"
    ):
        return None
    parsed = _parse_object_literal(tokens, name_index + 2)
    if parsed is None or parsed[1] >= len(tokens) or tokens[parsed[1]][1] != ")":
        return None
    return parsed[0], parsed[1] + 1


def _matches(
    tokens: Sequence[tuple[str, str]], start: int, values: Sequence[str]
) -> bool:
    return len(tokens) >= start + len(values) and all(
        tokens[start + offset][1] == value for offset, value in enumerate(values)
    )


def _parse_object_literal(
    tokens: Sequence[tuple[str, str]], start: int
) -> tuple[dict[str, object], int] | None:
    values: dict[str, object] = {}
    index = start + 1
    while index < len(tokens):
        if tokens[index][1] == "}":
            return values, index + 1
        kind, key = tokens[index]
        if kind not in {"identifier", "string"}:
            return None
        if index + 2 >= len(tokens) or tokens[index + 1][1] != ":":
            return None
        value_kind, value = tokens[index + 2]
        if value_kind == "string":
            values[key] = value
        elif value_kind == "identifier" and value in {"true", "false", "null"}:
            values[key] = value
        elif value_kind == "number":
            values[key] = value
        else:
            return None
        index += 3
        if index >= len(tokens):
            return None
        if tokens[index][1] == "}":
            return values, index + 1
        if tokens[index][1] != ",":
            return None
        index += 1
    return None


def _tokenize_javascript(source: str) -> tuple[tuple[str, str], ...] | None:
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            index = len(source) if end < 0 else end + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                return None
            index = end + 2
            continue
        if character in {"'", '"'}:
            parsed = _read_js_string(source, index)
            if parsed is None:
                return None
            value, index = parsed
            tokens.append(("string", value))
            continue
        if character == "`":
            return None
        if character.isalpha() or character in {"_", "$"}:
            end = index + 1
            while end < len(source) and (source[end].isalnum() or source[end] in {"_", "$"}):
                end += 1
            tokens.append(("identifier", source[index:end]))
            index = end
            continue
        if character.isdigit():
            end = index + 1
            while end < len(source) and (source[end].isdigit() or source[end] == "."):
                end += 1
            tokens.append(("number", source[index:end]))
            index = end
            continue
        tokens.append(("punctuation", character))
        index += 1
    return tuple(tokens)


def _read_js_string(source: str, start: int) -> tuple[str, int] | None:
    quote = source[start]
    parts: list[str] = []
    index = start + 1
    while index < len(source):
        character = source[index]
        if character == quote:
            return "".join(parts), index + 1
        if character != "\\":
            parts.append(character)
            index += 1
            continue
        if index + 1 >= len(source):
            return None
        escaped = source[index + 1]
        escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
        if escaped == "u":
            digits = source[index + 2 : index + 6]
            if len(digits) != 4 or any(digit not in "0123456789abcdefABCDEF" for digit in digits):
                return None
            parts.append(chr(int(digits, 16)))
            index += 6
        elif escaped == "x":
            digits = source[index + 2 : index + 4]
            if len(digits) != 2 or any(digit not in "0123456789abcdefABCDEF" for digit in digits):
                return None
            parts.append(chr(int(digits, 16)))
            index += 4
        elif escaped in escapes:
            parts.append(escapes[escaped])
            index += 2
        elif escaped in {"\\", "'", '"', "/"}:
            parts.append(escaped)
            index += 2
        else:
            return None
    return None


def _patch_targets(record: Mapping[str, object], cwd: str) -> tuple[str, ...]:
    name = record.get("name")
    if not isinstance(name, str) or name.rsplit(".", 1)[-1] != "apply_patch":
        return ()
    patch = _patch_text(record)
    if not patch:
        return ()
    return _unique_paths(_resolve_path(target, cwd) for target in _PATCH_TARGET.findall(patch))


def _patch_text(record: Mapping[str, object]) -> str:
    for key in ("input", "arguments"):
        value = record.get(key)
        if isinstance(value, str) and "*** " in value:
            return value
        if isinstance(value, dict):
            for nested in ("patch", "input"):
                candidate = value.get(nested)
                if isinstance(candidate, str) and "*** " in candidate:
                    return candidate
    return ""


def _resolve_path(value: str, base: str) -> str:
    normalized = normalize_local_path(value)
    if not normalized:
        return ""
    if base and not normalized.startswith("/") and not re.match(r"^[A-Za-z]:", normalized):
        return normalize_local_path(posixpath.join(normalize_local_path(base), normalized))
    return normalized


def _unique_paths(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _path_mapping(
    paths: Sequence[str],
    projects: Sequence[ProjectRef],
    aliases: Mapping[str, str],
    *,
    include_roots: bool = True,
    include_aliases: bool = True,
) -> str | None:
    owners = {
        project_id
        for path in paths
        if (project_id := map_project_path(
            path,
            projects,
            aliases,
            include_roots=include_roots,
            include_aliases=include_aliases,
        )) is not None
    }
    if len(owners) == 1:
        return next(iter(owners))
    return "ambiguous" if owners else None


def _git_owners(
    paths: Sequence[str], projects: Sequence[ProjectRef], git_owner: GitOwner
) -> str | None:
    owners = {owner for path in paths if (owner := git_owner(Path(path), projects)) is not None}
    if len(owners) == 1:
        return next(iter(owners))
    return "ambiguous" if owners else None


def _mapping(session_id: str, project_id: str, reason: str) -> SessionMapping:
    if project_id == "ambiguous":
        return SessionMapping(session_id=session_id, project_id=None, reason="ambiguous")
    return SessionMapping(session_id=session_id, project_id=project_id, reason=reason)  # type: ignore[arg-type]
