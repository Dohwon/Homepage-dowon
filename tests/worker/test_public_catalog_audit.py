import hashlib

from atlas_worker.models import EvidenceRecord
from scripts.audit_public_atlas_catalog import (
    EXPECTED_PROJECT_IDS,
    audit_project_id_set,
    validate_evidence_owner,
)


def test_catalog_requires_the_exact_33_project_ids():
    result = audit_project_id_set(EXPECTED_PROJECT_IDS)

    assert len(result.project_ids) == 33
    assert "finish" not in result.project_ids
    assert result.missing_project_ids == ()
    assert result.unexpected_project_ids == ()


def test_catalog_rejects_count_only_substitution():
    substituted = (*EXPECTED_PROJECT_IDS[:-1], "wrong-project")

    result = audit_project_id_set(substituted)

    assert result.missing_project_ids == (EXPECTED_PROJECT_IDS[-1],)
    assert result.unexpected_project_ids == ("wrong-project",)


def test_evidence_must_point_to_original_nonblank_claim_line(tmp_path):
    project = tmp_path / "project"
    source = project / "src" / "owner.py"
    source.parent.mkdir(parents=True)
    source.write_text("header\nowned_claim = True\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = EvidenceRecord(
        evidence_id="owner-proof",
        project_id="alpha",
        label="Owner proof",
        source_type="code",
        source_locator="src/owner.py:2",
        observed_at="2026-08-31T00:00:00Z",
        privacy_class="public-safe",
        content_hash=digest,
    )

    assert validate_evidence_owner(project, evidence) == ()


def test_self_authored_atlas_restatement_is_not_owner_evidence(tmp_path):
    project = tmp_path / "project"
    source = project / "project_memory" / "project-atlas" / "sources" / "verified-findings.md"
    source.parent.mkdir(parents=True)
    source.write_text("restated claim\n", encoding="utf-8")
    evidence = EvidenceRecord(
        evidence_id="restatement",
        project_id="alpha",
        label="Restatement",
        source_type="project_memory",
        source_locator="project_memory/project-atlas/sources/verified-findings.md:1",
        observed_at="2026-08-31T00:00:00Z",
        privacy_class="public-safe",
        content_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
    )

    assert validate_evidence_owner(project, evidence) == (
        "self-authored-atlas-evidence",
    )
