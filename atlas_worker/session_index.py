"""Private one-pass session indexing and deterministic project ownership mapping."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .models import ProjectRef, SessionMapping, SessionTrace
from .sessions import map_project_path, normalize_codex_record, normalize_local_path


_PATCH_TARGET = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.MULTILINE)
_TOOL_TYPES = frozenset({"function_call", "function_call_output", "tool_call", "custom_tool_call"})
_PATH_KEYS = ("cwd", "workdir", "path")
_GIT_COMMON_DIR_KEYS = ("git_common_dir", "git_common_dirs")


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
                from .models import SessionEvent

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
            tool_paths = _structured_paths(tool_record)
            changed_paths.extend(tool_paths)
            changed_paths.extend(_patch_targets(tool_record, tool_paths, cwd))
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
    trace_by_id = {trace.session_id: trace for trace in traces if trace.session_id}
    mapping_by_id = {mapping.session_id: mapping for mapping in mappings}
    children: dict[str, list[str]] = {}
    for trace in traces:
        if trace.session_id and trace.parent_session_id in trace_by_id:
            children.setdefault(trace.parent_session_id, []).append(trace.session_id)

    changed = True
    while changed:
        changed = False
        for trace in traces:
            current = mapping_by_id.get(trace.session_id)
            parent = mapping_by_id.get(trace.parent_session_id)
            if (
                current is None
                or current.reason != "unmapped"
                or parent is None
                or parent.project_id is None
                or parent.reason == "ambiguous"
            ):
                continue
            mapping_by_id[trace.session_id] = SessionMapping(
                session_id=current.session_id,
                project_id=parent.project_id,
                reason="parent-session",
                child_session_ids=current.child_session_ids,
            )
            changed = True

    result = []
    for mapping in mappings:
        resolved = mapping_by_id[mapping.session_id]
        result.append(
            SessionMapping(
                session_id=resolved.session_id,
                project_id=resolved.project_id,
                reason=resolved.reason,
                child_session_ids=tuple(sorted(set(children.get(resolved.session_id, ())))),
            )
        )
    return tuple(result)


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


def _structured_paths(record: Mapping[str, object]) -> tuple[str, ...]:
    values = _structured_values(record, _PATH_KEYS)
    workdirs = _structured_values(record, ("workdir", "cwd"))
    base = next((value for value in workdirs if value), "")
    return _unique_paths(_resolve_path(value, base) for value in values)


def _structured_values(record: Mapping[str, object], keys: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for value in _walk_structured_values(record):
        if not isinstance(value, dict):
            continue
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                values.append(candidate.strip())
            elif isinstance(candidate, list):
                values.extend(item.strip() for item in candidate if isinstance(item, str) and item.strip())
    return tuple(values)


def _walk_structured_values(record: Mapping[str, object]):
    pending: list[object] = [record]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            yield value
            pending.extend(reversed(tuple(value.values())))
        elif isinstance(value, list):
            pending.extend(reversed(value))
        elif isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, (dict, list)):
                pending.append(decoded)


def _patch_targets(record: Mapping[str, object], tool_paths: tuple[str, ...], cwd: str) -> tuple[str, ...]:
    name = record.get("name")
    if not isinstance(name, str) or name.rsplit(".", 1)[-1] != "apply_patch":
        return ()
    patch = _patch_text(record)
    if not patch:
        return ()
    base = next((path for path in tool_paths if path), cwd)
    return _unique_paths(_resolve_path(target, base) for target in _PATCH_TARGET.findall(patch))


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
