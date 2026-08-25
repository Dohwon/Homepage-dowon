"""Deterministic public graph generation from selected project tags."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from urllib.parse import quote

from .models import GraphData, GraphEdge, GraphNode, PublicProject
from .taxonomy import display_tag_label, normalize_tag_label


TAG_WEIGHTS = {"domain": 4, "problem": 6, "pattern": 5, "technology": 1, "outcome": 4}
_TAG_KINDS = tuple(TAG_WEIGHTS)
_MAX_NEIGHBORS = 5


def similarity(left: PublicProject, right: PublicProject) -> int:
    """Score normalized shared taxonomy labels using the public graph weights."""
    return sum(
        len(_tag_identities(left, kind) & _tag_identities(right, kind)) * weight
        for kind, weight in TAG_WEIGHTS.items()
    )


def build_graph(projects: tuple[PublicProject, ...]) -> GraphData:
    """Build typed tag membership and globally degree-bounded similarity edges."""
    ordered_projects = tuple(sorted(projects, key=lambda project: project.project_id))
    _require_unique_project_ids(ordered_projects)
    tag_labels = _canonical_tag_labels(ordered_projects)
    nodes = _nodes(ordered_projects, tag_labels)
    membership_edges = _membership_edges(ordered_projects, tag_labels)
    similarity_edges = _select_similarity_edges(ordered_projects, tag_labels)
    edges = tuple(
        sorted(
            membership_edges + similarity_edges,
            key=lambda edge: (edge.kind, edge.source_id, edge.target_id, -edge.weight, edge.reasons),
        )
    )
    return GraphData(nodes=nodes, edges=edges)


def _require_unique_project_ids(projects: tuple[PublicProject, ...]) -> None:
    project_ids = [project.project_id for project in projects]
    if len(project_ids) != len(set(project_ids)):
        raise ValueError("Project graph requires unique project_id values")


def _canonical_tag_labels(projects: tuple[PublicProject, ...]) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], list[str]] = defaultdict(list)
    for project in projects:
        for kind in _TAG_KINDS:
            for label in getattr(project.tags, kind):
                labels[(kind, normalize_tag_label(label))].append(display_tag_label(label))
    return {
        key: min(values, key=lambda value: (normalize_tag_label(value), value))
        for key, values in labels.items()
    }


def _nodes(projects: tuple[PublicProject, ...], tag_labels: dict[tuple[str, str], str]) -> tuple[GraphNode, ...]:
    project_nodes = [
        GraphNode(_project_node_id(project.project_id), project.display_name, "project")
        for project in projects
    ]
    tag_nodes = [
        GraphNode(_tag_node_id(kind, identity), label, kind)
        for (kind, identity), label in tag_labels.items()
    ]
    return tuple(sorted(project_nodes + tag_nodes, key=lambda node: (node.kind, node.node_id)))


def _membership_edges(
    projects: tuple[PublicProject, ...], tag_labels: dict[tuple[str, str], str]
) -> tuple[GraphEdge, ...]:
    edges = []
    for project in projects:
        for kind in _TAG_KINDS:
            for identity in sorted(_tag_identities(project, kind)):
                edges.append(
                    GraphEdge(
                        _project_node_id(project.project_id),
                        _tag_node_id(kind, identity),
                        "tag-membership",
                        1,
                    )
                )
    return tuple(edges)


def _select_similarity_edges(
    projects: tuple[PublicProject, ...], tag_labels: dict[tuple[str, str], str]
) -> tuple[GraphEdge, ...]:
    candidates = []
    for left, right in combinations(projects, 2):
        score = similarity(left, right)
        if score <= 0:
            continue
        source_id, target_id = sorted((_project_node_id(left.project_id), _project_node_id(right.project_id)))
        candidates.append(
            GraphEdge(source_id, target_id, "project-similarity", score, _similarity_reasons(left, right, tag_labels))
        )

    degrees = defaultdict(int)
    selected = []
    for edge in sorted(candidates, key=lambda item: (-item.weight, item.source_id, item.target_id, item.reasons)):
        if degrees[edge.source_id] >= _MAX_NEIGHBORS or degrees[edge.target_id] >= _MAX_NEIGHBORS:
            continue
        degrees[edge.source_id] += 1
        degrees[edge.target_id] += 1
        selected.append(edge)
    return tuple(selected)


def _similarity_reasons(
    left: PublicProject, right: PublicProject, tag_labels: dict[tuple[str, str], str]
) -> tuple[str, ...]:
    reasons = []
    for kind in _TAG_KINDS:
        for identity in sorted(_tag_identities(left, kind) & _tag_identities(right, kind)):
            reasons.append(f"{kind}:{tag_labels[(kind, identity)]}")
    return tuple(reasons)


def _tag_identities(project: PublicProject, kind: str) -> set[str]:
    return {normalize_tag_label(label) for label in getattr(project.tags, kind)}


def _project_node_id(project_id: str) -> str:
    return f"project:{quote(project_id, safe='')}"


def _tag_node_id(kind: str, identity: str) -> str:
    return f"{kind}:{quote(identity, safe='')}"
