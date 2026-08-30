"""Deterministic evidence-backed public knowledge graph projection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

import yaml

from .models import (
    GRAPH_EDGE_KINDS,
    GRAPH_NODE_KINDS,
    GraphData,
    GraphEdge,
    GraphNode,
    PublicProject,
)
from .taxonomy import display_tag_label, normalize_tag_label


_STABLE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_RELATION_KINDS = frozenset({"EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT"})
_TAXONOMY_KEYS = frozenset({"focuses", "domains", "tags"})


@dataclass(frozen=True)
class _Focus:
    item_id: str
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class _Domain:
    item_id: str
    label: str
    focus_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class _Tag:
    item_id: str
    label: str
    domain_id: str
    parent_tag_id: str | None
    aliases: tuple[str, ...]


class KnowledgeTaxonomy:
    """Reviewed taxonomy with strict IDs, parent references, and aliases."""

    def __init__(
        self,
        focuses: tuple[_Focus, ...],
        domains: tuple[_Domain, ...],
        tags: tuple[_Tag, ...],
    ) -> None:
        self.focuses = focuses
        self.domains = domains
        self.tags = tags
        self._focuses = {item.item_id: item for item in focuses}
        self._domains = {item.item_id: item for item in domains}
        self._tags = {item.item_id: item for item in tags}
        self._domain_aliases = _alias_index(domains, "domain")
        self._tag_aliases = _alias_index(tags, "tag")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "KnowledgeTaxonomy":
        if not isinstance(value, Mapping) or frozenset(value) != _TAXONOMY_KEYS:
            raise ValueError("graph-taxonomy-shape")
        focuses = tuple(_focus(item) for item in _sequence(value["focuses"], "focuses"))
        domains = tuple(_domain(item) for item in _sequence(value["domains"], "domains"))
        tags = tuple(_tag(item) for item in _sequence(value["tags"], "tags"))
        _require_unique_ids(focuses, domains, tags)

        focus_ids = {item.item_id for item in focuses}
        domain_ids = {item.item_id for item in domains}
        tag_ids = {item.item_id for item in tags}
        for domain in domains:
            if domain.focus_id not in focus_ids:
                raise ValueError("graph-taxonomy-focus-reference")
        for tag in tags:
            if tag.domain_id not in domain_ids:
                raise ValueError("graph-taxonomy-domain-reference")
            if tag.parent_tag_id is not None and tag.parent_tag_id not in tag_ids:
                raise ValueError("graph-taxonomy-parent-reference")
            if tag.parent_tag_id == tag.item_id:
                raise ValueError("graph-taxonomy-parent-self")
        taxonomy = cls(focuses, domains, tags)
        taxonomy._require_acyclic_tags()
        return taxonomy

    @classmethod
    def from_file(cls, path: str | Path) -> "KnowledgeTaxonomy":
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("graph-taxonomy-shape")
        return cls.from_mapping(value)

    def require_domain(self, label: str) -> str:
        return self._require_alias(self._domain_aliases, label)

    def require_tag(self, label: str) -> str:
        return self._require_alias(self._tag_aliases, label)

    def focus_for(self, domain_id: str) -> str:
        try:
            return self._domains[domain_id].focus_id
        except KeyError:
            raise ValueError(f"graph-taxonomy-label: {domain_id}") from None

    def _require_alias(self, aliases: Mapping[str, str], label: str) -> str:
        try:
            return aliases[normalize_tag_label(label)]
        except KeyError:
            raise ValueError(f"graph-taxonomy-label: {label}") from None

    def _require_acyclic_tags(self) -> None:
        for tag in self.tags:
            seen = {tag.item_id}
            parent = tag.parent_tag_id
            while parent is not None:
                if parent in seen:
                    raise ValueError("graph-taxonomy-parent-cycle")
                seen.add(parent)
                parent = self._tags[parent].parent_tag_id


def load_knowledge_taxonomy(path: str | Path | None = None) -> KnowledgeTaxonomy:
    source = path or Path(__file__).parent.parent / "data" / "knowledge-taxonomy.yaml"
    return KnowledgeTaxonomy.from_file(source)


def build_knowledge_graph(
    projects: Iterable[PublicProject],
    articles: Mapping[str, object],
    evidence: Mapping[str, Sequence[object]],
    relations: Mapping[str, Sequence[Mapping[str, object]]],
    taxonomy: KnowledgeTaxonomy | Mapping[str, object] | str | Path,
) -> GraphData:
    """Project reviewed taxonomy, public evidence, and curated relations into a KG."""
    reviewed = _taxonomy(taxonomy)
    ordered_projects = tuple(sorted(projects, key=lambda item: item.project_id))
    project_ids = _require_unique_project_ids(ordered_projects)
    _require_known_mapping_keys(articles, project_ids, "graph-article-endpoint")
    _require_known_mapping_keys(evidence, project_ids, "graph-evidence-endpoint")
    _require_known_mapping_keys(relations, project_ids, "graph-relation-endpoint")
    public_evidence = _public_evidence(evidence)

    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str], GraphEdge] = {}
    _add_taxonomy(nodes, edges, reviewed)

    for project in ordered_projects:
        project_id = _project_node_id(project.project_id)
        _add_node(
            nodes,
            GraphNode(
                project_id,
                project.display_name,
                "Project",
                f"/projects/{quote(project.project_id, safe='')}",
                project.summary,
            ),
        )
        for label in project.tags.domain:
            domain_id = reviewed.require_domain(label)
            _add_edge(edges, GraphEdge(project_id, _focus_node_id(reviewed.focus_for(domain_id)), "HAS_FOCUS"))
            _add_edge(edges, GraphEdge(project_id, _domain_node_id(domain_id), "HAS_TAG"))
        for kind in ("problem", "pattern", "outcome"):
            for label in getattr(project.tags, kind):
                _add_edge(edges, GraphEdge(project_id, _tag_node_id(reviewed.require_tag(label)), "HAS_TAG"))
        for technology in project.tags.technology:
            technology_id = _technology_node_id(technology)
            _add_node(nodes, GraphNode(technology_id, display_tag_label(technology), "Technology"))
            _add_edge(edges, GraphEdge(project_id, technology_id, "USES_TECH"))
        _add_public_artifacts(nodes, edges, project, evidence.get(project.project_id, ()), reviewed)

    _add_curated_relations(edges, relations, project_ids, public_evidence)
    _validate_public_graph(nodes, edges)
    return GraphData(
        tuple(sorted(nodes.values(), key=_node_key)),
        tuple(sorted(edges.values(), key=_edge_key)),
    )


def _taxonomy(value: KnowledgeTaxonomy | Mapping[str, object] | str | Path) -> KnowledgeTaxonomy:
    if isinstance(value, KnowledgeTaxonomy):
        return value
    if isinstance(value, (str, Path)):
        return KnowledgeTaxonomy.from_file(value)
    return KnowledgeTaxonomy.from_mapping(value)


def _focus(value: object) -> _Focus:
    row = _row(value, frozenset({"id", "label"}), frozenset({"aliases"}), "focus")
    return _Focus(_id(row["id"]), _label(row["label"]), _aliases(row.get("aliases")))


def _domain(value: object) -> _Domain:
    row = _row(value, frozenset({"id", "label", "focus_id"}), frozenset({"aliases"}), "domain")
    return _Domain(
        _id(row["id"]),
        _label(row["label"]),
        _id(row["focus_id"]),
        _aliases(row.get("aliases")),
    )


def _tag(value: object) -> _Tag:
    row = _row(
        value,
        frozenset({"id", "label", "domain_id"}),
        frozenset({"aliases", "parent_tag_id"}),
        "tag",
    )
    parent = row.get("parent_tag_id")
    return _Tag(
        _id(row["id"]),
        _label(row["label"]),
        _id(row["domain_id"]),
        _id(parent) if parent is not None else None,
        _aliases(row.get("aliases")),
    )


def _row(
    value: object,
    required: frozenset[str],
    optional: frozenset[str],
    label: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"graph-taxonomy-{label}-shape")
    keys = frozenset(value)
    if not required <= keys or keys - required - optional:
        raise ValueError(f"graph-taxonomy-{label}-shape")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"graph-taxonomy-{label}-shape")
    return value


def _id(value: object) -> str:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError("graph-taxonomy-id")
    return value


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("graph-taxonomy-label")
    return display_tag_label(value)


def _aliases(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("graph-taxonomy-alias-shape")
    aliases = tuple(_label(item) for item in value)
    if len({normalize_tag_label(item) for item in aliases}) != len(aliases):
        raise ValueError("graph-taxonomy-duplicate-alias")
    return aliases


def _require_unique_ids(*groups: Sequence[object]) -> None:
    for group in groups:
        ids = [item.item_id for item in group]  # type: ignore[attr-defined]
        if len(ids) != len(set(ids)):
            raise ValueError("graph-taxonomy-duplicate-id")


def _alias_index(items: Sequence[object], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        item_id = item.item_id  # type: ignore[attr-defined]
        values = (item.label, *item.aliases)  # type: ignore[attr-defined]
        for value in values:
            identity = normalize_tag_label(value)
            if identity in result and result[identity] != item_id:
                raise ValueError(f"graph-taxonomy-duplicate-{label}-alias")
            result[identity] = item_id
    return result


def _require_unique_project_ids(projects: Sequence[PublicProject]) -> set[str]:
    project_ids = [project.project_id for project in projects]
    if len(project_ids) != len(set(project_ids)):
        raise ValueError("graph-project-duplicate-id")
    return set(project_ids)


def _require_known_mapping_keys(values: Mapping[str, object], project_ids: set[str], error: str) -> None:
    if any(project_id not in project_ids for project_id in values):
        raise ValueError(error)


def _public_evidence(evidence: Mapping[str, Sequence[object]]) -> dict[str, tuple[str, dict[str, str]]]:
    result: dict[str, tuple[str, dict[str, str]]] = {}
    for project_id in sorted(evidence):
        for record in evidence[project_id]:
            evidence_id = _evidence_value(record, "id", "evidence_id")
            label = _evidence_value(record, "label")
            if evidence_id in result:
                raise ValueError("graph-evidence-duplicate-id")
            result[evidence_id] = (
                project_id,
                {"label": label, "url": f"/projects/{quote(project_id, safe='')}?tab=evidence"},
            )
    return result


def _evidence_value(record: object, key: str, attribute: str | None = None) -> str:
    value: Any
    if isinstance(record, Mapping):
        value = record.get(key)
    else:
        value = getattr(record, attribute or key, None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("graph-evidence-shape")
    return value


def _add_taxonomy(
    nodes: dict[str, GraphNode],
    edges: dict[tuple[str, str, str], GraphEdge],
    taxonomy: KnowledgeTaxonomy,
) -> None:
    for focus in taxonomy.focuses:
        _add_node(nodes, GraphNode(_focus_node_id(focus.item_id), focus.label, "KnowledgeFocus"))
    for domain in taxonomy.domains:
        domain_id = _domain_node_id(domain.item_id)
        _add_node(nodes, GraphNode(domain_id, domain.label, "KnowledgeDomain"))
        _add_edge(edges, GraphEdge(_focus_node_id(domain.focus_id), domain_id, "FOCUS_HAS_TAG"))
    for tag in taxonomy.tags:
        tag_id = _tag_node_id(tag.item_id)
        _add_node(nodes, GraphNode(tag_id, tag.label, "KnowledgeTag"))
        parent_id = _tag_node_id(tag.parent_tag_id) if tag.parent_tag_id else _domain_node_id(tag.domain_id)
        _add_edge(edges, GraphEdge(parent_id, tag_id, "HAS_SUBTAG"))


def _add_public_artifacts(
    nodes: dict[str, GraphNode],
    edges: dict[tuple[str, str, str], GraphEdge],
    project: PublicProject,
    evidence: Sequence[object],
    taxonomy: KnowledgeTaxonomy,
) -> None:
    project_node = _project_node_id(project.project_id)
    for record in evidence:
        evidence_id = _evidence_value(record, "id", "evidence_id")
        label = _evidence_value(record, "label")
        artifact_id = _artifact_node_id(project.project_id, evidence_id)
        url = f"/projects/{quote(project.project_id, safe='')}?tab=evidence"
        _add_node(nodes, GraphNode(artifact_id, label, "Artifact", url, label))
        _add_edge(edges, GraphEdge(project_node, artifact_id, "PRODUCES_ARTIFACT"))
        for tag_id in _artifact_tag_ids(record, taxonomy):
            _add_edge(edges, GraphEdge(artifact_id, _tag_node_id(tag_id), "ARTIFACT_HAS_TAG"))


def _artifact_tag_ids(record: object, taxonomy: KnowledgeTaxonomy) -> tuple[str, ...]:
    if not isinstance(record, Mapping):
        return ()
    if "tag_ids" in record:
        values = record["tag_ids"]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError("graph-artifact-tag-shape")
        result = []
        for value in values:
            tag_id = _id(value)
            if tag_id not in taxonomy._tags:
                raise ValueError(f"graph-taxonomy-label: {tag_id}")
            result.append(tag_id)
        return tuple(result)
    if "tags" in record:
        values = record["tags"]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError("graph-artifact-tag-shape")
        return tuple(taxonomy.require_tag(_label(value)) for value in values)
    return ()


def _add_curated_relations(
    edges: dict[tuple[str, str, str], GraphEdge],
    relations: Mapping[str, Sequence[Mapping[str, object]]],
    project_ids: set[str],
    evidence: Mapping[str, tuple[str, dict[str, str]]],
) -> None:
    seen: set[tuple[str, str, str]] = set()
    for source_id in sorted(relations):
        for relation in relations[source_id]:
            if not isinstance(relation, Mapping):
                raise ValueError("graph-relation-shape")
            kind = relation.get("type")
            if kind not in _RELATION_KINDS or kind not in GRAPH_EDGE_KINDS:
                raise ValueError("graph-edge-kind")
            target_id = relation.get("target")
            if not isinstance(target_id, str) or target_id not in project_ids:
                raise ValueError("graph-relation-endpoint")
            if source_id == target_id:
                raise ValueError("graph-relation-self")
            identity = (kind, source_id, target_id)
            if identity in seen:
                raise ValueError("graph-relation-duplicate-id")
            seen.add(identity)
            evidence_ids = relation.get("evidence_ids")
            if not isinstance(evidence_ids, Sequence) or isinstance(evidence_ids, (str, bytes)) or not evidence_ids:
                raise ValueError("graph-relation-evidence")
            if any(not isinstance(item, str) for item in evidence_ids) or len(evidence_ids) != len(set(evidence_ids)):
                raise ValueError("graph-relation-evidence")
            try:
                links = tuple(evidence[item][1] for item in sorted(evidence_ids))
            except KeyError:
                raise ValueError("graph-relation-evidence") from None
            _add_edge(
                edges,
                GraphEdge(_project_node_id(source_id), _project_node_id(target_id), kind, 1, links),
            )


def _add_node(nodes: dict[str, GraphNode], node: GraphNode) -> None:
    if node.node_id in nodes and nodes[node.node_id] != node:
        raise ValueError("graph-node-duplicate-id")
    nodes[node.node_id] = node


def _add_edge(edges: dict[tuple[str, str, str], GraphEdge], edge: GraphEdge) -> None:
    identity = (edge.kind, edge.source_id, edge.target_id)
    if identity in edges and edges[identity] != edge:
        raise ValueError("graph-edge-duplicate-id")
    edges[identity] = edge


def _validate_public_graph(
    nodes: Mapping[str, GraphNode],
    edges: Mapping[tuple[str, str, str], GraphEdge],
) -> None:
    for node in nodes.values():
        if node.kind not in GRAPH_NODE_KINDS:
            raise ValueError("graph-node-kind")
    for edge in edges.values():
        if edge.kind not in GRAPH_EDGE_KINDS:
            raise ValueError("graph-edge-kind")
        if edge.source_id == edge.target_id:
            raise ValueError("graph-edge-self")
        if edge.source_id not in nodes or edge.target_id not in nodes:
            raise ValueError("graph-edge-endpoint")


def _project_node_id(project_id: str) -> str:
    return f"project:{quote(project_id, safe='')}"


def _focus_node_id(focus_id: str) -> str:
    return f"focus:{focus_id}"


def _domain_node_id(domain_id: str) -> str:
    return f"domain:{domain_id}"


def _tag_node_id(tag_id: str) -> str:
    return f"tag:{tag_id}"


def _technology_node_id(label: str) -> str:
    return f"technology:{quote(normalize_tag_label(label), safe='')}"


def _artifact_node_id(project_id: str, evidence_id: str) -> str:
    return f"artifact:{quote(project_id, safe='')}:{quote(evidence_id, safe='')}"


def _node_key(node: GraphNode) -> tuple[str, str, str]:
    return node.kind, node.node_id, node.label


def _edge_key(edge: GraphEdge) -> tuple[str, str, str, int, tuple[tuple[str, str], ...]]:
    links = tuple((item["label"], item["url"]) for item in edge.evidence_links)
    return edge.kind, edge.source_id, edge.target_id, -edge.weight, links
