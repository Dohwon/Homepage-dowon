from __future__ import annotations

from pathlib import Path

import pytest

from atlas_worker.article import load_project_article, load_project_evidence
from atlas_worker.config import DiscoveryConfig
from atlas_worker.discovery import discover_projects
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
    assert article.sections[0].title == "TMAP 데이터 장기 저장 제한 해결"
    assert article.sections[0].evidence_ids == (
        "v2-tmap-retention-spec",
        "v2-vworld-feature-spec",
        "v2-source-discard-spec",
    )
    body = "\n".join(section.body for section in article.sections)
    assert "24시간" in body
    assert "세션 입력" in body
    assert "VWorld Feature ID" in body
    assert "geometry snapshot" in body
    assert "TMAP 원본 경로" in body
    assert audit.readiness == "ready"
    assert [item.evidence_id for item in evidence] == [
        "v2-tmap-retention-spec",
        "v2-vworld-feature-spec",
        "v2-source-discard-spec",
    ]
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
