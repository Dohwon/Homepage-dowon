import csv
import json
from pathlib import Path

import pytest

from scripts.import_llm_wiki_graph import audit_llm_wiki_graph


APPROVED_NODE_TYPES = {
    "KnowledgeFocus",
    "KnowledgeDomain",
    "KnowledgeTag",
    "Project",
    "Technology",
    "Artifact",
}
APPROVED_EDGE_TYPES = {
    "HAS_FOCUS",
    "FOCUS_HAS_TAG",
    "HAS_SUBTAG",
    "HAS_TAG",
    "USES_TECH",
    "PRODUCES_ARTIFACT",
    "ARTIFACT_HAS_TAG",
}


def reviewed_taxonomy():
    return {
        "focuses": [{"id": "ai-quality", "label": "AI Quality"}],
        "domains": [
            {
                "id": "evaluation",
                "label": "Evaluation",
                "focus_id": "ai-quality",
            }
        ],
        "tags": [
            {
                "id": "evaluation-benchmarking",
                "label": "Evaluation / Benchmarking",
                "domain_id": "evaluation",
            }
        ],
    }


def _write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def old_graph_fixture(tmp_path):
    graph = tmp_path / "knowledge-graph"
    _write_csv(
        graph / "nodes.csv",
        ["id", "type", "name", "source_locator"],
        [
            {"id": "focus:ai", "type": "knowledge_focus", "name": "AI Quality"},
            {"id": "domain:evaluation", "type": "knowledge domain", "name": "Evaluation"},
            {
                "id": "tag:benchmark",
                "type": "knowledge-tag",
                "name": "Evaluation / Benchmarking",
            },
            {"id": "project:alpha", "type": "project", "name": "Alpha"},
            {"id": "technology:python", "type": "technology", "name": "Python"},
            {"id": "artifact:report", "type": "artifact", "name": "Report"},
            {"id": "tag:unmapped", "type": "KnowledgeTag", "name": "Novel Label"},
            {
                "id": "artifact:private",
                "type": "Artifact",
                "name": "Private",
                "source_locator": "/private/evidence.md:4",
            },
        ],
    )
    _write_csv(
        graph / "edges.csv",
        ["source", "target", "type", "evidence_path"],
        [
            {"source": "project:alpha", "target": "focus:ai", "type": "has focus"},
            {"source": "focus:ai", "target": "domain:evaluation", "type": "focus-has-tag"},
            {"source": "domain:evaluation", "target": "tag:benchmark", "type": "has_subtag"},
            {"source": "project:alpha", "target": "tag:benchmark", "type": "HAS_TAG"},
            {"source": "project:alpha", "target": "technology:python", "type": "uses tech"},
            {
                "source": "project:alpha",
                "target": "artifact:report",
                "type": "produces-artifact",
            },
            {
                "source": "artifact:report",
                "target": "tag:benchmark",
                "type": "artifact has tag",
            },
            {"source": "project:alpha", "target": "focus:ai", "type": "SHARES_FOCUS"},
            {"source": "project:alpha", "target": "tag:benchmark", "type": "SHARES_TAG"},
            {"source": "project:missing", "target": "focus:ai", "type": "HAS_FOCUS"},
            {"source": "project:alpha", "target": "", "type": "HAS_TAG"},
            {
                "source": "project:alpha",
                "target": "artifact:report",
                "type": "PRODUCES_ARTIFACT",
                "evidence_path": "C:\\private\\evidence.md",
            },
        ],
    )
    return graph.parent


def test_importer_reports_old_graph_without_creating_similarity_or_family_edges(
    tmp_path, old_graph_fixture
):
    files_before = {
        path.relative_to(old_graph_fixture): path.read_bytes()
        for path in old_graph_fixture.rglob("*")
        if path.is_file()
    }
    report = audit_llm_wiki_graph(old_graph_fixture, reviewed_taxonomy())

    assert report.accepted_node_types == APPROVED_NODE_TYPES
    assert "SHARES_FOCUS" in report.rejected_edge_types
    assert "SHARES_TAG" in report.rejected_edge_types
    assert report.output_edge_types == APPROVED_EDGE_TYPES
    assert "project-similarity" not in report.output_edge_types
    assert report.rejected_relation_counts == {"SHARES_FOCUS": 1, "SHARES_TAG": 1}
    assert report.rejection_counts == {
        "missing_endpoint": 1,
        "name_derived_relation": 2,
        "raw_locator": 2,
        "unknown_project_id": 1,
    }
    assert report.accepted_node_count == 6
    assert report.unmapped_node_count == 1
    assert report.accepted_edge_count == 7
    assert report.rejected_edge_count == 5
    assert report.suggested_taxonomy_aliases == (
        {"kind": "KnowledgeTag", "label": "Novel Label"},
    )
    assert {
        path.relative_to(old_graph_fixture): path.read_bytes()
        for path in old_graph_fixture.rglob("*")
        if path.is_file()
    } == files_before
    assert not list(tmp_path.rglob("*.json"))


def test_importer_json_is_stable_and_contains_only_audit_counts(old_graph_fixture):
    report = audit_llm_wiki_graph(old_graph_fixture, reviewed_taxonomy())

    first = report.to_json()
    second = audit_llm_wiki_graph(old_graph_fixture, reviewed_taxonomy()).to_json()

    assert first == second
    payload = json.loads(first)
    assert payload["mode"] == "audit-only"
    assert payload["counts"] == {
        "accepted_edges": 7,
        "accepted_nodes": 6,
        "rejected_edges": 5,
        "rejected_nodes": 1,
        "unmapped_edges": 0,
        "unmapped_nodes": 1,
    }
    assert payload["rejected_relation_counts"] == {"SHARES_FOCUS": 1, "SHARES_TAG": 1}
    assert "source" not in payload
    assert "taxonomy" not in payload
