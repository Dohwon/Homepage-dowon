"""Load and project evidence-backed Project Atlas system maps."""

from __future__ import annotations

from html import escape
from pathlib import Path

from .article import _curated_source_root, _load_yaml_mapping, _validated_references
from .models import (
    EvidenceRecord,
    ProjectArticle,
    ProjectRef,
    ProjectSystemMap,
    SystemMapDecisionLink,
    SystemMapFlow,
    SystemMapNode,
    validate_schema,
)
from .privacy import PrivacyGate
from .visuals import validate_curated_svg


_KIND_FILL = {
    "actor": "#e9f2fb",
    "input": "#edf6f3",
    "interface": "#f4effa",
    "process": "#fff4d8",
    "state": "#eaf4ea",
    "service": "#fceceb",
    "output": "#eaf0fa",
    "guardrail": "#f1f1f1",
}


def load_project_system_map(
    ref: ProjectRef,
    article: ProjectArticle,
    evidence: tuple[EvidenceRecord, ...],
    gate: PrivacyGate | None = None,
) -> ProjectSystemMap | None:
    """Load one confined map and validate every cross-document reference."""
    root, source = _curated_source_root(ref, gate)
    try:
        data = _load_yaml_mapping(source / "system-map.yaml", root, gate, "system map")
    except FileNotFoundError:
        return None
    validate_schema(data, "project-system-map")
    if data["project_id"] != ref.project_id or article.project_id != ref.project_id:
        raise ValueError("system map project_id does not match project ref")

    node_values = data["nodes"]
    _require_unique((value["id"] for value in node_values), "system map node")
    nodes = tuple(
        SystemMapNode(value["id"], value["label"], value["kind"], value["description"])
        for value in node_values
    )
    node_ids = {node.node_id for node in nodes}

    flow_values = data["flows"]
    _require_unique((value["id"] for value in flow_values), "system map flow")
    flows = []
    for value in flow_values:
        if value["from"] not in node_ids or value["to"] not in node_ids:
            raise ValueError("system map flow references an unknown node")
        flows.append(SystemMapFlow(value["id"], value["from"], value["to"], value["label"]))

    section_ids = {section.section_id for section in article.sections}
    links = []
    for value in data["decision_links"]:
        if value["section_id"] not in section_ids:
            raise ValueError("system map decision references an unknown article section")
        if not set(value["node_ids"]).issubset(node_ids):
            raise ValueError("system map decision references an unknown node")
        links.append(
            SystemMapDecisionLink(tuple(value["node_ids"]), value["section_id"], value["label"])
        )

    evidence_ids = _validated_references(
        data["evidence_ids"], {record.evidence_id for record in evidence}, "system map evidence"
    )
    return ProjectSystemMap(
        project_id=data["project_id"],
        title=data["title"],
        summary=data["summary"],
        nodes=nodes,
        flows=tuple(flows),
        decision_links=tuple(links),
        evidence_ids=evidence_ids,
    )


def render_system_map_svg(system_map: ProjectSystemMap) -> str:
    """Render a stable narrative flow without embedding private provenance."""
    width = 1120
    node_x = 80
    node_width = 960
    node_height = 94
    row_step = 158
    title_lines = _wrap_svg_text(system_map.title, 38)
    summary_lines = _wrap_svg_text(system_map.summary, 42)
    header_height = 34 * len(title_lines) + 22 * len(summary_lines)
    start_y = 54 + header_height + 34
    height = max(420, start_y + len(system_map.nodes) * row_step + 24)
    positions: dict[str, float] = {}
    node_markup = []
    for index, node in enumerate(system_map.nodes, 1):
        y = start_y + (index - 1) * row_step
        positions[node.node_id] = y
        description = _truncate_svg_text(node.description, 68)
        node_markup.append(
            f'<g data-node="{escape(node.node_id)}">'
            f'<rect x="{node_x}" y="{y}" width="{node_width}" height="{node_height}" rx="6" '
            f'fill="{_KIND_FILL[node.kind]}" stroke="#52606d" stroke-width="1.5"/>'
            f'<circle cx="{node_x + 36}" cy="{y + 34}" r="18" fill="#17212b"/>'
            f'<text x="{node_x + 36}" y="{y + 39}" text-anchor="middle" fill="#ffffff" '
            f'font-size="13" font-weight="700">{index}</text>'
            f'<text x="{node_x + 70}" y="{y + 31}" fill="#17212b" font-size="17" font-weight="700">'
            f'{escape(node.label)}</text>'
            f'<text x="{node_x + node_width - 18}" y="{y + 31}" text-anchor="end" '
            f'fill="#52606d" font-size="11">{escape(node.kind)}</text>'
            f'<text x="{node_x + 70}" y="{y + 62}" fill="#52606d" font-size="12">'
            f'{escape(description)}</text></g>'
        )

    edge_markup = []
    for flow in sorted(system_map.flows, key=lambda item: item.flow_id):
        source_y = positions[flow.source_id] + node_height
        target_y = positions[flow.target_id]
        center_x = node_x + node_width / 2
        middle_y = (source_y + target_y) / 2
        label = _truncate_svg_text(flow.label, 46)
        label_width = min(420, max(72, len(label) * 12 + 24))
        edge_markup.append(
            f'<g data-flow="{escape(flow.flow_id)}">'
            f'<path d="M {center_x:g} {source_y:g} L {center_x:g} {target_y - 8:g}" '
            'fill="none" stroke="#7b8794" stroke-width="2" '
            'marker-end="url(#system-map-arrow)"/>'
            f'<rect x="{center_x - label_width / 2:g}" y="{middle_y - 14:g}" '
            f'width="{label_width:g}" height="24" rx="4" fill="#ffffff" stroke="#d6dce2"/>'
            f'<text x="{center_x:g}" y="{middle_y + 3:g}" text-anchor="middle" '
            f'fill="#52606d" font-size="11">{escape(label)}</text></g>'
        )

    title_markup = _svg_tspans(title_lines, x=80, y=52, line_height=34)
    summary_y = 52 + 34 * len(title_lines)
    summary_markup = _svg_tspans(summary_lines, x=80, y=summary_y, line_height=22)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="system-map-title system-map-desc">'
        f'<title id="system-map-title">{escape(system_map.title)}</title>'
        f'<desc id="system-map-desc">{escape(system_map.summary)}</desc>'
        '<defs><marker id="system-map-arrow" viewBox="0 0 10 10" refX="5" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#52606d"/></marker></defs>'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<text fill="#17212b" font-size="24" font-weight="700">{title_markup}</text>'
        f'<text fill="#52606d" font-size="13">{summary_markup}</text>'
        + "".join(edge_markup)
        + "".join(node_markup)
        + "</svg>"
    )
    validate_curated_svg(svg, label="system-map-svg")
    return svg


def _wrap_svg_text(value: str, line_limit: int) -> tuple[str, ...]:
    words = value.split()
    if not words:
        return ("",)
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= line_limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def _svg_tspans(lines: tuple[str, ...], *, x: int, y: int, line_height: int) -> str:
    return "".join(
        f'<tspan x="{x}" y="{y + index * line_height}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )


def _truncate_svg_text(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 3].rstrip()}..."


def _require_unique(values: object, label: str) -> None:
    seen: set[str] = set()
    for value in values:  # type: ignore[union-attr]
        if value in seen:
            raise ValueError(f"duplicate {label} id")
        seen.add(value)
