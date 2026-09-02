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
        map_type=data["map_type"],
        title=data["title"],
        summary=data["summary"],
        nodes=nodes,
        flows=tuple(flows),
        decision_links=tuple(links),
        evidence_ids=evidence_ids,
    )


def render_system_map_svg(system_map: ProjectSystemMap) -> str:
    """Render a semantic map whose geometry follows the project's map family."""
    width = 1240
    node_width = 250
    node_height = 126
    title_lines = _wrap_svg_text(system_map.title, 38)
    summary_lines = _wrap_svg_text(system_map.summary, 42)
    header_height = 34 * len(title_lines) + 22 * len(summary_lines)
    start_y = 76 + header_height + 54
    family, family_label = _map_family(system_map.map_type)
    positions = _semantic_positions(system_map.nodes, family, start_y, node_width, node_height)
    node_markup = []
    for index, node in enumerate(system_map.nodes, 1):
        x, y = positions[node.node_id]
        description_lines = _wrap_svg_text(node.description, 33)[:3]
        description_markup = _svg_tspans(description_lines, x=x + 18, y=y + 80, line_height=16)
        node_markup.append(
            f'<g data-node="{escape(node.node_id)}">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="8" '
            f'fill="{_KIND_FILL[node.kind]}" stroke="#52606d" stroke-width="1.5"/>'
            f'<circle cx="{x + 26}" cy="{y + 27}" r="14" fill="#17212b"/>'
            f'<text x="{x + 26}" y="{y + 32}" text-anchor="middle" fill="#ffffff" '
            f'font-size="11" font-weight="700">{index}</text>'
            f'<text x="{x + 50}" y="{y + 32}" fill="#17212b" font-size="16" font-weight="700">'
            f'{escape(_truncate_svg_text(node.label, 22))}</text>'
            f'<text x="{x + node_width - 16}" y="{y + 55}" text-anchor="end" '
            f'fill="#52606d" font-size="11">{escape(node.kind)}</text>'
            f'<text x="{x + 18}" y="{y + 78}" fill="#52606d" font-size="12">'
            f'{description_markup}</text></g>'
        )

    edge_markup = []
    for flow in sorted(system_map.flows, key=lambda item: item.flow_id):
        source_x, source_y = positions[flow.source_id]
        target_x, target_y = positions[flow.target_id]
        path, label_x, label_y = _flow_geometry(
            source_x, source_y, target_x, target_y, node_width, node_height, family
        )
        label = _truncate_svg_text(flow.label, 24)
        label_width = min(190, max(72, len(label) * 11 + 24))
        edge_markup.append(
            f'<g data-flow="{escape(flow.flow_id)}">'
            f'<path d="{path}" '
            'fill="none" stroke="#7b8794" stroke-width="2" '
            'marker-end="url(#system-map-arrow)"/>'
            f'<rect x="{label_x - label_width / 2:g}" y="{label_y:g}" '
            f'width="{label_width:g}" height="24" rx="4" fill="#ffffff" stroke="#d6dce2"/>'
            f'<text x="{label_x:g}" y="{label_y + 16:g}" text-anchor="middle" '
            f'fill="#52606d" font-size="11">{escape(label)}</text></g>'
        )

    title_markup = _svg_tspans(title_lines, x=40, y=52, line_height=34)
    summary_y = 52 + 34 * len(title_lines)
    summary_markup = _svg_tspans(summary_lines, x=40, y=summary_y, line_height=22)
    badge_y = summary_y + 22 * len(summary_lines) + 26
    max_y = max((y for _, y in positions.values()), default=start_y)
    height = max(420, max_y + node_height + 54)

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
        f'<rect x="40" y="{badge_y}" width="190" height="22" rx="11" fill="#17212b"/>'
        f'<text x="135" y="{badge_y + 15}" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">{escape(family_label)}</text>'
        + "".join(edge_markup)
        + "".join(node_markup)
        + "</svg>"
    )
    validate_curated_svg(svg, label="system-map-svg")
    return svg


_MAP_FAMILY_TYPES = {
    "version-roadmap": frozenset({
        "hybrid-drive-recording", "navigation-flow", "planned-route-recording", "road-recording"
    }),
    "state-transition": frozenset({
        "approval-workflow", "cross-surface-ledger", "personal-agent-service", "relationship-chat", "state-machine-ui"
    }),
    "evaluation-loop": frozenset({
        "agent-test-lifecycle", "dataset-release-pipeline", "evaluation-pipeline", "learning-loop", "multiturn-evaluation", "testset-generation"
    }),
    "agent-orchestration": frozenset({
        "agent-execution-control", "agent-routing", "language-schema-pipeline", "memory-distribution", "retrieval-routing", "routing-pipeline", "tool-registry"
    }),
    "service-boundary": frozenset({
        "browser-extension-service", "browser-instrument", "documentation-publishing", "local-desktop-app", "local-finance-app", "private-content-service"
    }),
}

_MAP_FAMILY_LABELS = {
    "version-roadmap": "버전 로드맵",
    "state-transition": "상태 전이",
    "evaluation-loop": "평가 루프",
    "agent-orchestration": "에이전트 오케스트레이션",
    "service-boundary": "서비스 경계",
    "data-flow": "데이터 흐름",
}


def _map_family(map_type: str) -> tuple[str, str]:
    for family, map_types in _MAP_FAMILY_TYPES.items():
        if map_type in map_types:
            return family, _MAP_FAMILY_LABELS[family]
    return "data-flow", _MAP_FAMILY_LABELS["data-flow"]


def _semantic_positions(
    nodes: tuple[SystemMapNode, ...], family: str, start_y: float, node_width: float, node_height: float
) -> dict[str, tuple[float, float]]:
    """Place nodes according to the relationship being explained, not a fixed grid."""
    positions: dict[str, tuple[float, float]] = {}
    count = len(nodes)
    if family == "version-roadmap":
        gap = 42
        total = count * node_width + max(0, count - 1) * gap
        x = max(40, (1240 - total) / 2)
        for node in nodes:
            positions[node.node_id] = (x, start_y + 28)
            x += node_width + gap
        return positions
    if family == "state-transition":
        center_x, center_y = 620, start_y + 150
        radius_x, radius_y = 410, max(130, min(250, count * 28))
        import math
        for index, node in enumerate(nodes):
            angle = (-math.pi / 2) + (2 * math.pi * index / max(1, count))
            positions[node.node_id] = (
                center_x + radius_x * math.cos(angle) - node_width / 2,
                center_y + radius_y * math.sin(angle) - node_height / 2,
            )
        return positions
    if family == "agent-orchestration":
        lanes = max(2, min(4, count))
        lane_gap = 42
        lane_width = (1160 - (lanes - 1) * lane_gap) / lanes
        for index, node in enumerate(nodes):
            lane = index % lanes
            row = index // lanes
            positions[node.node_id] = (
                40 + lane * (lane_width + lane_gap) + (lane_width - node_width) / 2,
                start_y + row * (node_height + 94),
            )
        return positions
    if family == "evaluation-loop":
        gap = 54
        total = count * node_width + max(0, count - 1) * gap
        x = max(40, (1240 - total) / 2)
        for index, node in enumerate(nodes):
            y = start_y + (0 if index % 2 == 0 else 118)
            positions[node.node_id] = (x, y)
            x += node_width + gap
        return positions
    if family == "service-boundary":
        columns = 3
        column_gap = 68
        row_gap = 104
        for index, node in enumerate(nodes):
            column = index % columns
            row = index // columns
            positions[node.node_id] = (
                40 + column * (node_width + column_gap),
                start_y + row * (node_height + row_gap),
            )
        return positions
    gap = 84
    for index, node in enumerate(nodes):
        positions[node.node_id] = (620 - node_width / 2, start_y + index * (node_height + gap))
    return positions


def _flow_geometry(
    source_x: float,
    source_y: float,
    target_x: float,
    target_y: float,
    node_width: float,
    node_height: float,
    family: str,
) -> tuple[str, float, float]:
    if family == "version-roadmap" and target_x >= source_x:
        y = source_y + node_height / 2
        return (
            f"M {source_x + node_width:g} {y:g} L {target_x - 8:g} {target_y + node_height / 2:g}",
            (source_x + node_width + target_x) / 2,
            (y + target_y + node_height / 2) / 2 - 16,
        )
    if family == "state-transition":
        start_x = source_x + node_width / 2
        start_y = source_y + node_height / 2
        end_x = target_x + node_width / 2
        end_y = target_y + node_height / 2
        bend = 54 if end_x >= start_x else -54
        return (
            f"M {start_x:g} {start_y:g} C {start_x + bend:g} {start_y:g}, {end_x - bend:g} {end_y:g}, {end_x:g} {end_y:g}",
            (start_x + end_x) / 2,
            (start_y + end_y) / 2 - 14,
        )
    if target_y >= source_y + node_height and abs(target_x - source_x) < node_width * 1.5:
        start_x = source_x + node_width / 2
        end_x = target_x + node_width / 2
        start_y = source_y + node_height
        end_y = target_y - 8
    else:
        start_x = source_x + (node_width if target_x >= source_x else 0)
        end_x = target_x + (0 if target_x >= source_x else node_width)
        start_y = source_y + node_height / 2
        end_y = target_y + node_height / 2
    curve = max(28, abs(end_y - start_y) / 2)
    path = f"M {start_x:g} {start_y:g} C {start_x:g} {start_y + curve:g}, {end_x:g} {end_y - curve:g}, {end_x:g} {end_y:g}"
    return path, (start_x + end_x) / 2, (start_y + end_y) / 2 - 14


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
