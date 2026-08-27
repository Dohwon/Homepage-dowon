from pathlib import Path

from atlas_worker.content_audit import ArticleValidationFinding, audit_project_content
from atlas_worker.models import (
    ArticleSection,
    EvidenceRecord,
    ProjectArticle,
    ProjectRef,
    SessionMapping,
)
from atlas_worker.source_manifest import SourceManifest


def _project() -> ProjectRef:
    return ProjectRef(
        project_id="alpha",
        display_name="Alpha",
        root=Path("/private/projects/alpha"),
        relative_path="projects/alpha",
        lifecycle="active",
        publication="public",
        aliases=(),
    )


def _manifest() -> SourceManifest:
    return SourceManifest(
        project_id="alpha",
        files=(),
        predecessor_ids=(),
        git_head_fingerprint="head",
        git_common_dir_fingerprint="common",
    )


def _article(*evidence_ids: str, sections: int = 1) -> ProjectArticle:
    return ProjectArticle(
        project_id="alpha",
        title="Evidence-backed decision",
        summary="Curated result",
        readiness="ready",
        sections=tuple(
            ArticleSection(
                section_id=f"section-{index}",
                title=f"Section {index}",
                section_type="decision",
                body="Curated body",
                evidence_ids=evidence_ids,
            )
            for index in range(sections)
        ),
    )


def _evidence(evidence_id: str, *, role: str = "supports") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        project_id="alpha",
        label="Curated evidence",
        source_type="session",
        source_locator="/private/sessions/alpha.jsonl:42",
        observed_at="2026-08-27T10:00:00Z",
        privacy_class="private",
        content_hash="a" * 64,
        claim_role=role,
    )


def test_missing_article_yields_insufficient_evidence_without_generic_sections():
    audit = audit_project_content(_project(), _manifest(), None, (), ())

    assert audit.readiness == "insufficient-evidence"
    assert "generic-section" not in audit.findings


def test_missing_referenced_evidence_is_review_required():
    audit = audit_project_content(_project(), _manifest(), _article("ev-missing"), (), ())

    assert audit.readiness == "review-required"
    assert audit.missing_evidence_ids == ("ev-missing",)


def test_contradictory_referenced_evidence_and_ambiguous_mapping_require_review():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-contradiction"),
        (_evidence("ev-contradiction", role="contradicts"),),
        (SessionMapping("session-private-01", "alpha", "ambiguous"),),
    )

    assert audit.readiness == "review-required"
    assert audit.findings == ("ambiguous-session-mapping", "contradictory-evidence")


def test_valid_article_with_varying_section_counts_and_support_context_evidence_is_ready():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support", "ev-context", sections=3),
        (_evidence("ev-support"), _evidence("ev-context", role="context")),
        (SessionMapping("mapped-private", "alpha", "cwd"),),
    )

    assert audit.readiness == "ready"
    assert audit.evidence_counts == {"context": 1, "contradicts": 0, "supports": 1, "total": 2}
    assert audit.session_stats == {"ambiguous": 0, "mapped": 1, "total": 1, "unmapped": 0}


def test_context_evidence_alone_cannot_support_an_article_claim():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-context"),
        (_evidence("ev-context", role="context"),),
        (),
    )

    assert audit.readiness == "insufficient-evidence"
    assert audit.findings == ("no-supporting-evidence",)


def test_title_and_diagram_findings_require_review_and_private_values_stay_out_of_public_like_payloads():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support"),
        (_evidence("ev-support"),),
        (SessionMapping("unmapped-private", None, "unmapped"),),
        validation_findings=(
            ArticleValidationFinding("title", "blank-title"),
            ArticleValidationFinding("diagram", "missing-diagram"),
        ),
    )
    public_like = {"project_id": audit.project_id, "readiness": audit.readiness, "findings": audit.findings}

    assert audit.readiness == "review-required"
    assert audit.unmapped_session_ids == ("unmapped-private",)
    assert audit.findings == ("diagram:missing-diagram", "title:blank-title")
    assert "/private" not in str(public_like)
    assert "unmapped-private" not in str(public_like)
    assert "Curated body" not in str(public_like)
    assert not hasattr(audit, "to_public_dict")
