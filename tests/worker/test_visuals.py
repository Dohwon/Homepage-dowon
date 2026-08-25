import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from atlas_worker.memory_writer import update_project_memory
from atlas_worker.models import EvidenceClaim, ProjectEvent
from atlas_worker.visuals import render_problem_solving_svg
from atlas_worker.backfill import extract_signal_claims
from atlas_worker.evidence import merge_claims
from tests.worker.helpers import (
    make_challenge_events,
    make_decision_knowledge,
    make_project_ref,
    make_session_event,
    write_memory_markdown,
)


def test_writer_creates_only_sections_with_evidence(tmp_path):
    ref = make_project_ref(tmp_path)

    update = update_project_memory(ref, make_decision_knowledge())

    assert update.changed_files == ("project_memory/decisions.md",)
    assert (tmp_path / "project_memory" / "decisions.md").exists()
    assert not (tmp_path / "project_memory" / "build-story.md").exists()
    assert not (tmp_path / "project_memory" / "rollbacks.md").exists()


def test_writer_omits_visual_until_a_decision_path_has_multiple_stages(tmp_path):
    ref = make_project_ref(tmp_path)

    update_project_memory(ref, make_decision_knowledge(), dry_run=False)

    assert not (tmp_path / "project_memory" / "visuals" / "problem-solving.svg").exists()


def test_writer_combines_legacy_curated_event_with_reviewed_event_for_local_visual(
    tmp_path,
):
    ref = make_project_ref(tmp_path)
    write_memory_markdown(
        tmp_path,
        "manager_memory/history.md",
        "## Decisions\n\n"
        "<!-- atlas:event:legacy-decision -->\n"
        "### 2026-08-23 · Decision\n\n"
        "- 상황: reviewed legacy evidence\n"
        "- 선택: Keep the typed path\n"
        "- 결과: Decision retained\n"
        "<!-- /atlas:event:legacy-decision -->\n",
    )
    rollback = EvidenceClaim(
        field="history:rollback-001",
        value="Return to the reviewed path",
        source_class="session",
        confidence=0.85,
        evidence_id="rollback-001",
        claim_type="rollback",
        event_date="2026-08-24T10:00:00Z",
        selected=True,
    )

    update = update_project_memory(ref, merge_claims((rollback,)))

    assert update.changed_files == (
        "project_memory/rollbacks.md",
        "project_memory/visuals/problem-solving.svg",
    )


def test_writer_preserves_user_text_and_replaces_a_matching_managed_event(tmp_path):
    ref = make_project_ref(tmp_path)
    path = write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "# Decisions\n\nAuthor note stays untouched.\n\n"
        "<!-- atlas:event:decision-001 -->\n### old\n\n- stale\n"
        "<!-- /atlas:event:decision-001 -->\n\nClosing note stays untouched.\n",
    )

    update_project_memory(ref, make_decision_knowledge(value="Use deterministic managed blocks"))

    content = path.read_text(encoding="utf-8")
    assert "# Decisions\n\nAuthor note stays untouched.\n\n" in content
    assert "\n\nClosing note stays untouched.\n" in content
    assert "### old" not in content
    assert content.count("<!-- atlas:event:decision-001 -->") == 1
    assert "Use deterministic managed blocks" in content


def test_writer_inserts_new_events_inside_the_target_h2_before_references(tmp_path):
    ref = make_project_ref(tmp_path)
    path = write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "# Project notes\n\n## Decisions\n\nUser decision text.\n\n"
        "## References\n\nUser reference text.\n",
    )

    update_project_memory(ref, make_decision_knowledge())

    content = path.read_text(encoding="utf-8")
    assert content.index("<!-- atlas:event:decision-001 -->") < content.index("## References")
    assert "## References\n\nUser reference text.\n" in content


def test_writer_rejects_duplicate_target_h2_without_overwriting_user_text(tmp_path):
    ref = make_project_ref(tmp_path)
    path = write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "## Decisions\n\nFirst section.\n\n## Decisions\n\nSecond section.\n",
    )
    original = path.read_bytes()

    with pytest.raises(ValueError, match="duplicate target headings"):
        update_project_memory(ref, make_decision_knowledge())

    assert path.read_bytes() == original


def test_writer_rejects_malformed_markers_without_overwriting_user_text(tmp_path):
    ref = make_project_ref(tmp_path)
    path = write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "# Decisions\n\n<!-- atlas:event:decision-001 -->\nUnclosed user text.\n",
    )
    original = path.read_bytes()

    with pytest.raises(ValueError, match="managed markers"):
        update_project_memory(ref, make_decision_knowledge())

    assert path.read_bytes() == original


def test_writer_rejects_duplicate_managed_markers_without_overwriting_user_text(tmp_path):
    ref = make_project_ref(tmp_path)
    path = write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "<!-- atlas:event:decision-001 -->\nFirst block.\n"
        "<!-- /atlas:event:decision-001 -->\n"
        "<!-- atlas:event:decision-001 -->\nSecond block.\n"
        "<!-- /atlas:event:decision-001 -->\n",
    )
    original = path.read_bytes()

    with pytest.raises(ValueError, match="managed markers"):
        update_project_memory(ref, make_decision_knowledge())

    assert path.read_bytes() == original


def test_writer_dry_run_reports_changes_without_creating_directories(tmp_path):
    ref = make_project_ref(tmp_path)

    update = update_project_memory(ref, make_decision_knowledge(), dry_run=True)

    assert update.changed_files == ("project_memory/decisions.md",)
    assert not (tmp_path / "project_memory").exists()


def test_writer_is_idempotent_and_ignores_review_only_claims(tmp_path):
    ref = make_project_ref(tmp_path)
    reviewed = make_decision_knowledge(confidence=0.75)

    assert update_project_memory(ref, reviewed).changed_files == ()
    first = update_project_memory(ref, make_decision_knowledge())
    content = (tmp_path / "project_memory" / "decisions.md").read_bytes()
    second = update_project_memory(ref, make_decision_knowledge())

    assert first.changed_files == ("project_memory/decisions.md",)
    assert second.changed_files == ()
    assert (tmp_path / "project_memory" / "decisions.md").read_bytes() == content


def test_writer_accepts_explicitly_selected_review_claims_only(tmp_path):
    ref = make_project_ref(tmp_path)

    assert update_project_memory(ref, make_decision_knowledge(confidence=0.75)).changed_files == ()
    update = update_project_memory(ref, make_decision_knowledge(confidence=0.75, selected=True))

    assert update.changed_files == ("project_memory/decisions.md",)


def test_writer_preserves_multiple_backfill_events_through_merge_and_routing(tmp_path):
    ref = make_project_ref(tmp_path)
    claims = extract_signal_claims(
        (
            make_session_event("rollback", session_id="rollback", line_number=1),
            make_session_event("이 아키텍처를 채택하기로 결정", session_id="decision", line_number=2),
            make_session_event("다시 수정해", session_id="revision", line_number=3),
            make_session_event("수정 완료", session_id="revision", role="assistant", line_number=4),
        )
    )

    update = update_project_memory(ref, merge_claims(claims))

    assert update.changed_files == (
        "project_memory/build-story.md",
        "project_memory/decisions.md",
        "project_memory/rollbacks.md",
        "project_memory/visuals/problem-solving.svg",
    )
    assert "revision confirmed" in (tmp_path / "project_memory" / "build-story.md").read_text(encoding="utf-8")
    assert "architecture decision recorded" in (tmp_path / "project_memory" / "decisions.md").read_text(encoding="utf-8")
    assert "rollback requested" in (tmp_path / "project_memory" / "rollbacks.md").read_text(encoding="utf-8")


def test_svg_contains_accessible_metadata_and_ordered_stable_nodes():
    svg = render_problem_solving_svg(
        make_project_ref(Path("/workspace/atlas"), project_id="atlas"),
        make_challenge_events(),
    )

    assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    assert '<title id="title">' in svg
    assert '<desc id="desc">' in svg
    assert 'role="img" aria-labelledby="title desc"' in svg
    assert 'viewBox="0 0 1200 640"' in svg
    assert [svg.index(f'id="node-{stage}"') for stage in ("constraint", "attempt", "revision", "decision", "result")] == sorted(
        svg.index(f'id="node-{stage}"') for stage in ("constraint", "attempt", "revision", "decision", "result")
    )
    assert "--atlas-bg" in svg
    assert "prefers-color-scheme: dark" in svg
    assert "<script" not in svg.lower()
    assert ET.fromstring(svg).tag == "{http://www.w3.org/2000/svg}svg"


def test_svg_escapes_dynamic_content_and_excludes_active_or_external_markup():
    ref = make_project_ref(Path("/private/project"), project_id="atlas<script>")
    event = ProjectEvent(
        "constraint-001",
        "2026-08-24",
        "<script>alert(1)</script>",
        '" onload="alert(1)" /private/project',
        "<foreignObject>unsafe</foreignObject>",
        "https://example.test/external.svg",
        "constraint",
    )

    svg = render_problem_solving_svg(ref, (event,))

    ET.fromstring(svg)
    assert "&lt;script&gt;" in svg
    assert "<script" not in svg.lower()
    assert "<foreignobject" not in svg.lower()
    assert "href=" not in svg.lower()
    assert "/private/project" not in svg
    assert re.search(r"<[^>]*\bon[a-z]+\s*=", '<rect onload="alert(1)" />', re.I)
    assert not re.search(r"<[^>]*\bon[a-z]+\s*=", svg, re.I)


def test_svg_redacts_delimiter_adjacent_and_root_paths_but_preserves_urls():
    ref = make_project_ref(Path("/private/project"), project_id="atlas")
    events = (
        ProjectEvent(
            "constraint-001", "2026-08-24", "Constraint", "root:/home/user/private",
            "root /", "https://ex.test/a", "constraint",
        ),
        ProjectEvent(
            "attempt-001", "2026-08-24", "Attempt", r"root:C:\\private\\project",
            "Keep local paths private", "Result", "attempt",
        ),
    )

    text_content = " ".join(ET.fromstring(render_problem_solving_svg(ref, events)).itertext())

    assert "/home/user/private" not in text_content
    assert "root /" not in text_content
    assert r"C:\\private\\project" not in text_content
    assert "https://ex.test/a" in text_content
