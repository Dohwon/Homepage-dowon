import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from atlas_worker.memory_writer import update_project_memory
from atlas_worker.models import EvidenceClaim, ProjectEvent, ProjectKnowledge
from atlas_worker.visuals import render_problem_solving_svg
from tests.worker.helpers import (
    make_challenge_events,
    make_decision_knowledge,
    make_project_ref,
    write_memory_markdown,
)


def test_writer_creates_only_sections_with_evidence(tmp_path):
    ref = make_project_ref(tmp_path)

    update = update_project_memory(ref, make_decision_knowledge())

    assert update.changed_files == ("project_memory/decisions.md",)
    assert (tmp_path / "project_memory" / "decisions.md").exists()
    assert not (tmp_path / "project_memory" / "build-story.md").exists()
    assert not (tmp_path / "project_memory" / "rollbacks.md").exists()


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


def test_writer_routes_selected_history_to_its_matching_memory_file(tmp_path):
    ref = make_project_ref(tmp_path)
    rollback = EvidenceClaim(
        "history", "Rollback restored the last verified bundle", "session", 0.95,
        "rollback-001", claim_type="rollback", event_date="2026-08-24",
    )
    revision = EvidenceClaim(
        "history", "Revision narrowed the extraction scope", "session", 0.90,
        "revision-001", claim_type="revision", event_date="2026-08-25",
    )
    knowledge = ProjectKnowledge(
        values={"rollback": rollback.value, "revision": revision.value},
        winners={"rollback": rollback, "revision": revision},
    )

    update = update_project_memory(ref, knowledge)

    assert update.changed_files == (
        "project_memory/build-story.md",
        "project_memory/rollbacks.md",
    )
    assert "Revision narrowed" in (tmp_path / "project_memory" / "build-story.md").read_text(encoding="utf-8")
    assert "Rollback restored" in (tmp_path / "project_memory" / "rollbacks.md").read_text(encoding="utf-8")


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
    assert not re.search(r"<[^>]*\\bon[a-z]+\\s*=", svg, re.I)
