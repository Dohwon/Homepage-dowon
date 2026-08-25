"""Idempotently maintain evidence-backed local project-memory Markdown."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from .models import EvidenceClaim, MemoryUpdate, ProjectKnowledge, ProjectRef


_MINIMUM_CONFIDENCE = 0.85
_TARGETS = {
    "decision": ("decisions.md", "Decisions", "Decision"),
    "rollback": ("rollbacks.md", "Rollbacks", "Rollback"),
    "revision": ("build-story.md", "Build Story", "Revision"),
    "failure": ("build-story.md", "Build Story", "Resolved Failure"),
}
_EVENT_ID = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_START_MARKER = re.compile(rf"<!-- atlas:event:({_EVENT_ID}) -->$")
_END_MARKER = re.compile(rf"<!-- /atlas:event:({_EVENT_ID}) -->$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,}).*$")


@dataclass(frozen=True)
class _ManagedBlock:
    event_id: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class _SectionBounds:
    end_line: int


@dataclass(frozen=True)
class _MemoryEvent:
    event_id: str
    date: str
    title: str
    context: str
    decision: str
    outcome: str
    filename: str
    section: str


def update_project_memory(
    ref: ProjectRef, knowledge: ProjectKnowledge, dry_run: bool = False
) -> MemoryUpdate:
    """Write only selected, high-confidence history while preserving user text."""
    grouped: dict[str, list[_MemoryEvent]] = defaultdict(list)
    for event in _selected_events(knowledge):
        grouped[event.filename].append(event)

    planned: list[tuple[Path, str]] = []
    for filename in sorted(grouped):
        path = ref.root / "project_memory" / filename
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        content = _updated_content(existing, grouped[filename])
        if content != existing:
            planned.append((path, content))

    if not dry_run:
        for path, content in planned:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    return MemoryUpdate(
        changed_files=tuple(
            path.relative_to(ref.root).as_posix() for path, _ in planned
        )
    )


def _selected_events(knowledge: ProjectKnowledge) -> tuple[_MemoryEvent, ...]:
    selected: list[_MemoryEvent] = []
    for claim in knowledge.winners.values():
        target = _TARGETS.get(claim.claim_type)
        if target is None or (claim.confidence < _MINIMUM_CONFIDENCE and not claim.selected):
            continue
        selected.append(_event_from_claim(claim, *target))

    deduplicated: dict[str, _MemoryEvent] = {}
    for event in sorted(selected, key=_event_sort_key):
        deduplicated.setdefault(event.event_id, event)
    return tuple(sorted(deduplicated.values(), key=_event_sort_key))


def _event_from_claim(
    claim: EvidenceClaim, filename: str, section: str, title: str
) -> _MemoryEvent:
    if not re.fullmatch(_EVENT_ID, claim.evidence_id):
        raise ValueError("selected history has an invalid event_id")
    if not isinstance(claim.value, str) or not _one_line(claim.value):
        raise ValueError("selected history requires non-empty text evidence")
    date = _one_line(claim.event_date)
    if not date:
        raise ValueError("selected history requires an event date")
    return _MemoryEvent(
        event_id=claim.evidence_id,
        date=date,
        title=title,
        context=f"{claim.source_class} evidence",
        decision=_one_line(claim.value),
        outcome=f"Confidence: {claim.confidence:.2f}",
        filename=filename,
        section=section,
    )


def _updated_content(existing: str, events: list[_MemoryEvent]) -> str:
    blocks = _parse_managed_blocks(existing)
    by_id = {block.event_id: block for block in blocks}
    replacements = {event.event_id: managed_event_block(event) for event in events if event.event_id in by_id}
    updated = _replace_blocks(existing, blocks, replacements)
    section_bounds = _target_section_bounds(updated, events[0].section)

    additions = [event for event in sorted(events, key=_event_sort_key) if event.event_id not in by_id]
    if not additions:
        return updated

    section = events[0].section
    if not updated:
        return f"## {section}\n\n" + "\n".join(managed_event_block(event) for event in additions)
    rendered = "\n".join(managed_event_block(event) for event in additions)
    if section_bounds is None:
        return updated + _separator(updated) + f"## {section}\n\n" + rendered
    return _insert_before_section_end(updated, section_bounds.end_line, rendered)


def managed_event_block(event: _MemoryEvent) -> str:
    """Render the exact local Atlas control metadata block."""
    return (
        f"<!-- atlas:event:{event.event_id} -->\n"
        f"### {event.date} · {event.title}\n\n"
        f"- 상황: {event.context}\n"
        f"- 선택: {event.decision}\n"
        f"- 결과: {event.outcome}\n"
        f"<!-- /atlas:event:{event.event_id} -->\n"
    )


def _parse_managed_blocks(content: str) -> tuple[_ManagedBlock, ...]:
    blocks: list[_ManagedBlock] = []
    open_event: tuple[str, int] | None = None
    seen_ids: set[str] = set()
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        marker = line.rstrip("\r\n")
        if "atlas:event:" not in marker:
            continue
        start = _START_MARKER.fullmatch(marker)
        end = _END_MARKER.fullmatch(marker)
        if start is None and end is None:
            raise ValueError("malformed managed markers")
        if start is not None:
            if open_event is not None or start.group(1) in seen_ids:
                raise ValueError("malformed managed markers")
            open_event = (start.group(1), index)
            seen_ids.add(start.group(1))
            continue
        if open_event is None or end is None or end.group(1) != open_event[0]:
            raise ValueError("malformed managed markers")
        blocks.append(_ManagedBlock(open_event[0], open_event[1], index))
        open_event = None
    if open_event is not None:
        raise ValueError("malformed managed markers")
    return tuple(blocks)


def _replace_blocks(
    content: str, blocks: tuple[_ManagedBlock, ...], replacements: dict[str, str]
) -> str:
    if not replacements:
        return content
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    cursor = 0
    for block in blocks:
        output.extend(lines[cursor:block.start_line])
        output.append(replacements.get(block.event_id, "".join(lines[block.start_line : block.end_line + 1])))
        cursor = block.end_line + 1
    output.extend(lines[cursor:])
    return "".join(output)


def _target_section_bounds(content: str, section: str) -> _SectionBounds | None:
    headings = _markdown_headings(content)
    targets = [index for index, level, title in headings if level == 2 and title.casefold() == section.casefold()]
    if len(targets) > 1:
        raise ValueError("duplicate target headings")
    if not targets:
        return None
    target = targets[0]
    end_line = len(content.splitlines(keepends=True))
    for index, level, _ in headings:
        if index > target and level <= 2:
            end_line = index
            break
    return _SectionBounds(end_line=end_line)


def _markdown_headings(content: str) -> tuple[tuple[int, int, str], ...]:
    headings: list[tuple[int, int, str]] = []
    fence: str | None = None
    for index, line in enumerate(content.splitlines(keepends=True)):
        raw = line.rstrip("\r\n")
        if fence is not None:
            if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", raw):
                fence = None
            continue
        opened = _FENCE_OPEN.match(raw)
        if opened:
            fence = opened.group(1)
            continue
        heading = _HEADING.match(raw)
        if heading:
            headings.append((index, len(heading.group(1)), heading.group(2).strip()))
    if fence is not None:
        raise ValueError("unsafe Markdown structure")
    return tuple(headings)


def _insert_before_section_end(content: str, end_line: int, addition: str) -> str:
    lines = content.splitlines(keepends=True)
    before = "".join(lines[:end_line])
    after = "".join(lines[end_line:])
    after_separator = "" if not after or after.startswith(("\n", "\r")) else "\n"
    return before + _separator(before) + addition + after_separator + after


def _separator(content: str) -> str:
    if content.endswith(("\n\n", "\r\n\r\n")):
        return ""
    if content.endswith(("\n", "\r")):
        return "\n"
    return "\n\n"


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _event_sort_key(event: _MemoryEvent) -> tuple[str, str, str, str]:
    return (event.date, event.event_id, event.filename, event.decision)
