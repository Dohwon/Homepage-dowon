"""Render deterministic, accessible local problem-solving SVG maps."""

from __future__ import annotations

import html
import math
import re
import xml.etree.ElementTree as ET

from .models import ProjectEvent, ProjectRef


_STAGES = ("constraint", "attempt", "revision", "decision", "result")
_STAGE_LABELS = {
    "constraint": "Constraint",
    "attempt": "Attempt",
    "revision": "Revision",
    "decision": "Decision",
    "result": "Result",
}
_LOCAL_OR_URL = re.compile(
    r"https?://[^\s<>\"']+|[A-Za-z]:[\\/][^\s<>\"']*|\\\\[^\s<>\"']+|/[^\s<>\"']*",
    re.I,
)
_ACTIVE_ATTRIBUTE = re.compile(r"\b(?:href|src|on[a-z]+)\s*=", re.I)
_CANVAS_WIDTH = 1200
_NODE_WIDTH = 208
_NODE_GAP = 24
_SVG_DECLARATION = re.compile(r"<!\s*(?:doctype|entity)\b", re.I)
_SVG_FRAGMENT = re.compile(r"^#[A-Za-z_][A-Za-z0-9_.:-]*$")
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_PROCESSING_INSTRUCTION = re.compile(r"<\?(.*?)\?>", re.S)


def validate_curated_svg(svg: str, *, label: str) -> None:
    """Validate a local curated SVG without allowing executable or external content."""
    if not isinstance(svg, str) or _SVG_DECLARATION.search(svg):
        raise ValueError(f"{label}: declarations and entities are not allowed")
    for match in _PROCESSING_INSTRUCTION.finditer(svg):
        instruction = match.group(1)
        if match.start() != 0 or not instruction.startswith("xml "):
            raise ValueError(f"{label}: processing instructions are not allowed")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise ValueError(f"{label}: malformed XML") from error
    if root.tag != f"{{{_SVG_NAMESPACE}}}svg":
        raise ValueError(f"{label}: root must be svg")
    _validate_view_box(root.attrib.get("viewBox"), label)
    if not _has_exact_direct_metadata(root, "title") or not _has_exact_direct_metadata(root, "desc"):
        raise ValueError(f"{label}: title and desc are required")
    for element in root.iter():
        name = _svg_name(element.tag)
        if name.casefold() in {"script", "foreignobject"}:
            raise ValueError(f"{label}: active SVG element")
        if name.casefold() == "style":
            raise ValueError(f"{label}: CSS is not allowed")
        for attribute, value in element.attrib.items():
            attribute_name = _svg_name(attribute).casefold()
            if attribute_name == "style":
                raise ValueError(f"{label}: CSS is not allowed")
            if attribute_name.startswith("on"):
                raise ValueError(f"{label}: event handlers are not allowed")
            if attribute_name in {"href", "src"} and not _is_local_fragment(value):
                raise ValueError(f"{label}: external or file reference is not allowed")


def _svg_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _has_exact_direct_metadata(root: ET.Element, name: str) -> bool:
    values = [
        element
        for element in root
        if element.tag == f"{{{_SVG_NAMESPACE}}}{name}"
    ]
    return len(values) == 1 and bool("".join(values[0].itertext()).strip())


def _validate_view_box(value: str | None, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label}: viewBox is required")
    parts = tuple(part for part in re.split(r"[\s,]+", value.strip()) if part)
    if len(parts) != 4:
        raise ValueError(f"{label}: viewBox must contain four finite numbers")
    try:
        numbers = tuple(float(part) for part in parts)
    except ValueError:
        raise ValueError(f"{label}: viewBox must contain four finite numbers") from None
    if not all(math.isfinite(number) for number in numbers) or numbers[2] <= 0 or numbers[3] <= 0:
        raise ValueError(f"{label}: viewBox dimensions must be positive finite numbers")


def _is_local_fragment(value: str) -> bool:
    fragment = value.strip()
    return bool(_SVG_FRAGMENT.fullmatch(fragment))




def has_problem_solving_evidence(events: tuple[ProjectEvent, ...]) -> bool:
    """Require a recorded decision plus at least one reviewed path transition."""
    stages = {event.stage.casefold() for event in events}
    return "decision" in stages and bool(stages & {"rollback", "revision", "failure"})


def render_problem_solving_svg(project: ProjectRef, events: tuple[ProjectEvent, ...]) -> str:
    """Render selected events into a fixed, non-executable SVG flow."""
    event_by_stage = _events_by_stage(events)
    stages = tuple(stage for stage in _STAGES if stage in event_by_stage)
    positions = _node_positions(len(stages))
    title = _escape(f"{project.display_name} problem-solving map")
    desc = _escape(" to ".join(_STAGE_LABELS[stage] for stage in stages) + ".")
    nodes = "\n".join(
        _node(stage, _STAGE_LABELS[stage], event_by_stage[stage], x)
        for stage, x in zip(stages, positions)
    )
    arrows = "\n".join(
        f'<path class="arrow" d="M {x + _NODE_WIDTH} 320 H {next_x - 12}" marker-end="url(#arrowhead)" />'
        for x, next_x in zip(positions, positions[1:])
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 640" '
        'role="img" aria-labelledby="title desc">\n'
        '<title id="title">' + title + '</title>\n'
        '<desc id="desc">' + desc + '</desc>\n'
        '<style>\n'
        ':root { --atlas-bg: #f6f8fb; --atlas-node: #ffffff; --atlas-ink: #172033; --atlas-line: #52657f; --atlas-accent: #0b7285; --atlas-muted: #52657f; }\n'
        '@media (prefers-color-scheme: dark) { :root { --atlas-bg: #121820; --atlas-node: #1d2632; --atlas-ink: #f4f7fb; --atlas-line: #9ab1c8; --atlas-accent: #5fd0d8; --atlas-muted: #c2d0df; } }\n'
        'svg { background: var(--atlas-bg); font-family: Arial, sans-serif; }\n'
        '.node { fill: var(--atlas-node); stroke: var(--atlas-line); stroke-width: 2; }\n'
        '.stage { fill: var(--atlas-accent); font-size: 18px; font-weight: bold; }\n'
        '.body { fill: var(--atlas-ink); font-size: 13px; }\n'
        '.muted { fill: var(--atlas-muted); font-size: 12px; }\n'
        '.arrow { fill: none; stroke: var(--atlas-line); stroke-width: 2; }\n'
        '</style>\n'
        '<defs><marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="var(--atlas-line)" /></marker></defs>\n'
        + arrows
        + '\n'
        + nodes
        + '\n</svg>\n'
    )


def _events_by_stage(events: tuple[ProjectEvent, ...]) -> dict[str, ProjectEvent]:
    selected: dict[str, ProjectEvent] = {}
    stage_aliases = {"rollback": "revision", "failure": "result"}
    for event in sorted(events, key=lambda item: (item.stage.casefold(), item.date, item.event_id, item.title)):
        stage = stage_aliases.get(event.stage.casefold(), event.stage.casefold())
        if stage in _STAGE_LABELS:
            selected.setdefault(stage, event)
    return selected


def _node_positions(count: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    content_width = count * _NODE_WIDTH + max(0, count - 1) * _NODE_GAP
    start = (_CANVAS_WIDTH - content_width) // 2
    return tuple(start + index * (_NODE_WIDTH + _NODE_GAP) for index in range(count))


def _node(stage: str, label: str, event: ProjectEvent, x: int) -> str:
    fields = (
        ("Title", event.title),
        ("Context", event.context),
        ("Decision", event.decision),
        ("Result", event.outcome),
    )
    text = [f'<text class="stage" x="{x + 14}" y="180">{_escape(label)}</text>']
    for index, (field, value) in enumerate(fields):
        y = 216 + index * 72
        text.extend(_text_lines(x + 14, y, field, value))
    return (
        f'<g id="node-{stage}">\n'
        f'<rect class="node" x="{x}" y="142" width="208" height="356" rx="6" />\n'
        + "\n".join(text)
        + "\n</g>"
    )


def _text_lines(x: int, y: int, field: str, value: str) -> tuple[str, ...]:
    lines = _wrap(_safe_text(value), max_chars=26, max_lines=2)
    if not lines:
        return ()
    rendered = []
    for index, line in enumerate(lines):
        prefix = f"{field}: " if index == 0 else ""
        rendered.append(
            f'<text class="{"body" if field == "Title" else "muted"}" x="{x}" y="{y + index * 17}">{_escape(prefix + line)}</text>'
        )
    return tuple(rendered)


def _wrap(value: str, max_chars: int, max_lines: int) -> tuple[str, ...]:
    words = value.split()
    if not words:
        return ()
    lines: list[str] = []
    current = ""
    for word in words:
        word = _truncate_word(word, max_chars)
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines:
            return tuple(_truncate_lines(lines, max_chars))
    if current:
        lines.append(current)
    return tuple(_truncate_lines(lines[:max_lines], max_chars))


def _truncate_lines(lines: list[str], max_chars: int) -> list[str]:
    if len(lines) <= 1:
        return lines
    if len(lines[-1]) == max_chars:
        lines[-1] = lines[-1][:-3] + "..."
    return lines


def _truncate_word(word: str, max_chars: int) -> str:
    return word if len(word) <= max_chars else word[: max_chars - 3] + "..."


def _safe_text(value: str) -> str:
    text = _LOCAL_OR_URL.sub(_redact_local_path, str(value))
    return _ACTIVE_ATTRIBUTE.sub("attribute ", text)


def _redact_local_path(match: re.Match[str]) -> str:
    value = match.group(0)
    return value if value.casefold().startswith(("http://", "https://")) else "[local path]"


def _escape(value: str) -> str:
    return html.escape(_safe_text(value), quote=True)
