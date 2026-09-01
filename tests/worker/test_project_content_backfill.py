from __future__ import annotations

from copy import deepcopy

from scripts.backfill_project_atlas_content import (
    build_system_map,
    promote_opening_to_orientation,
)


def _article() -> dict[str, object]:
    return {
        "project_id": "alpha",
        "title": "알파 프로젝트",
        "summary": "서로 다른 데이터 수명을 분리해 기록을 보존한 프로젝트다.",
        "readiness": "ready",
        "sections": [
            {
                "id": "background",
                "title": "기록이 사라지는 문제",
                "section_type": "planning",
                "body": "임시 경로는 하루 뒤 사라졌다.\n\n영구 기록에는 다른 정본이 필요했다.\n",
                "evidence_ids": ["ev-background"],
            },
            {
                "id": "split-lifetimes",
                "title": "임시 경로와 영구 기록의 수명 분리",
                "section_type": "decision",
                "body": "경로는 계산에만 쓰고 도로 snapshot만 저장했다.\n",
                "evidence_ids": ["ev-split"],
            },
            {
                "id": "server-boundary",
                "title": "외부 API를 서버 경계 뒤에 배치",
                "section_type": "decision",
                "body": "브라우저가 공급자 자격 증명을 소유하지 않게 했다.\n",
                "evidence_ids": ["ev-server"],
            },
            {
                "id": "implementation-flow",
                "title": "경로 계산에서 기록 확정까지",
                "section_type": "implementation",
                "body": "서버가 후보를 만들고 사용자가 기록을 확정한다.\n",
                "evidence_ids": ["ev-flow"],
            },
            {
                "id": "limitations",
                "title": "실기기 검증은 남아 있음",
                "section_type": "result",
                "body": "로컬 계약만 확인했고 기기 검증은 남아 있다.\n",
                "evidence_ids": ["ev-result"],
            },
        ],
        "decision_index": [],
    }


def test_promotes_project_specific_problem_to_unheaded_orientation():
    article = _article()

    changed = promote_opening_to_orientation(article)

    assert changed is True
    assert article["orientation"] == (
        "임시 경로는 하루 뒤 사라졌다.\n\n영구 기록에는 다른 정본이 필요했다.\n"
    )
    assert article["orientation_evidence_ids"] == ["ev-background"]
    assert [section["id"] for section in article["sections"]] == [
        "split-lifetimes",
        "server-boundary",
        "implementation-flow",
        "limitations",
    ]


def test_orientation_promotion_is_idempotent():
    article = _article()
    promote_opening_to_orientation(article)
    first_result = deepcopy(article)

    assert promote_opening_to_orientation(article) is False
    assert article == first_result


def test_indexed_opening_is_kept_as_a_decision_without_repeating_the_full_intro():
    article = _article()
    article["decision_index"] = [
        {
            "decision_id": "define-starting-scope",
            "section_id": "background",
            "status": "adopted",
            "evidence_ids": ["ev-background"],
        }
    ]

    promote_opening_to_orientation(article)

    assert article["orientation"] == "임시 경로는 하루 뒤 사라졌다."
    assert article["sections"][0]["id"] == "background"
    assert article["sections"][0]["section_type"] == "decision"
    assert article["sections"][0]["body"].startswith("임시 경로는 하루 뒤")


def test_system_map_uses_project_subjects_and_evidence():
    article = _article()
    promote_opening_to_orientation(article)

    system_map = build_system_map(article)

    assert system_map["map_type"] == "documentation-publishing"
    assert [node["id"] for node in system_map["nodes"]] == ["subject-00", "subject-01", "subject-02"]
    assert [node["label"] for node in system_map["nodes"]] == [
        "임시 경로와 영구 기록의 수명 분리",
        "외부 API를 서버 경계 뒤에 배치",
        "실기기 검증은 남아 있음",
    ]
    assert [flow["to"] for flow in system_map["flows"]] == ["subject-01", "subject-02"]
    assert system_map["decision_links"] == [
        {
            "node_ids": ["subject-00"],
            "section_id": "split-lifetimes",
            "label": "임시 경로와 영구 기록의 수명 분리",
        },
    ]
    assert system_map["evidence_ids"] == [
        "ev-split",
        "ev-server",
        "ev-result",
    ]


def test_system_map_size_follows_available_content_instead_of_a_fixed_template():
    article = _article()
    article["sections"] = article["sections"][:3]
    promote_opening_to_orientation(article)

    system_map = build_system_map(article)

    assert len(system_map["nodes"]) == 2
    assert len(system_map["flows"]) == 1
