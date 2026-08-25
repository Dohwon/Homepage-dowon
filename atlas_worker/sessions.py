"""Streaming normalization and deterministic project mapping for local sessions."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from .models import ProjectRef, SessionEvent


_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:")
_TEXT_BLOCK_TYPES = {"input_text", "output_text", "text"}


def iter_session_events(path: Path) -> Iterator[SessionEvent]:
    """Yield retained Codex event shapes without loading a JSONL file at once."""
    session_id = ""
    cwd = ""
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                yield SessionEvent(
                    session_id=session_id,
                    timestamp="",
                    cwd=cwd,
                    role="system",
                    text="",
                    source_path=str(path),
                    line_number=line_number,
                    parse_error="invalid_json",
                )
                continue

            event, session_id, cwd = normalize_codex_record(raw, path, line_number, session_id, cwd)
            if event is not None:
                yield event


def normalize_codex_record(
    raw: object,
    path: Path,
    line_number: int,
    session_id: str = "",
    cwd: str = "",
) -> tuple[SessionEvent | None, str, str]:
    """Normalize only session metadata, turn context, and message response items."""
    if not isinstance(raw, dict):
        return None, session_id, cwd

    record_type = raw.get("type")
    payload = raw.get("payload")
    if not isinstance(record_type, str) or not isinstance(payload, dict):
        return None, session_id, cwd

    timestamp = _string_value(raw.get("timestamp")) or _string_value(payload.get("timestamp"))
    if record_type == "session_meta":
        session_id = _string_value(payload.get("id")) or session_id
        cwd = _string_value(payload.get("cwd")) or cwd
        return _event(session_id, timestamp, cwd, "system", "", path, line_number), session_id, cwd

    if record_type == "turn_context":
        session_id = _string_value(payload.get("session_id")) or session_id
        cwd = _string_value(payload.get("cwd")) or cwd
        return _event(session_id, timestamp, cwd, "system", "", path, line_number), session_id, cwd

    if record_type != "response_item":
        return None, session_id, cwd

    item = payload.get("item")
    if not isinstance(item, dict):
        item = payload
    if item.get("type") != "message":
        return None, session_id, cwd

    item_session_id = _string_value(item.get("session_id")) or session_id
    item_cwd = _string_value(item.get("cwd")) or cwd
    role = _string_value(item.get("role"))
    text = _message_text(item.get("content"))
    if not role or text is None:
        return None, session_id, cwd
    return (
        _event(item_session_id, timestamp, item_cwd, role, text, path, line_number),
        item_session_id,
        item_cwd,
    )


def map_session(
    event: SessionEvent,
    projects: Sequence[ProjectRef],
    aliases: Mapping[str, str],
) -> str | None:
    """Map a session cwd to the nearest project root or explicit historical alias."""
    cwd = _normalized_path(event.cwd)
    if not cwd:
        return None

    project_ids = {project.project_id for project in projects}
    candidates: list[tuple[str, str]] = []
    for project in projects:
        candidates.append((_normalized_path(str(project.root)), project.project_id))
        for alias in project.aliases:
            normalized = _normalized_path(alias)
            if normalized.startswith("/") or _WINDOWS_DRIVE.match(normalized):
                candidates.append((normalized, project.project_id))
    for alias, project_id in aliases.items():
        if project_id in project_ids:
            candidates.append((_normalized_path(alias), project_id))

    matches = [
        (candidate, project_id)
        for candidate, project_id in candidates
        if candidate and _component_prefix(cwd, candidate)
    ]
    if not matches:
        return None
    return min(matches, key=lambda item: (-_path_depth(item[0]), item[1], item[0]))[1]


def _event(
    session_id: str,
    timestamp: str,
    cwd: str,
    role: str,
    text: str,
    path: Path,
    line_number: int,
) -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        timestamp=timestamp,
        cwd=cwd,
        role=role,
        text=text,
        source_path=str(path),
        line_number=line_number,
    )


def _message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") in _TEXT_BLOCK_TYPES
        and isinstance(block.get("text"), str)
    ]
    return "\n".join(parts) if parts else None


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalized_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    if not candidate:
        return ""
    normalized = posixpath.normpath(candidate)
    return normalized.casefold() if _WINDOWS_DRIVE.match(normalized) else normalized


def _component_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _path_depth(path: str) -> int:
    return len(tuple(part for part in path.split("/") if part))
