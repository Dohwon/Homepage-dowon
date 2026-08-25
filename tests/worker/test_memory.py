import pytest
from pathlib import Path

from atlas_worker.evidence import merge_claims
from atlas_worker.memory import load_project_memory
from atlas_worker.memory_writer import update_project_memory
from atlas_worker.models import EvidenceClaim
from tests.worker.helpers import (
    make_decision_knowledge,
    make_project_ref,
    write_memory_markdown,
    write_project_profile,
)


def test_manual_profile_beats_curated_and_inferred_claims():
    claims = [
        EvidenceClaim("summary", "inferred", "session", 0.92, "s1"),
        EvidenceClaim("summary", "curated", "project_memory", 1.0, "m1"),
        EvidenceClaim("summary", "manual", "profile", 1.0, "p1"),
    ]

    assert merge_claims(claims).values["summary"] == "manual"


def test_claim_ties_use_confidence_then_evidence_id_deterministically():
    claims = [
        EvidenceClaim("summary", "lower", "source", 0.7, "z1"),
        EvidenceClaim("summary", "higher", "source", 0.9, "a1"),
        EvidenceClaim("summary", "stable", "source", 0.9, "z9"),
    ]

    knowledge = merge_claims(claims)

    assert knowledge.values["summary"] == "stable"
    assert knowledge.winners["summary"].evidence_id == "z9"


def test_unknown_claim_source_class_is_rejected():
    claims = [EvidenceClaim("summary", "unknown", "archive", 1.0, "a1")]

    with pytest.raises(ValueError, match="Unknown source_class: archive"):
        merge_claims(claims)


def test_missing_optional_memory_files_return_empty_sections(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path, publication="public")

    memory = load_project_memory(ref)

    assert memory.rollbacks == ()
    assert memory.decisions == ()
    assert memory.build_story == ()
    assert memory.events == ()
    assert not (tmp_path / "project_memory" / "rollbacks.md").exists()
    assert not (tmp_path / "manager_memory").exists()


def test_memory_reads_only_list_items_under_explicit_level_two_headings(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path)
    write_memory_markdown(
        tmp_path,
        "project_memory/history.md",
        "# Ignored title\n\n- ignored top-level list\n\n## Decisions\n\n- keep typed contracts\n- reject unknown classes\n\nProse is not memory.\n\n### Ignored child\n\n- ignored child list\n\n## Rollbacks\n\n- restored last public bundle\n",
    )
    write_memory_markdown(
        tmp_path,
        "manager_memory/legacy.md",
        "## Build Story\n\n- migrated from legacy memory\n",
    )

    memory = load_project_memory(ref)

    assert memory.decisions == ("keep typed contracts", "reject unknown classes")
    assert memory.rollbacks == ("restored last public bundle",)
    assert memory.build_story == ("migrated from legacy memory",)


def test_nested_memory_markdown_is_not_imported(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path)
    write_memory_markdown(
        tmp_path,
        "project_memory/history.md",
        "## Decisions\n\n- direct project memory\n",
    )
    write_memory_markdown(
        tmp_path,
        "project_memory/visuals/README.md",
        "## Decisions\n\n- nested project artifact\n",
    )
    write_memory_markdown(
        tmp_path,
        "manager_memory/legacy.md",
        "## Decisions\n\n- direct legacy memory\n",
    )
    write_memory_markdown(
        tmp_path,
        "manager_memory/archive/history.md",
        "## Decisions\n\n- nested legacy archive\n",
    )

    memory = load_project_memory(ref)

    assert memory.decisions == ("direct project memory", "direct legacy memory")


@pytest.mark.parametrize("fence", ("```", "~~~"))
def test_memory_ignores_bullets_inside_fenced_code_blocks(tmp_path, fence):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path)
    write_memory_markdown(
        tmp_path,
        "project_memory/history.md",
        f"## Decisions\n\n- kept decision\n\n{fence}text\n- example, not memory\n{fence}\n\n- final decision\n",
    )

    memory = load_project_memory(ref)

    assert memory.decisions == ("kept decision", "final decision")


@pytest.mark.parametrize(
    "value",
    (Path("/private/project"), "/private/project", r"C:\private\project", r"\\server\share\project"),
)
def test_merge_claims_rejects_standalone_absolute_path_values(value):
    claim = EvidenceClaim("summary", value, "source", 1.0, "local-claim", source_path="/local/evidence")

    with pytest.raises(ValueError, match="summary"):
        merge_claims([claim])


def test_merge_claims_preserves_prose_that_mentions_an_absolute_path():
    prose = "Read /private/project/README.md before the next deploy."
    claim = EvidenceClaim("summary", prose, "source", 1.0, "local-claim")

    assert merge_claims([claim]).values["summary"] == prose


def test_merge_claims_allows_absolute_path_metadata_outside_values():
    claim = EvidenceClaim(
        "summary",
        "Public summary",
        "source",
        1.0,
        "/local/evidence-id",
        source_path="/local/source.md",
    )

    knowledge = merge_claims([claim])

    assert knowledge.values == {"summary": "Public summary"}
    assert knowledge.winners["summary"].source_path == "/local/source.md"


def test_invalid_profile_raises_before_memory_is_consumed(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path, tags={})
    write_memory_markdown(tmp_path, "project_memory/history.md", "## Decisions\n\n- ignored\n")

    with pytest.raises(ValueError, match=r"tags\.domain"):
        load_project_memory(ref)


def test_writer_managed_event_round_trips_as_typed_history_under_owning_h2(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path)
    write_memory_markdown(
        tmp_path,
        "project_memory/decisions.md",
        "## Decisions\n\n- user-authored decision\n\n### Ordinary prose\n\n- not curated structure\n",
    )

    update_project_memory(ref, make_decision_knowledge(), dry_run=False)
    memory = load_project_memory(ref)

    assert memory.decisions == (
        "user-authored decision",
        "Use typed contracts for project memory",
    )
    assert len(memory.events) == 1
    event = memory.events[0]
    assert (
        event.event_id,
        event.date,
        event.title,
        event.context,
        event.decision,
        event.outcome,
        event.stage,
    ) == (
        "decision-001",
        "2026-08-24",
        "Decision",
        "source evidence",
        "Use typed contracts for project memory",
        "Confidence: 0.90",
        "decision",
    )
    assert not hasattr(event, "source_path")


@pytest.mark.parametrize(
    "managed_content",
    (
        "## Decisions\n\n<!-- atlas:event:broken -->\n### 2026-08-24 · Decision\n",
        "## Decisions\n\n<!-- /atlas:event:broken -->\n",
        (
            "## Decisions\n\n<!-- atlas:event:first -->\n"
            "### 2026-08-24 · Decision\n\n- 상황: evidence\n- 선택: choice\n- 결과: result\n"
            "<!-- /atlas:event:second -->\n"
        ),
    ),
)
def test_loader_rejects_malformed_or_unmatched_managed_event_markers(
    tmp_path, managed_content
):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path)
    write_memory_markdown(tmp_path, "project_memory/decisions.md", managed_content)

    with pytest.raises(ValueError, match="managed"):
        load_project_memory(ref)
