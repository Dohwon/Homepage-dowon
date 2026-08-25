"""Read curated project memory without manufacturing absent files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

import yaml

from .fs_safety import direct_regular_files, read_confined_text, require_confined_directory
from .models import ProjectMemory, ProjectRef, validate_schema
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
    require_confined_directory(root, root, gate)
    profile = _load_profile(root / "project_memory" / "project-profile.yaml", root, gate)
    sections: dict[str, list[str]] = defaultdict(list)
    for directory in (root / "project_memory", root / "manager_memory"):
        for path in _markdown_files(directory, root, gate):
            for section, items in _parse_memory_sections(path, root, gate).items():
                sections[section].extend(items)

    return ProjectMemory(
        profile=profile,
        build_story=tuple(sections["build_story"]),
        decisions=tuple(sections["decisions"]),
        rollbacks=tuple(sections["rollbacks"]),
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
) -> dict[str, tuple[str, ...]]:
    sections: dict[str, list[str]] = defaultdict(list)
    active_section: str | None = None
    fence: str | None = None
    for line in read_confined_text(path, root, gate).splitlines():
        if fence is not None:
            if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
                fence = None
            continue

        fence_open = _FENCE_OPEN.match(line)
        if fence_open:
            fence = fence_open.group(1)
            continue
        heading = _HEADING.match(line)
        if heading:
            active_section = _section_name(heading) if len(heading.group(1)) == 2 else None
            continue
        item = _LIST_ITEM.match(line)
        if active_section is not None and item:
            sections[active_section].append(item.group(1))
    return {name: tuple(items) for name, items in sections.items()}


def _section_name(heading: re.Match[str]) -> str | None:
    return _SECTION_NAMES.get(heading.group(2).strip().casefold())
