"""Idempotently maintain evidence-backed local project-memory Markdown."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

from .fs_safety import (
    FileWrite,
    commit_file_transaction,
    direct_regular_files,
    read_confined_text,
    require_confined_directory,
    require_write_destination,
)
from .history import EVENT_ID_PATTERN, parse_managed_events, render_managed_event
from .models import EvidenceClaim, MemoryUpdate, ProjectEvent, ProjectKnowledge, ProjectRef
from .visuals import has_problem_solving_evidence, render_problem_solving_svg


_MINIMUM_CONFIDENCE = 0.85
_TARGETS = {
    "decision": ("decisions.md", "Decisions", "Decision"),
    "rollback": ("rollbacks.md", "Rollbacks", "Rollback"),
    "revision": ("build-story.md", "Build Story", "Revision"),
    "failure": ("build-story.md", "Build Story", "Resolved Failure"),
}
_EVENT_ID = EVENT_ID_PATTERN
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


def update_project_memory(
    ref: ProjectRef, knowledge: ProjectKnowledge, dry_run: bool = False
) -> MemoryUpdate:
    """Write only selected, high-confidence history while preserving user text."""
    planned = plan_project_memory_writes(ref, knowledge)
    if not dry_run:
        commit_file_transaction(planned)
    return MemoryUpdate(
        changed_files=tuple(
            write.path.relative_to(ref.root).as_posix() for write in planned
        )
    )


def plan_project_memory_writes(
    ref: ProjectRef, knowledge: ProjectKnowledge
) -> tuple[FileWrite, ...]:
    """Prepare every changed memory payload without mutating the project tree."""
    require_confined_directory(ref.root, ref.root)
    grouped: dict[str, list[ProjectEvent]] = defaultdict(list)
    for event in _selected_events(knowledge):
        grouped[_TARGETS[event.stage][0]].append(event)

    filenames = tuple(sorted({target[0] for target in _TARGETS.values()}))
    destinations = {
        filename: require_write_destination(
            ref.root / "project_memory" / filename,
            ref.root,
        )
        for filename in filenames
    }
    contents: dict[str, str] = {}
    for filename, path in destinations.items():
        try:
            contents[filename] = read_confined_text(path, ref.root)
        except FileNotFoundError:
            contents[filename] = ""

    planned: list[FileWrite] = []
    for filename in sorted(grouped):
        path = destinations[filename]
        existing = contents[filename]
        content = _updated_content(existing, grouped[filename])
        contents[filename] = content
        if content != existing:
            planned.append(FileWrite(path=path, content=content.encode("utf-8"), root=ref.root))

    managed_sources = [contents[filename] for filename in filenames]
    target_paths = set(destinations.values())
    for directory in (ref.root / "project_memory", ref.root / "manager_memory"):
        for path in direct_regular_files(directory, ref.root, suffix=".md"):
            if path not in target_paths:
                managed_sources.append(read_confined_text(path, ref.root))
    events_by_id: dict[str, ProjectEvent] = {}
    for content in managed_sources:
        for block in parse_managed_events(content):
            if block.event.event_id in events_by_id:
                raise ValueError("duplicate managed event id")
            events_by_id[block.event.event_id] = block.event
    events = tuple(sorted(events_by_id.values(), key=_event_sort_key))
    if has_problem_solving_evidence(events):
        visual_path = require_write_destination(
            ref.root / "project_memory" / "visuals" / "problem-solving.svg",
            ref.root,
        )
        rendered = render_problem_solving_svg(ref, events)
        try:
            current_visual = read_confined_text(visual_path, ref.root)
        except FileNotFoundError:
            current_visual = ""
        if rendered != current_visual:
            planned.append(
                FileWrite(
                    path=visual_path,
                    content=rendered.encode("utf-8"),
                    root=ref.root,
                )
            )
    return tuple(planned)


def _selected_events(knowledge: ProjectKnowledge) -> tuple[ProjectEvent, ...]:
    selected: list[ProjectEvent] = []
    for claim in knowledge.winners.values():
        target = _TARGETS.get(claim.claim_type)
        if target is None or (claim.confidence < _MINIMUM_CONFIDENCE and not claim.selected):
            continue
        selected.append(_event_from_claim(claim, target[2]))

    deduplicated: dict[str, ProjectEvent] = {}
    for event in sorted(selected, key=_event_sort_key):
        deduplicated.setdefault(event.event_id, event)
    return tuple(sorted(deduplicated.values(), key=_event_sort_key))


def _event_from_claim(
    claim: EvidenceClaim, title: str
) -> ProjectEvent:
    if not re.fullmatch(_EVENT_ID, claim.evidence_id):
        raise ValueError("selected history has an invalid event_id")
    if not isinstance(claim.value, str) or not _one_line(claim.value):
        raise ValueError("selected history requires non-empty text evidence")
    raw_date = _one_line(claim.event_date)
    if len(raw_date) < 10:
        raise ValueError("selected history requires an event date")
    event_date = raw_date[:10]
    try:
        date.fromisoformat(event_date)
    except ValueError:
        raise ValueError("selected history requires an event date") from None
    return ProjectEvent(
        event_id=claim.evidence_id,
        date=event_date,
        title=title,
        context=f"{claim.source_class} evidence",
        decision=_one_line(claim.value),
        outcome=f"Confidence: {claim.confidence:.2f}",
        stage=claim.claim_type,
    )


def _updated_content(existing: str, events: list[ProjectEvent]) -> str:
    blocks = _parse_managed_blocks(existing)
    by_id = {block.event_id: block for block in blocks}
    section = _TARGETS[events[0].stage][1]
    original_section = _target_section_bounds(existing, section)
    relocate_existing = original_section is None and any(
        event.event_id in by_id for event in events
    )
    replacements = {
        event.event_id: "" if relocate_existing else managed_event_block(event)
        for event in events
        if event.event_id in by_id
    }
    updated = _replace_blocks(existing, blocks, replacements)
    section_bounds = _target_section_bounds(updated, section)

    additions = [
        event
        for event in sorted(events, key=_event_sort_key)
        if relocate_existing or event.event_id not in by_id
    ]
    if not additions:
        return updated

    if not updated:
        return f"## {section}\n\n" + "\n".join(managed_event_block(event) for event in additions)
    rendered = "\n".join(managed_event_block(event) for event in additions)
    if section_bounds is None:
        return updated + _separator(updated) + f"## {section}\n\n" + rendered
    return _insert_before_section_end(updated, section_bounds.end_line, rendered)


def managed_event_block(event: ProjectEvent) -> str:
    """Render the exact local Atlas control metadata block."""
    return render_managed_event(event)


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


def _event_sort_key(event: ProjectEvent) -> tuple[str, str, str, str]:
    return (
        event.date,
        event.event_id,
        _TARGETS[event.stage][0],
        event.decision,
    )
