import hashlib
import json

from atlas_worker.models import EvidenceRecord
from scripts.audit_public_atlas_catalog import (
    CatalogAudit,
    EXPECTED_PROJECT_IDS,
    audit_project_id_set,
    main,
    validate_evidence_owner,
)
from tests.worker.git_helpers import git, init_repo, write


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


def test_honest_insufficient_evidence_status_does_not_block_the_catalog():
    audit = CatalogAudit(
        project_ids=EXPECTED_PROJECT_IDS,
        missing_project_ids=(),
        unexpected_project_ids=(),
        review_required=(),
        insufficient_evidence=("sparse-project",),
        generic_decision_documents=(),
        invalid_evidence=(),
        unreferenced_svgs=(),
        similarity_edges=(),
        inferred_relations=(),
        map_diary_ownership_findings=(),
    )

    assert audit.ready


def test_git_evidence_must_reference_a_tracked_owner_file(tmp_path):
    project = init_repo(tmp_path / "project")
    source = project / "decision.txt"
    write(source, "tracked policy\n")
    evidence = EvidenceRecord(
        evidence_id="git-proof",
        project_id="alpha",
        label="Git proof",
        source_type="git",
        source_locator="decision.txt:1",
        observed_at="2026-08-31T00:00:00Z",
        privacy_class="public-safe",
        content_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
    )

    assert validate_evidence_owner(project, evidence) == ("git-evidence-untracked",)
    git(project, "add", "--", "decision.txt")
    assert validate_evidence_owner(project, evidence) == ()


def test_catalog_cli_sanitizes_unexpected_failures(monkeypatch, capsys, tmp_path):
    private_path = tmp_path / "private-source"

    def fail(_workspace):
        raise OSError(f"cannot read {private_path}")

    monkeypatch.setattr("scripts.audit_public_atlas_catalog.audit_public_catalog", fail)

    code = main(["--workspace", str(tmp_path)])

    output = capsys.readouterr().out
    assert code == 2
    assert json.loads(output) == {"error": "catalog-audit-failed", "ready": False}
    assert str(private_path) not in output
