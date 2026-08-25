import pytest

from atlas_worker.evidence import merge_claims
from atlas_worker.memory import load_project_memory
from atlas_worker.models import EvidenceClaim
from tests.worker.helpers import make_project_ref, write_memory_markdown, write_project_profile


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


def test_invalid_profile_raises_before_memory_is_consumed(tmp_path):
    ref = make_project_ref(tmp_path)
    write_project_profile(tmp_path, tags={})
    write_memory_markdown(tmp_path, "project_memory/history.md", "## Decisions\n\n- ignored\n")

    with pytest.raises(ValueError, match=r"tags\.domain"):
        load_project_memory(ref)
