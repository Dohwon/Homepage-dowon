from pathlib import Path

import pytest

from atlas_worker.models import (
    ArticleSection,
    DecisionIndexEntry,
    DiagramRef,
    EvidenceRecord,
    GraphData,
    GraphEdge,
    GraphNode,
    ProjectArticle,
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
            GraphEdge("project:alpha", "project:project-6", "project-similarity", 1),
            GraphEdge("project:alpha", "project:project-5", "project-similarity", 2),
            GraphEdge("project:alpha", "project:project-4", "project-similarity", 3),
            GraphEdge("project:alpha", "project:project-3", "project-similarity", 4),
            GraphEdge("project:alpha", "project:project-2", "project-similarity", 5),
            GraphEdge("project:alpha", "project:project-1", "project-similarity", 6),
            GraphEdge("project:alpha", "domain:ai", "tag-membership", 100),
        ),
    )

    neighbors = graph.project_neighbors("alpha")

    assert [edge.target_id for edge in neighbors] == [
        "project:project-1",
        "project:project-2",
        "project:project-3",
        "project:project-4",
        "project:project-5",
    ]


def test_graph_data_rejects_unknown_node_and_edge_kinds():
    with pytest.raises(ValueError, match="Unknown graph node kind: unknown"):
        GraphData(nodes=(GraphNode("unknown:1", "Unknown", "unknown"),), edges=())

    with pytest.raises(ValueError, match="Unknown graph edge kind: unknown"):
        GraphData(nodes=(), edges=(GraphEdge("project:alpha", "project:beta", "unknown", 1),))


def test_project_article_omits_absent_optional_sections_from_public_projection():
    article = ProjectArticle(
        project_id="alpha",
        title="라우팅 실패 분류 개선",
        summary="운영 로그에서 실패 유형을 재현 가능하게 분류했다.",
        sections=(
            ArticleSection(
                section_id="failure-taxonomy",
                title="실패 유형 분리",
                section_type="planning",
                body="같은 실패처럼 보이던 사례를 입력, 라우팅, 실행 단계로 나눴다.",
                evidence_ids=("ev-spec",),
            ),
        ),
        readiness="ready",
    )

    payload = article.to_public_dict()

    assert payload["sections"][0]["id"] == "failure-taxonomy"
    assert "prior_context" not in payload
    assert "diagrams" not in payload["sections"][0]
    validate_schema(payload, "public-article")


def test_public_article_schema_rejects_private_evidence_locator():
    payload = {
        "project_id": "alpha",
        "title": "라우팅 개선",
        "summary": "검증된 요약",
        "readiness": "ready",
        "sections": [
            {
                "id": "routing",
                "title": "라우팅 개선",
                "section_type": "decision",
                "body": "본문",
                "evidence_ids": ["ev-1"],
                "source_locator": "/home/dowon/private",
            }
        ],
    }

    with pytest.raises(ValueError, match="source_locator"):
        validate_schema(payload, "public-article")


def test_public_article_diagrams_expose_only_public_metadata():
    article = ProjectArticle(
        project_id="alpha",
        title="라우팅 개선",
        summary="검증된 요약",
        sections=(
            ArticleSection(
                section_id="routing",
                title="라우팅 개선",
                section_type="decision",
                body="본문",
                evidence_ids=("ev-1",),
                diagrams=(
                    DiagramRef(
                        diagram_id="routing-flow",
                        source_path="project_memory/project-atlas/visuals/routing-flow.svg",
                        caption="라우팅 흐름",
                        alt="입력부터 실행까지의 라우팅 흐름",
                        svg="<svg><title>private source</title></svg>",
                    ),
                ),
            ),
        ),
        readiness="ready",
    )

    payload = article.to_public_dict()

    assert payload["sections"][0]["diagrams"] == [
        {"id": "routing-flow", "caption": "라우팅 흐름", "alt": "입력부터 실행까지의 라우팅 흐름"}
    ]
    validate_schema(payload, "public-article")


def test_evidence_record_projects_only_public_fields_and_validates_preapproved_url():
    evidence = EvidenceRecord(
        evidence_id="ev-spec",
        project_id="alpha",
        label="라우팅 사양",
        source_type="spec",
        source_locator="project_memory/project-atlas/evidence.yaml:12",
        observed_at="2026-08-27T09:00:00+09:00",
        privacy_class="private",
        content_hash="a" * 64,
        url="https://example.com/projects/alpha/spec",
    )

    payload = evidence.to_public_dict()

    assert payload == {
        "id": "ev-spec",
        "label": "라우팅 사양",
        "source_type": "spec",
        "observed_at": "2026-08-27T09:00:00+09:00",
        "url": "https://example.com/projects/alpha/spec",
    }
    validate_schema([payload], "public-evidence")


def test_public_evidence_schema_rejects_invalid_url():
    payload = [
        {
            "id": "ev-spec",
            "label": "라우팅 사양",
            "source_type": "spec",
            "observed_at": "2026-08-27T09:00:00+09:00",
            "url": "not a uri",
        }
    ]

    with pytest.raises(ValueError, match="url"):
        validate_schema(payload, "public-evidence")


def test_project_article_projects_decision_evidence_ids_as_public_lists():
    article = ProjectArticle(
        project_id="alpha",
        title="라우팅 개선",
        summary="검증된 요약",
        sections=(
            ArticleSection(
                section_id="routing",
                title="라우팅 개선",
                section_type="decision",
                body="본문",
                evidence_ids=("ev-spec",),
            ),
        ),
        readiness="ready",
        decision_index=(
            DecisionIndexEntry(
                decision_id="routing-choice",
                section_id="routing",
                status="adopted",
                evidence_ids=("ev-spec",),
            ),
        ),
    )

    payload = article.to_public_dict()

    assert payload["decision_index"] == [
        {
            "decision_id": "routing-choice",
            "section_id": "routing",
            "status": "adopted",
            "evidence_ids": ["ev-spec"],
        }
    ]
    validate_schema(payload, "public-article")


@pytest.mark.parametrize(
    ("schema_name", "payload", "field_name"),
    (
        (
            "project-article",
            {
                "project_id": "Alpha_1",
                "title": "라우팅 개선",
                "summary": "검증된 요약",
                "readiness": "ready",
                "sections": [],
            },
            "project_id",
        ),
        (
            "public-article",
            {
                "project_id": "alpha",
                "title": "라우팅 개선",
                "summary": "검증된 요약",
                "readiness": "ready",
                "sections": [
                    {
                        "id": "routing_section",
                        "title": "라우팅 개선",
                        "section_type": "decision",
                        "body": "본문",
                        "evidence_ids": ["ev-spec"],
                    }
                ],
            },
            "sections.0.id",
        ),
    ),
)
def test_article_schemas_reject_malformed_stable_ids(schema_name, payload, field_name):
    with pytest.raises(ValueError, match=field_name):
        validate_schema(payload, schema_name)


def test_project_article_schema_accepts_curated_article_shape():
    payload = {
        "project_id": "alpha",
        "title": "라우팅 개선",
        "summary": "검증된 요약",
        "readiness": "ready",
        "prior_context": "이전 검토에서 남은 제약을 해결했다.",
        "sections": [
            {
                "id": "routing",
                "title": "라우팅 개선",
                "section_type": "decision",
                "body": "본문",
                "evidence_ids": ["ev-spec"],
                "diagrams": [{"id": "routing-flow", "caption": "흐름", "alt": "라우팅 흐름"}],
            }
        ],
        "decision_index": [
            {
                "decision_id": "routing-choice",
                "section_id": "routing",
                "status": "adopted",
                "evidence_ids": ["ev-spec"],
            }
        ],
    }

    validate_schema(payload, "project-article")


@pytest.mark.parametrize(
    ("schema_name", "payload", "field_name"),
    (
        (
            "public-timeline",
            [
                {
                    "event_id": "routing-1",
                    "date": "2026-02-30",
                    "title": "라우팅 변경",
                    "context": "운영 로그",
                    "decision": "규칙 분리",
                    "outcome": "검증 완료",
                    "stage": "validation",
                }
            ],
            "0.date",
        ),
        (
            "public-timeline",
            [
                {
                    "event_id": "routing-1",
                    "date": "20260827",
                    "title": "라우팅 변경",
                    "context": "운영 로그",
                    "decision": "규칙 분리",
                    "outcome": "검증 완료",
                    "stage": "validation",
                }
            ],
            "0.date",
        ),
        (
            "public-evidence",
            [
                {
                    "id": "ev-spec",
                    "label": "라우팅 사양",
                    "source_type": "spec",
                    "observed_at": "2026-02-30T25:61:00+09:00",
                }
            ],
            "0.observed_at",
        ),
        (
            "public-evidence",
            [
                {
                    "id": "ev-spec",
                    "label": "라우팅 사양",
                    "source_type": "spec",
                    "observed_at": "2026-08-27T09:00:00",
                }
            ],
            "0.observed_at",
        ),
    ),
)
def test_public_schemas_reject_invalid_dates(schema_name, payload, field_name):
    with pytest.raises(ValueError, match=field_name):
        validate_schema(payload, schema_name)


def test_public_timeline_schema_accepts_project_event_projection():
    payload = [
        {
            "event_id": "routing-1",
            "date": "2026-08-27",
            "title": "라우팅 변경",
            "context": "운영 로그",
            "decision": "규칙 분리",
            "outcome": "검증 완료",
            "stage": "validation",
        }
    ]

    validate_schema(payload, "public-timeline")


@pytest.mark.parametrize("private_field", ("source_locator", "content_hash", "privacy_class"))
def test_public_evidence_schema_rejects_private_provenance_fields(private_field):
    payload = [
        {
            "id": "ev-spec",
            "label": "라우팅 사양",
            "source_type": "spec",
            "observed_at": "2026-08-27T09:00:00+09:00",
            private_field: "private-value",
        }
    ]

    with pytest.raises(ValueError, match=private_field):
        validate_schema(payload, "public-evidence")
