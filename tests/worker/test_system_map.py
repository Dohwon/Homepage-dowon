from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atlas_worker.models import ArticleSection, EvidenceRecord, ProjectArticle, validate_schema
from atlas_worker.privacy import PrivacyGate
from atlas_worker.system_map import load_project_system_map, render_system_map_svg
from tests.worker.helpers import make_project_ref


def _gate() -> PrivacyGate:
    return PrivacyGate(alias_key=b"system-map-test")


def _article() -> ProjectArticle:
    return ProjectArticle(
        project_id="alpha",
        title="경로 저장 개선",
        summary="임시 경로와 영구 기록을 분리했다.",
        readiness="ready",
        orientation="경로 제공자의 보존 기간이 방문 기록보다 짧았다.",
        orientation_evidence_ids=("ev-map",),
        sections=(
            ArticleSection(
                section_id="retention",
                title="저장 수명 분리",
                section_type="decision",
                body="영구 도로 정보만 방문 기록에 남긴다.",
                evidence_ids=("ev-map",),
            ),
        ),
    )


def _evidence() -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord(
            evidence_id="ev-map",
            project_id="alpha",
            label="Verified design",
            source_type="spec",
            source_locator="/private/design.md:4",
            observed_at="2026-08-31T10:00:00Z",
            privacy_class="private",
            content_hash="a" * 64,
            claim_role="supports",
        ),
    )


def _map() -> dict[str, object]:
    return {
        "project_id": "alpha",
        "title": "경로 데이터 수명 지도",
        "summary": "탐색용 경로가 영구 방문 기록으로 바뀌는 경계를 보여 준다.",
        "nodes": [
            {"id": "route-provider", "label": "경로 제공자", "kind": "service", "description": "하루 동안 탐색 경로를 제공한다."},
            {"id": "road-snapshot", "label": "도로 스냅샷", "kind": "state", "description": "영구 보존할 도로 geometry다."},
            {"id": "visit-record", "label": "방문 기록", "kind": "output", "description": "사용자가 다시 보는 기록이다."},
        ],
        "flows": [
            {"id": "resolve-road", "from": "route-provider", "to": "road-snapshot", "label": "도로 식별"},
            {"id": "store-visit", "from": "road-snapshot", "to": "visit-record", "label": "영구 저장"},
        ],
        "decision_links": [
            {"node_ids": ["route-provider", "road-snapshot"], "section_id": "retention", "label": "임시 입력과 영구 정본 분리"},
        ],
        "evidence_ids": ["ev-map"],
    }


def _write_map(root: Path, value: dict[str, object]) -> None:
    directory = root / "project_memory" / "project-atlas"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "system-map.yaml").write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_loads_referenced_system_map_and_projects_deterministic_public_assets(tmp_path):
    _write_map(tmp_path, _map())

    system_map = load_project_system_map(make_project_ref(tmp_path), _article(), _evidence(), _gate())

    assert system_map is not None
    assert system_map.project_id == "alpha"
    assert [node.node_id for node in system_map.nodes] == ["route-provider", "road-snapshot", "visit-record"]
    assert system_map.decision_links[0].section_id == "retention"
    public = system_map.to_public_dict()
    validate_schema(public, "public-system-map")
    assert "/private" not in str(public)
    first = render_system_map_svg(system_map)
    second = render_system_map_svg(system_map)
    assert first == second
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in first
    assert "경로 데이터 수명 지도" in first
    assert "경로 제공자" in first
    assert "영구 저장" in first
    assert 'marker-end="url(#system-map-arrow)"' in first
    assert first.index('data-node="route-provider"') < first.index('data-node="road-snapshot"')
    assert first.index('data-node="road-snapshot"') < first.index('data-node="visit-record"')


def test_svg_wraps_long_project_context_instead_of_clipping_it(tmp_path):
    value = _map()
    value["summary"] = (
        "처음 보는 사람도 프로젝트의 출발 문제와 구현 경계를 읽을 수 있도록 "
        "긴 설명을 여러 줄로 나누어 표시한다."
    )
    _write_map(tmp_path, value)
    system_map = load_project_system_map(
        make_project_ref(tmp_path), _article(), _evidence(), _gate()
    )

    svg = render_system_map_svg(system_map)

    assert svg.count("<tspan") >= 2
    assert "긴 설명을 여러 줄로" in svg


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value["nodes"].append(dict(value["nodes"][0])), "duplicate"),
        (lambda value: value["flows"][0].update({"to": "missing"}), "node"),
        (lambda value: value["decision_links"][0].update({"section_id": "missing"}), "section"),
        (lambda value: value.update({"evidence_ids": ["missing"]}), "evidence"),
    ),
)
def test_rejects_broken_system_map_references(tmp_path, mutation, message):
    value = _map()
    mutation(value)
    _write_map(tmp_path, value)

    with pytest.raises(ValueError, match=message):
        load_project_system_map(make_project_ref(tmp_path), _article(), _evidence(), _gate())


def test_missing_system_map_returns_none(tmp_path):
    assert load_project_system_map(make_project_ref(tmp_path), _article(), _evidence(), _gate()) is None
