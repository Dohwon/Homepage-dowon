from dataclasses import replace

import pytest
import yaml

from atlas_worker.kg import (
    KnowledgeTaxonomy,
    build_knowledge_graph,
    load_knowledge_taxonomy,
    load_project_relations,
)
from atlas_worker.models import (
    GRAPH_EDGE_KINDS,
    EvidenceRecord,
    GraphEdge,
    GraphNode,
    ProjectArticle,
    TagSet,
    validate_schema,
)
from atlas_worker.privacy import PrivacyGate
from tests.worker.helpers import make_public_project


@pytest.fixture
def taxonomy_data():
    return {
        "focuses": [
            {"id": "product-delivery", "label": "Product Delivery"},
            {"id": "ai-quality", "label": "AI Quality"},
        ],
        "domains": [
            {
                "id": "mobility",
                "label": "Mobility",
                "focus_id": "product-delivery",
                "aliases": ["Mobile App"],
            },
            {"id": "evaluation", "label": "Evaluation", "focus_id": "ai-quality"},
        ],
        "tags": [
            {
                "id": "evaluation-benchmarking",
                "label": "Evaluation / Benchmarking",
                "domain_id": "evaluation",
                "aliases": ["Routing", "Evaluation", "Tool"],
            },
            {
                "id": "mobility-navigation",
                "label": "Mobility / Navigation",
                "domain_id": "mobility",
                "aliases": ["Navigation", "Route validation"],
            },
        ],
    }


@pytest.fixture
def taxonomy(taxonomy_data):
    return KnowledgeTaxonomy.from_mapping(taxonomy_data)


@pytest.fixture
def project_factory():
    def factory(
        project_id,
        *,
        domain=("Mobility",),
        problem=("Routing",),
        pattern=("Evaluation",),
        technology=("JavaScript",),
        outcome=("Tool",),
    ):
        return replace(
            make_public_project(project_id),
            tags=TagSet(
                domain=domain,
                problem=problem,
                pattern=pattern,
                technology=technology,
                outcome=outcome,
            ),
        )

    return factory


@pytest.fixture
def projects(project_factory):
    return (project_factory("left"), project_factory("right", domain=("Evaluation",)))


def public_article(project_id):
    return ProjectArticle(
        project_id=project_id,
        title=f"{project_id} article",
        summary=f"{project_id} public article",
        sections=(),
        readiness="ready",
    )


def public_evidence(project_id, evidence_id="routing-spec"):
    return EvidenceRecord(
        evidence_id=evidence_id,
        project_id=project_id,
        label="Routing spec",
        source_type="spec",
        source_locator="private/session/locator.jsonl:7",
        observed_at="2026-08-27T10:00:00Z",
        privacy_class="public-safe",
        content_hash="a" * 64,
    )


def public_article_mapping(project_id, readiness="ready"):
    return replace(public_article(project_id), readiness=readiness).to_public_dict()


def test_kg_uses_six_node_types_and_no_similarity_edges(projects, taxonomy):
    graph = build_knowledge_graph(projects, {}, {}, {}, taxonomy)

    assert {node.kind for node in graph.nodes} <= {
        "KnowledgeFocus",
        "KnowledgeDomain",
        "KnowledgeTag",
        "Project",
        "Technology",
        "Artifact",
    }
    assert "project-similarity" not in {edge.kind for edge in graph.edges}
    assert all(edge.kind in GRAPH_EDGE_KINDS for edge in graph.edges)


def test_reviewed_taxonomy_loads_old_labels_and_current_profile_aliases():
    taxonomy = load_knowledge_taxonomy()

    assert taxonomy.require_domain("Mobility") == "product-ux"
    assert taxonomy.require_domain("LLM 평가") == "evaluation"
    assert taxonomy.require_tag("Evaluation / Benchmarking") == "evaluation-benchmarking"
    assert taxonomy.require_tag("경로 정확도") == "evaluation-benchmarking"
    assert taxonomy.require_tag("재현 가능한 도로 기록") == "product-ux-app-surface"


def test_shared_tags_do_not_create_direct_project_edge(project_factory, taxonomy):
    left = project_factory("left", domain=("Mobility",), technology=("JavaScript",))
    right = project_factory("right", domain=("Mobility",), technology=("JavaScript",))

    graph = build_knowledge_graph((left, right), {}, {}, {}, taxonomy)
    project_pairs = {
        frozenset((edge.source_id, edge.target_id))
        for edge in graph.edges
        if edge.source_id.startswith("project:") and edge.target_id.startswith("project:")
    }

    assert project_pairs == set()


def test_curated_project_relation_requires_public_evidence(projects, taxonomy):
    relations = {
        "left": [
            {"type": "EVOLVED_FROM", "target": "right", "evidence_ids": ["missing"]}
        ]
    }

    with pytest.raises(ValueError, match="graph-relation-evidence"):
        build_knowledge_graph(projects, {}, {}, relations, taxonomy)


def test_profile_labels_map_to_reviewed_taxonomy_aliases(project_factory, taxonomy):
    project = project_factory("alpha", domain=("Mobile App",))

    graph = build_knowledge_graph((project,), {}, {}, {}, taxonomy)
    project_edges = {
        (edge.target_id, edge.kind)
        for edge in graph.edges
        if edge.source_id == "project:alpha"
    }

    assert ("focus:product-delivery", "HAS_FOCUS") in project_edges
    assert ("domain:mobility", "HAS_TAG") in project_edges
    assert ("tag:evaluation-benchmarking", "HAS_TAG") in project_edges
    assert ("technology:javascript", "USES_TECH") in project_edges


def test_projection_is_input_stable_and_never_caps_project_nodes(project_factory, taxonomy):
    projects = tuple(project_factory(f"project-{index}") for index in range(32))

    first = build_knowledge_graph(projects, {}, {}, {}, taxonomy)
    second = build_knowledge_graph(tuple(reversed(projects)), {}, {}, {}, taxonomy)

    assert first == second
    assert len([node for node in first.nodes if node.kind == "Project"]) == 32


def test_public_artifacts_and_relations_include_safe_evidence_links(projects, taxonomy):
    evidence = {
        "left": (
            {
                "id": "routing-spec",
                "project_id": "left",
                "label": "Routing spec",
                "source_type": "spec",
                "observed_at": "2026-08-27T10:00:00Z",
            },
        )
    }
    relations = {
        "left": [
            {
                "type": "EVOLVED_FROM",
                "target": "right",
                "evidence_ids": ["routing-spec"],
            }
        ]
    }

    graph = build_knowledge_graph(
        projects,
        {"left": public_article("left")},
        evidence,
        relations,
        taxonomy,
    )
    artifact = next(node for node in graph.nodes if node.kind == "Artifact")
    relation = next(edge for edge in graph.edges if edge.kind == "EVOLVED_FROM")

    assert artifact.node_id == "artifact:left:routing-spec"
    assert artifact.url == "/projects/left?tab=evidence"
    assert relation.evidence_links == (
        {"label": "Routing spec", "url": "/projects/left?tab=evidence"},
    )
    validate_schema(graph.to_public_dict(), "public-graph")


@pytest.mark.parametrize(
    ("relation", "message"),
    (
        (
            {"type": "project-similarity", "target": "right", "evidence_ids": ["proof"]},
            "graph-edge-kind",
        ),
        (
            {"type": "EVOLVED_FROM", "target": "right", "evidence_ids": []},
            "graph-relation-evidence",
        ),
        (
            {
                "type": "EVOLVED_FROM",
                "target": "right",
                "evidence_ids": ["proof"],
                "label": "unreviewed",
            },
            "graph-relation-shape",
        ),
    ),
)
def test_project_relations_loader_is_strict_and_evidence_backed(tmp_path, relation, message):
    source = tmp_path / "project_memory" / "project-atlas" / "relations.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        yaml.safe_dump({"relations": [relation]}, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_project_relations(tmp_path, PrivacyGate(alias_key=b"unit-test-key"))


@pytest.mark.parametrize(
    "url",
    (
        "/home/dowon/private/session.jsonl",
        "session:019fca18-private-locator",
        "file:///home/dowon/private/evidence",
        "/projects/../../private",
        "/projects/..%2Fprivate?tab=evidence",
        "/projects/%252E%252E%252Fprivate?tab=evidence",
    ),
)
def test_graph_node_projection_rejects_private_locator_urls(url):
    node = GraphNode("project:alpha", "Alpha", "Project", url, "Alpha project")

    with pytest.raises(ValueError, match="graph-node-url"):
        node.to_public_dict()


@pytest.mark.parametrize(
    "url",
    (
        "/home/dowon/.codex/sessions/private.jsonl:12",
        "session:private-evidence",
        "file:///tmp/evidence",
        "/projects/../private?tab=evidence",
        "/projects/..%2Fprivate?tab=evidence",
        "/projects/%252E%252E%252Fprivate?tab=evidence",
    ),
)
def test_graph_evidence_link_projection_rejects_private_locator_urls(url):
    edge = GraphEdge(
        "project:left",
        "project:right",
        "EVOLVED_FROM",
        evidence_links=({"label": "Private locator", "url": url},),
    )

    with pytest.raises(ValueError, match="graph-evidence-link-url"):
        edge.to_public_dict()


def test_public_graph_schema_rejects_private_locator_urls():
    payload = {
        "nodes": [
            {
                "id": "project:alpha",
                "label": "Alpha",
                "kind": "Project",
                "url": "/home/dowon/private/session.jsonl",
                "summary": "Alpha project",
            }
        ],
        "edges": [
            {
                "id": "evolved_from:project%3Aalpha:project%3Abeta",
                "source": "project:alpha",
                "target": "project:beta",
                "kind": "EVOLVED_FROM",
                "weight": 1,
                "evidence_links": [
                    {
                        "label": "Private evidence",
                        "url": "session:private-evidence",
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError):
        validate_schema(payload, "public-graph")


@pytest.mark.parametrize(
    "url",
    (
        "/projects/..%2Fprivate?tab=evidence",
        "/projects/%252E%252E%252Fprivate?tab=evidence",
    ),
)
def test_public_graph_schema_rejects_encoded_traversal_urls(url):
    payload = {
        "nodes": [
            {
                "id": "project:alpha",
                "label": "Alpha",
                "kind": "Project",
                "url": url,
                "summary": "Alpha project",
            }
        ],
        "edges": [],
    }

    with pytest.raises(ValueError):
        validate_schema(payload, "public-graph")


@pytest.mark.parametrize(
    "url",
    (
        "/projects/alpha",
        "/projects/alpha%2Fbeta?tab=evidence",
        "https://example.com/public/evidence",
    ),
)
def test_graph_projection_accepts_internal_project_routes_and_safe_https(url):
    node = GraphNode("project:alpha", "Alpha", "Project", url, "Alpha project")
    edge = GraphEdge(
        "project:left",
        "project:right",
        "EVOLVED_FROM",
        evidence_links=({"label": "Public evidence", "url": url},),
    )

    assert node.to_public_dict()["url"] == url
    assert edge.to_public_dict()["evidence_links"] == [{"label": "Public evidence", "url": url}]


def test_public_evidence_requires_a_matching_article(projects, taxonomy):
    evidence = {"left": (public_evidence("left"),)}

    with pytest.raises(ValueError, match="graph-evidence-article"):
        build_knowledge_graph(projects, {}, evidence, {}, taxonomy)


def test_public_evidence_project_id_must_match_mapping_key(projects, taxonomy):
    evidence = {"left": (public_evidence("right"),)}

    with pytest.raises(ValueError, match="graph-evidence-project"):
        build_knowledge_graph(
            projects,
            {"left": public_article("left")},
            evidence,
            {},
            taxonomy,
        )


def test_public_article_project_id_must_match_mapping_key(projects, taxonomy):
    evidence = {"left": (public_evidence("left"),)}

    with pytest.raises(ValueError, match="graph-article-project"):
        build_knowledge_graph(
            projects,
            {"left": public_article("right")},
            evidence,
            {},
            taxonomy,
        )


def test_id_only_article_mapping_cannot_publish_evidence(projects, taxonomy):
    evidence = {"left": (public_evidence("left"),)}

    with pytest.raises(ValueError, match="graph-article-schema"):
        build_knowledge_graph(
            projects,
            {"left": {"project_id": "left"}},
            evidence,
            {},
            taxonomy,
        )


def test_review_required_article_cannot_publish_evidence(projects, taxonomy):
    evidence = {"left": (public_evidence("left"),)}
    article = replace(public_article("left"), readiness="review-required")

    with pytest.raises(ValueError, match="graph-article-readiness"):
        build_knowledge_graph(
            projects,
            {"left": article},
            evidence,
            {},
            taxonomy,
        )


def test_complete_ready_article_mapping_can_publish_evidence(projects, taxonomy):
    graph = build_knowledge_graph(
        projects,
        {"left": public_article_mapping("left")},
        {"left": (public_evidence("left"),)},
        {},
        taxonomy,
    )

    assert any(node.kind == "Artifact" for node in graph.nodes)


def test_unknown_project_taxonomy_label_enters_review(project_factory, taxonomy):
    project = project_factory("alpha", problem=("Unreviewed label",))

    with pytest.raises(ValueError, match="graph-taxonomy-label"):
        build_knowledge_graph((project,), {}, {}, {}, taxonomy)


def test_duplicate_taxonomy_ids_are_rejected(taxonomy_data):
    taxonomy_data["domains"].append(
        {"id": "mobility", "label": "Duplicate", "focus_id": "product-delivery"}
    )

    with pytest.raises(ValueError, match="graph-taxonomy-duplicate-id"):
        KnowledgeTaxonomy.from_mapping(taxonomy_data)


def test_taxonomy_file_loader_rejects_duplicate_mapping_keys(tmp_path):
    taxonomy_path = tmp_path / "duplicate-key.yaml"
    taxonomy_path.write_text(
        """focuses:
  - id: first
    id: overwritten
    label: Focus
domains: []
tags: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="graph-taxonomy-yaml-key"):
        KnowledgeTaxonomy.from_file(taxonomy_path)


def test_taxonomy_file_loader_rejects_merge_keys(tmp_path):
    taxonomy_path = tmp_path / "merge-key.yaml"
    taxonomy_path.write_text(
        """focuses:
  - &focus
    id: first
    label: Focus
  - <<: *focus
    id: second
domains: []
tags: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="graph-taxonomy-yaml-merge"):
        KnowledgeTaxonomy.from_file(taxonomy_path)


def test_duplicate_public_evidence_ids_are_rejected(projects, taxonomy):
    evidence = {
        "left": (public_evidence("left", "same"),),
        "right": (public_evidence("right", "same"),),
    }
    articles = {
        "left": public_article("left"),
        "right": public_article("right"),
    }

    with pytest.raises(ValueError, match="graph-evidence-duplicate-id"):
        build_knowledge_graph(projects, articles, evidence, {}, taxonomy)


@pytest.mark.parametrize(
    ("relations", "message"),
    [
        (
            {"left": [{"type": "EVOLVED_FROM", "target": "missing", "evidence_ids": []}]},
            "graph-relation-endpoint",
        ),
        (
            {"left": [{"type": "EVOLVED_FROM", "target": "left", "evidence_ids": []}]},
            "graph-relation-self",
        ),
        (
            {"left": [{"type": "SIMILAR_TO", "target": "right", "evidence_ids": []}]},
            "graph-edge-kind",
        ),
    ],
)
def test_curated_relations_validate_endpoints_self_edges_and_kinds(
    projects, taxonomy, relations, message
):
    with pytest.raises(ValueError, match=message):
        build_knowledge_graph(projects, {}, {}, relations, taxonomy)
