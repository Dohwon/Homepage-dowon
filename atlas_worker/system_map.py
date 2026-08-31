"""Load and project evidence-backed Project Atlas system maps."""

from __future__ import annotations

from collections import defaultdict
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


_KIND_COLUMN = {
    "actor": 0,
    "input": 0,
    "interface": 1,
    "process": 1,
    "state": 2,
    "service": 2,
    "output": 3,
    "guardrail": 3,
}
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
    """Render a stable four-column map without embedding private provenance."""
    columns: dict[int, list[SystemMapNode]] = defaultdict(list)
    for node in system_map.nodes:
        columns[_KIND_COLUMN[node.kind]].append(node)
    for values in columns.values():
        values.sort(key=lambda node: (node.kind, node.label, node.node_id))

    width = 1280
    row_gap = 122
    max_rows = max((len(values) for values in columns.values()), default=1)
    height = max(420, 170 + max_rows * row_gap)
    node_width = 228
    node_height = 74
    column_x = {0: 42, 1: 365, 2: 688, 3: 1010}
    positions: dict[str, tuple[float, float]] = {}
    node_markup = []
    for column in range(4):
        values = columns.get(column, [])
        content_height = max(0, (len(values) - 1) * row_gap)
        start_y = 118 + max(0, (max_rows - len(values)) * row_gap / 2)
        for index, node in enumerate(values):
            x = column_x[column]
            y = start_y + index * row_gap
            positions[node.node_id] = (x, y)
            node_markup.append(
                f'<g data-node="{escape(node.node_id)}">'
                f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="6" '
                f'fill="{_KIND_FILL[node.kind]}" stroke="#52606d" stroke-width="1.5"/>'
                f'<text x="{x + 14}" y="{y + 29}" fill="#17212b" font-size="16" font-weight="700">'
                f'{escape(node.label)}</text>'
                f'<text x="{x + 14}" y="{y + 53}" fill="#52606d" font-size="11">'
                f'{escape(node.kind)}</text></g>'
            )

    edge_markup = []
    for flow in sorted(system_map.flows, key=lambda item: item.flow_id):
        source_x, source_y = positions[flow.source_id]
        target_x, target_y = positions[flow.target_id]
        sx = source_x + node_width
        sy = source_y + node_height / 2
        tx = target_x
        ty = target_y + node_height / 2
        if target_x <= source_x:
            sx = source_x + node_width / 2
            sy = source_y + node_height
            tx = target_x + node_width / 2
            ty = target_y
        mx = (sx + tx) / 2
        my = (sy + ty) / 2
        edge_markup.append(
            f'<g data-flow="{escape(flow.flow_id)}">'
            f'<path d="M {sx:g} {sy:g} C {mx:g} {sy:g}, {mx:g} {ty:g}, {tx:g} {ty:g}" '
            'fill="none" stroke="#7b8794" stroke-width="2"/>'
            f'<circle cx="{tx:g}" cy="{ty:g}" r="4" fill="#52606d"/>'
            f'<text x="{mx:g}" y="{my - 8:g}" text-anchor="middle" fill="#52606d" font-size="11">'
            f'{escape(flow.label)}</text></g>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="system-map-title system-map-desc">'
        f'<title id="system-map-title">{escape(system_map.title)}</title>'
        f'<desc id="system-map-desc">{escape(system_map.summary)}</desc>'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<text x="42" y="54" fill="#17212b" font-size="24" font-weight="700">{escape(system_map.title)}</text>'
        f'<text x="42" y="82" fill="#52606d" font-size="13">{escape(system_map.summary)}</text>'
        + "".join(edge_markup)
        + "".join(node_markup)
        + "</svg>"
    )
    validate_curated_svg(svg, label="system-map-svg")
    return svg


def _require_unique(values: object, label: str) -> None:
    seen: set[str] = set()
    for value in values:  # type: ignore[union-attr]
        if value in seen:
            raise ValueError(f"duplicate {label} id")
        seen.add(value)
