from dataclasses import replace

import pytest

from atlas_worker.graph import build_graph, similarity
from atlas_worker.models import (
    GRAPH_EDGE_KINDS,
    GRAPH_NODE_KINDS,
    GraphEdge,
    TagCandidate,
    TagSet,
)
from atlas_worker.taxonomy import select_tags
from tests.worker.helpers import make_public_project


def test_public_graph_contract_uses_evidence_backed_kinds():
    assert GRAPH_NODE_KINDS == frozenset(
        {
            "KnowledgeFocus",
            "KnowledgeDomain",
            "KnowledgeTag",
            "Project",
            "Technology",
            "Artifact",
        }
    )
    assert GRAPH_EDGE_KINDS == frozenset(
        {
            "HAS_FOCUS",
            "FOCUS_HAS_TAG",
            "HAS_SUBTAG",
            "HAS_TAG",
            "USES_TECH",
            "PRODUCES_ARTIFACT",
            "ARTIFACT_HAS_TAG",
            "EVOLVED_FROM",
            "VALIDATES",
            "DEPLOYS",
            "REUSES_COMPONENT",
        }
    )
    edge = GraphEdge("project:left", "project:right", "EVOLVED_FROM")

    assert edge.edge_id == "evolved_from:project%3Aleft:project%3Aright"


def test_inferred_semantic_tag_requires_two_source_classes():
    candidates = [
        TagCandidate("Agent Routing", "problem", "source", "code-1", 0.9),
        TagCandidate("Agent Routing", "problem", "session", "session-1", 0.8),
        TagCandidate("Generic", "pattern", "session", "session-2", 0.9),
    ]

    selected = select_tags(make_public_project("alpha"), candidates)

    assert selected.problem == ("Agent Routing", "Routing")
    assert "Generic" not in selected.pattern


def test_manual_profile_approval_selects_one_source_and_rejection_excludes_a_baseline_tag():
    candidates = [
        TagCandidate("Workflow", "pattern", "profile", "profile-approve", 0.1, "approve"),
        TagCandidate(" python ", "technology", "profile", "profile-reject", 1.0, "reject"),
    ]

    selected = select_tags(make_public_project("alpha"), candidates)

    assert selected.pattern == ("Evaluation", "Workflow")
    assert selected.technology == ()


def test_single_source_and_duplicate_evidence_do_not_select_an_inferred_tag():
    candidates = [
        TagCandidate("Single Source", "technology", "source", "source-1", 1.0),
        TagCandidate("Repeated Source", "technology", "source", "source-2", 1.0),
        TagCandidate("Repeated Source", "technology", "source", "source-2", 1.0),
        TagCandidate("Repeated Source", "technology", "source", "source-3", 0.9),
        TagCandidate("Shared Identifier", "technology", "source", "shared-id", 1.0),
        TagCandidate("Shared Identifier", "technology", "session", "shared-id", 1.0),
    ]

    selected = select_tags(make_public_project("alpha"), candidates)

    assert selected.technology == ("Python",)


def test_selected_tags_are_stable_for_shuffled_candidates_and_ranked_by_evidence():
    candidates = [
        TagCandidate(" lower rank ", "technology", "source", "a-source", 0.2),
        TagCandidate("lower rank", "technology", "session", "a-session", 0.2),
        TagCandidate("Higher Rank", "technology", "source", "b-source", 0.9),
        TagCandidate(" higher rank ", "technology", "session", "b-session", 0.9),
    ]
    project = replace(
        make_public_project("alpha"),
        tags=TagSet(
            domain=("AI",),
            problem=("Routing",),
            pattern=("Evaluation",),
            technology=("One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven"),
            outcome=("Tool",),
        ),
    )

    first = select_tags(project, candidates)
    second = select_tags(project, tuple(reversed(candidates)))

    assert first == second
    assert "Higher Rank" in first.technology
    assert "lower rank" not in first.technology


def test_rejecting_the_only_required_tag_blocks_public_readiness_without_filler():
    candidate = TagCandidate(" ai ", "domain", "profile", "profile-reject", 1.0, "reject")

    with pytest.raises(ValueError, match="not public-ready: domain requires at least 1 supported tag"):
        select_tags(make_public_project("alpha"), [candidate])


@pytest.mark.parametrize(
    "candidate",
    [
        TagCandidate("Unknown kind", "unknown", "source", "id-1", 1.0),
        TagCandidate("Unknown source", "technology", "archive", "id-1", 1.0),
        TagCandidate("Unknown decision", "technology", "source", "id-1", 1.0, "hold"),
    ],
)
def test_unknown_tag_metadata_values_are_rejected(candidate):
    with pytest.raises(ValueError, match="Unknown (kind|source_class|decision)"):
        select_tags(make_public_project("alpha"), [candidate])


def test_similarity_uses_the_specified_tag_weights_after_normalization():
    left = make_public_project("left")
    right = replace(
        make_public_project("right"),
        tags=TagSet(
            domain=(" ai ",),
            problem=("Routing",),
            pattern=("Other",),
            technology=("Python",),
            outcome=("Tool",),
        ),
    )

    assert similarity(left, right) == 15


def test_graph_canonicalizes_normalized_tag_nodes_and_aggregates_similarity_reasons():
    left = replace(
        make_public_project("alpha"),
        tags=TagSet(
            domain=("AI", " ai "),
            problem=("Routing",),
            pattern=("Evaluation",),
            technology=("Python",),
            outcome=("Tool",),
        ),
    )
    right = make_public_project("beta")

    graph = build_graph((right, left))
    domain_nodes = [node for node in graph.nodes if node.kind == "domain"]
    similarity_edges = [edge for edge in graph.edges if edge.kind == "project-similarity"]

    assert [(node.node_id, node.label) for node in domain_nodes] == [("domain:ai", "AI")]
    assert len(similarity_edges) == 1
    assert similarity_edges[0].weight == 20
    assert similarity_edges[0].reasons == (
        "domain:AI",
        "problem:Routing",
        "pattern:Evaluation",
        "technology:Python",
        "outcome:Tool",
    )


def test_graph_omits_zero_score_similarity_edges():
    other = replace(
        make_public_project("other"),
        tags=TagSet(
            domain=("Data",),
            problem=("Search",),
            pattern=("Pipeline",),
            technology=("Rust",),
            outcome=("Report",),
        ),
    )

    graph = build_graph((make_public_project("alpha"), other))

    assert not [edge for edge in graph.edges if edge.kind == "project-similarity"]


def test_project_neighbors_accepts_project_ids_that_need_canonical_encoding():
    graph = build_graph((make_public_project("alpha/beta"), make_public_project("gamma")))

    neighbors = graph.project_neighbors("alpha/beta")

    assert len(neighbors) == 1
    assert neighbors[0].source_id == "project:alpha%2Fbeta"


def test_project_neighbors_keeps_raw_ids_distinct_from_canonical_node_ids():
    special_tags = TagSet(
        domain=("Data",),
        problem=("Search",),
        pattern=("Pipeline",),
        technology=("Rust",),
        outcome=("Report",),
    )
    graph = build_graph(
        (
            make_public_project("alpha"),
            make_public_project("beta"),
            replace(make_public_project("project:alpha"), tags=special_tags),
            replace(make_public_project("gamma"), tags=special_tags),
        )
    )

    alpha_neighbors = graph.project_neighbors("alpha")
    special_neighbors = graph.project_neighbors("project:alpha")

    assert {(edge.source_id, edge.target_id) for edge in alpha_neighbors} == {
        ("project:alpha", "project:beta")
    }
    assert {(edge.source_id, edge.target_id) for edge in special_neighbors} == {
        ("project:gamma", "project:project%3Aalpha")
    }


def test_similarity_edges_are_limited_to_five_neighbors_globally_and_are_input_stable():
    projects = tuple(make_public_project(f"project-{index}") for index in range(8))

    first = build_graph(projects)
    second = build_graph(tuple(reversed(projects)))
    degrees = {project.project_id: 0 for project in projects}
    for edge in first.edges:
        if edge.kind == "project-similarity":
            degrees[edge.source_id.removeprefix("project:")] += 1
            degrees[edge.target_id.removeprefix("project:")] += 1

    assert first == second
    assert all(degree <= 5 for degree in degrees.values())
    assert len(first.project_neighbors("project-0")) <= 5
