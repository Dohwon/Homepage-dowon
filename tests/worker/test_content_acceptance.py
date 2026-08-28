from __future__ import annotations

from pathlib import Path

import pytest

from atlas_worker.article import load_project_article, load_project_evidence
from atlas_worker.config import DiscoveryConfig
from atlas_worker.discovery import discover_projects
from atlas_worker.fs_safety import read_confined_text
from atlas_worker.models import DecisionIndexEntry
from atlas_worker.source_manifest import resolve_git_owner
from tests.worker.helpers import (
    StaticGitRunner,
    atlas_content_gate,
    audit_ref,
    project_content_fixture_ref,
    write_project_profile,
)


@pytest.fixture
def map_diary_v2_ref():
    return project_content_fixture_ref(
        "map-diary-v2",
        project_id="260802-map-diary-v2",
        display_name="지도 기록 다이어리 v2",
    )


@pytest.fixture
def insufficient_ref():
    return project_content_fixture_ref(
        "insufficient",
        project_id="insufficient",
        display_name="Insufficient",
    )


def test_map_diary_v2_article_preserves_verified_data_lifecycle_decision(map_diary_v2_ref):
    article = load_project_article(map_diary_v2_ref, atlas_content_gate())
    evidence = load_project_evidence(map_diary_v2_ref, atlas_content_gate())
    audit = audit_ref(map_diary_v2_ref)

    assert article is not None
    assert article.project_id == "260802-map-diary-v2"
    assert article.title == "지도 기록 다이어리 v2"
    assert len(article.sections) == 1
    assert article.sections[0].section_id == "retention"
    assert article.sections[0].section_type == "decision"
    assert article.sections[0].title == "TMAP 데이터 장기 저장 제한 해결"
    assert article.sections[0].body == (
        "TMAP 데이터는 24시간을 넘겨 보관할 수 없어서 예상 경로 계산용 세션 입력으로만 사용했다.\n\n"
        "영구 방문 기록에는 VWorld Feature ID와 geometry snapshot만 남겨 같은 도로 객체를 다시 확인할 수 있게 했다.\n\n"
        "영구 변환이 끝난 뒤에는 TMAP 원본 경로를 버리고 방문 기록에 남기지 않도록 저장 계약을 분리했다.\n"
    )
    assert article.sections[0].evidence_ids == (
        "v2-tmap-retention-spec",
        "v2-vworld-feature-spec",
        "v2-source-discard-spec",
    )
    assert article.decision_index == (
        DecisionIndexEntry(
            "tmap-data-retention-boundary",
            "retention",
            "adopted",
            (
                "v2-tmap-retention-spec",
                "v2-vworld-feature-spec",
                "v2-source-discard-spec",
            ),
        ),
    )
    assert audit.readiness == "ready"
    assert [(item.evidence_id, item.source_locator) for item in evidence] == [
        (
            "v2-tmap-retention-spec",
            "project_memory/project-atlas/sources/verified-v2-design.md:3",
        ),
        (
            "v2-vworld-feature-spec",
            "project_memory/project-atlas/sources/verified-v2-design.md:5",
        ),
        (
            "v2-source-discard-spec",
            "project_memory/project-atlas/sources/verified-v2-design.md:7",
        ),
    ]
    expected_source_lines = (
        "근거 1: TMAP 데이터는 24시간을 넘겨 저장하지 않는다.",
        "근거 2: 영구 방문 기록에는 VWorld Feature ID와 geometry snapshot을 저장한다.",
        "근거 3: 영구 변환 뒤 TMAP 원본 경로는 폐기하고 방문 기록에 남기지 않는다.",
    )
    for record, expected_line in zip(evidence, expected_source_lines, strict=True):
        relative_path, separator, line_text = record.source_locator.rpartition(":")
        assert separator and line_text.isdecimal()
        source = read_confined_text(
            map_diary_v2_ref.root / relative_path,
            map_diary_v2_ref.root,
            atlas_content_gate(),
        )
        assert source.splitlines()[int(line_text) - 1] == expected_line
    assert all("source_locator" not in item for item in (record.to_public_dict() for record in evidence))
    diagram = article.sections[0].diagrams[0]
    assert diagram.diagram_id == "tmap-vworld-lifecycle"
    assert "TMAP 세션 입력 수명" in diagram.svg
    assert "VWorld 영구 기록 수명" in diagram.svg
    assert "문제 -> 결정 -> 결과" not in diagram.svg


def test_worktree_v4_evidence_does_not_create_an_independent_project(tmp_path):
    workspace = tmp_path / "workspace"
    v3_root = workspace / "projects" / "260802-map-diary-v3"
    worktree = v3_root / ".worktrees" / "v4-auto-drive-detection"
    worktree.mkdir(parents=True)
    write_project_profile(
        v3_root,
        id="260802-map-diary-v3",
        name="지도 기록 다이어리 v3",
        publication="public",
    )

    report = discover_projects(DiscoveryConfig.for_workspace(workspace))
    ids = {project.project_id for project in report.projects}

    assert "260802-map-diary-v4" not in ids
    assert "260802-map-diary-v3" in ids
    assert resolve_git_owner(
        worktree,
        report.projects,
        StaticGitRunner(
            common_dirs={
                Path(v3_root): "/git/map-diary-v3",
                Path(worktree): "/git/map-diary-v3",
            }
        ),
    ) == "260802-map-diary-v3"


def test_insufficient_project_has_no_manufactured_decisions(insufficient_ref):
    audit = audit_ref(insufficient_ref)

    assert audit.readiness == "insufficient-evidence"
    assert load_project_article(insufficient_ref, atlas_content_gate()) is None
