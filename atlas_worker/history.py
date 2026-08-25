"""Typed parsing and rendering for Atlas-managed project history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from .models import ProjectEvent


EVENT_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_START_MARKER = re.compile(rf"<!-- atlas:event:({EVENT_ID_PATTERN}) -->$")
_END_MARKER = re.compile(rf"<!-- /atlas:event:({EVENT_ID_PATTERN}) -->$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_EVENT_HEADING = re.compile(r"^### (\d{4}-\d{2}-\d{2}) · (.+)$")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,}).*$")
_SECTION_NAMES = {
    "build story": "build_story",
    "build-story": "build_story",
    "build_story": "build_story",
    "decisions": "decisions",
    "rollbacks": "rollbacks",
}
_EVENT_TYPES = {
    ("decisions", "Decision"): "decision",
    ("rollbacks", "Rollback"): "rollback",
    ("build_story", "Revision"): "revision",
    ("build_story", "Resolved Failure"): "failure",
}


@dataclass(frozen=True)
class ManagedEventBlock:
    event: ProjectEvent
    section: str
    start_line: int
    end_line: int


def render_managed_event(event: ProjectEvent) -> str:
    """Render the sole managed-event wire format."""
    _validate_event(event)
    return (
        f"<!-- atlas:event:{event.event_id} -->\n"
        f"### {event.date} · {event.title}\n\n"
        f"- 상황: {event.context}\n"
        f"- 선택: {event.decision}\n"
        f"- 결과: {event.outcome}\n"
        f"<!-- /atlas:event:{event.event_id} -->\n"
    )


def parse_managed_events(content: str) -> tuple[ManagedEventBlock, ...]:
    """Parse exact balanced event blocks under their owning level-two section."""
    lines = content.splitlines()
    blocks: list[ManagedEventBlock] = []
    seen_ids: set[str] = set()
    active_section: str | None = None
    fence: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if fence is not None:
            if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
                fence = None
            index += 1
            continue
        opened = _FENCE_OPEN.match(line)
        if opened:
            fence = opened.group(1)
            index += 1
            continue
        if "atlas:event:" in line:
            start = _START_MARKER.fullmatch(line)
            if start is None:
                raise ValueError("malformed managed event markers")
            event_id = start.group(1)
            if event_id in seen_ids or active_section is None:
                raise ValueError("malformed managed event markers")
            end_line = index + 6
            if end_line >= len(lines):
                raise ValueError("malformed managed event markers")
            end = _END_MARKER.fullmatch(lines[end_line])
            if end is None or end.group(1) != event_id:
                raise ValueError("malformed managed event markers")
            event = _parse_event_body(event_id, active_section, lines[index + 1 : end_line])
            blocks.append(
                ManagedEventBlock(
                    event=event,
                    section=active_section,
                    start_line=index,
                    end_line=end_line,
                )
            )
            seen_ids.add(event_id)
            index = end_line + 1
            continue
        heading = _HEADING.fullmatch(line)
        if heading:
            level = len(heading.group(1))
            if level == 2:
                active_section = _SECTION_NAMES.get(
                    heading.group(2).strip().casefold()
                )
            elif level < 2:
                active_section = None
        index += 1
    if fence is not None:
        raise ValueError("unsafe Markdown structure")
    return tuple(blocks)


def _parse_event_body(
    event_id: str, section: str, body: list[str]
) -> ProjectEvent:
    if len(body) != 5 or body[1] != "":
        raise ValueError("malformed managed event block")
    heading = _EVENT_HEADING.fullmatch(body[0])
    if heading is None:
        raise ValueError("malformed managed event block")
    event_date, title = heading.groups()
    try:
        date.fromisoformat(event_date)
    except ValueError:
        raise ValueError("malformed managed event block") from None
    stage = _EVENT_TYPES.get((section, title))
    if stage is None:
        raise ValueError("malformed managed event block")
    context = _field(body[2], "- 상황: ")
    decision = _field(body[3], "- 선택: ")
    outcome = _field(body[4], "- 결과: ")
    return ProjectEvent(
        event_id=event_id,
        date=event_date,
        title=title,
        context=context,
        decision=decision,
        outcome=outcome,
        stage=stage,
    )


def _field(line: str, prefix: str) -> str:
    if not line.startswith(prefix) or not line[len(prefix) :]:
        raise ValueError("malformed managed event block")
    return line[len(prefix) :]


def _validate_event(event: ProjectEvent) -> None:
    if not re.fullmatch(EVENT_ID_PATTERN, event.event_id):
        raise ValueError("managed event has an invalid event_id")
    if _EVENT_TYPES.get((_section_for_stage(event.stage), event.title)) != event.stage:
        raise ValueError("managed event has an invalid title or stage")
    try:
        date.fromisoformat(event.date)
    except ValueError:
        raise ValueError("managed event has an invalid date") from None
    if any(not value or "\n" in value or "\r" in value for value in (
        event.context,
        event.decision,
        event.outcome,
    )):
        raise ValueError("managed event fields must be non-empty single lines")


def _section_for_stage(stage: str) -> str:
    return {
        "decision": "decisions",
        "rollback": "rollbacks",
        "revision": "build_story",
        "failure": "build_story",
    }.get(stage, "")
