from pathlib import Path

import pytest

from atlas_worker.models import ProjectRef, PublicProject, TagSet, validate_schema


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
