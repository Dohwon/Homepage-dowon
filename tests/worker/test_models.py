from pathlib import Path

import pytest

from atlas_worker.models import (
    GraphData,
    GraphEdge,
    ProjectRef,
    PublicProject,
    TagSet,
    validate_schema,
)


def test_finished_project_serializes_as_independent_project():
    ref = ProjectRef(
        project_id="260410-keyboard-piano",
        display_name="Keyboard Piano",
        root=Path("/workspace/projects/finish/260410_keyboard_piano"),
        relative_path="projects/finish/260410_keyboard_piano",
        lifecycle="finished",
        publication="public",
        aliases=(),
    )

    assert ref.to_dict()["lifecycle"] == "finished"
    assert ref.project_id != "finish"


def test_tag_limits_are_enforced():
    with pytest.raises(ValueError, match=r"domain supports 1\.\.2 values"):
        TagSet(
            domain=("AI", "Product", "Data"),
            problem=("Routing",),
            pattern=("Eval",),
            technology=(),
            outcome=("Tool",),
        )


def test_private_project_is_rejected_by_public_schema():
    candidate = {
        "id": "secret",
        "name": "Secret",
        "lifecycle": "active",
        "publication": "private",
        "summary": "Not publishable",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
        },
    }

    with pytest.raises(ValueError, match="publication"):
        validate_schema(candidate, "public-project")


def test_public_schema_rejects_local_root_with_field_path():
    candidate = {
        "id": "public-project",
        "name": "Public Project",
        "lifecycle": "active",
        "publication": "public",
        "summary": "Publishable project",
        "root": "/workspace/projects/public-project",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
        },
    }

    with pytest.raises(ValueError, match="root"):
        validate_schema(candidate, "public-project")


def test_public_project_serializes_tags_as_schema_arrays():
    project = PublicProject(
        project_id="alpha",
        display_name="Alpha",
        lifecycle="active",
        summary="Public project",
        tags=TagSet(
            domain=("AI",),
            problem=("Routing",),
            pattern=("Evaluation",),
            technology=("Python",),
            outcome=("Tool",),
        ),
    )

    payload = project.to_dict()

    validate_schema(payload, "public-project")
    assert payload["tags"]["domain"] == ["AI"]


def test_schema_error_includes_nested_unexpected_field_path():
    candidate = {
        "id": "alpha",
        "name": "Alpha",
        "lifecycle": "active",
        "publication": "public",
        "summary": "Public project",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
            "leaked": ["local value"],
        },
    }

    with pytest.raises(ValueError, match=r"tags\.leaked"):
        validate_schema(candidate, "public-project")


def test_schema_error_includes_nested_missing_required_field_path():
    candidate = {
        "id": "alpha",
        "name": "Alpha",
        "lifecycle": "active",
        "publication": "public",
        "summary": "Public project",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
        },
    }

    with pytest.raises(ValueError, match=r"tags\.outcome"):
        validate_schema(candidate, "public-project")


def test_project_neighbors_are_ranked_and_limited_to_five():
    graph = GraphData(
        nodes=(),
        edges=(
            GraphEdge("alpha", "project-6", "project-similarity", 1),
            GraphEdge("alpha", "project-5", "project-similarity", 2),
            GraphEdge("alpha", "project-4", "project-similarity", 3),
            GraphEdge("alpha", "project-3", "project-similarity", 4),
            GraphEdge("alpha", "project-2", "project-similarity", 5),
            GraphEdge("alpha", "project-1", "project-similarity", 6),
            GraphEdge("alpha", "topic-ai", "tag-membership", 100),
        ),
    )

    neighbors = graph.project_neighbors("alpha")

    assert [edge.target_id for edge in neighbors] == [
        "project-1",
        "project-2",
        "project-3",
        "project-4",
        "project-5",
    ]
