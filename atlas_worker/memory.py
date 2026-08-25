"""Read curated project memory without manufacturing absent files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

import yaml

from .models import ProjectMemory, ProjectRef, validate_schema


_SECTION_NAMES = {
    "build story": "build_story",
    "build-story": "build_story",
    "build_story": "build_story",
    "decisions": "decisions",
    "rollbacks": "rollbacks",
}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")


def load_project_memory(ref: ProjectRef) -> ProjectMemory:
    """Load a validated profile plus list-based curated and legacy history."""
    root = ref.root
    profile = _load_profile(root / "project_memory" / "project-profile.yaml")
    sections: dict[str, list[str]] = defaultdict(list)
    for directory in (root / "project_memory", root / "manager_memory"):
        for path in _markdown_files(directory):
            for section, items in _parse_memory_sections(path).items():
                sections[section].extend(items)

    return ProjectMemory(
        profile=profile,
        build_story=tuple(sections["build_story"]),
        decisions=tuple(sections["decisions"]),
        rollbacks=tuple(sections["rollbacks"]),
    )


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Project profile is required at {path}: $")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Project profile must be a mapping at {path}: $")
    validate_schema(data, "project-profile")
    return data


def _markdown_files(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    return tuple(sorted(directory.rglob("*.md"), key=lambda path: path.as_posix()))


def _parse_memory_sections(path: Path) -> dict[str, tuple[str, ...]]:
    sections: dict[str, list[str]] = defaultdict(list)
    active_section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
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
