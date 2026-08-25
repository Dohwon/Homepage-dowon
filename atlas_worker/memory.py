"""Read curated project memory without manufacturing absent files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

import yaml

from .fs_safety import direct_regular_files, read_confined_text, require_confined_directory
from .history import parse_managed_events
from .models import ProjectEvent, ProjectMemory, ProjectRef, validate_schema
from .privacy import PrivacyGate


_SECTION_NAMES = {
    "build story": "build_story",
    "build-story": "build_story",
    "build_story": "build_story",
    "decisions": "decisions",
    "rollbacks": "rollbacks",
}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,}).*$")


def load_project_memory(ref: ProjectRef, gate: PrivacyGate | None = None) -> ProjectMemory:
    """Load a validated profile plus list-based curated and legacy history."""
    root = ref.root
    if ref.standalone_asset:
        boundary = root.parent
        require_confined_directory(boundary, boundary, gate)
        read_confined_text(root, boundary, gate)
        if ref.profile_path is None:
            raise ValueError("Project profile is required: $")
        profile = _load_profile(ref.profile_path, boundary, gate)
        return ProjectMemory(profile=profile)
    require_confined_directory(root, root, gate)
    profile_path = ref.profile_path or root / "project_memory" / "project-profile.yaml"
    profile = _load_profile(profile_path, root, gate)
    sections: dict[str, list[str]] = defaultdict(list)
    events: list[ProjectEvent] = []
    event_ids: set[str] = set()
    for directory in (root / "project_memory", root / "manager_memory"):
        for path in _markdown_files(directory, root, gate):
            parsed_sections, parsed_events = _parse_memory_sections(path, root, gate)
            for section, items in parsed_sections.items():
                sections[section].extend(items)
            for event in parsed_events:
                if event.event_id in event_ids:
                    raise ValueError("duplicate managed event id")
                event_ids.add(event.event_id)
                events.append(event)

    return ProjectMemory(
        profile=profile,
        build_story=tuple(sections["build_story"]),
        decisions=tuple(sections["decisions"]),
        rollbacks=tuple(sections["rollbacks"]),
        events=tuple(events),
    )


def _load_profile(path: Path, root: Path, gate: PrivacyGate | None) -> dict[str, Any]:
    try:
        content = read_confined_text(path, root, gate)
    except FileNotFoundError:
        raise ValueError("Project profile is required: $") from None
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError(f"Project profile must be a mapping at {path}: $")
    validate_schema(data, "project-profile")
    return data


def _markdown_files(
    directory: Path, root: Path, gate: PrivacyGate | None
) -> tuple[Path, ...]:
    return direct_regular_files(directory, root, gate, suffix=".md")


def _parse_memory_sections(
    path: Path, root: Path, gate: PrivacyGate | None
) -> tuple[dict[str, tuple[str, ...]], tuple[ProjectEvent, ...]]:
    content = read_confined_text(path, root, gate)
    managed = parse_managed_events(content)
    blocks_by_start = {block.start_line: block for block in managed}
    sections: dict[str, list[str]] = defaultdict(list)
    active_section: str | None = None
    fence: str | None = None
    lines = content.splitlines()
    line_number = 0
    while line_number < len(lines):
        block = blocks_by_start.get(line_number)
        if block is not None:
            sections[block.section].append(block.event.decision)
            active_section = None
            line_number = block.end_line + 1
            continue
        line = lines[line_number]
        if fence is not None:
            if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
                fence = None
            line_number += 1
            continue

        fence_open = _FENCE_OPEN.match(line)
        if fence_open:
            fence = fence_open.group(1)
            line_number += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            active_section = _section_name(heading) if len(heading.group(1)) == 2 else None
            line_number += 1
            continue
        item = _LIST_ITEM.match(line)
        if active_section is not None and item:
            sections[active_section].append(item.group(1))
        line_number += 1
    return (
        {name: tuple(items) for name, items in sections.items()},
        tuple(block.event for block in managed),
    )


def _section_name(heading: re.Match[str]) -> str | None:
    return _SECTION_NAMES.get(heading.group(2).strip().casefold())
