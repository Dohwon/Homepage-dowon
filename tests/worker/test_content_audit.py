from pathlib import Path

from atlas_worker.content_audit import (
    ArticleValidationFinding,
    ArticleValidationReport,
    audit_project_content,
)
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


def _article(*evidence_ids: str, sections: int = 1, title: str = "Evidence-backed decision") -> ProjectArticle:
    return ProjectArticle(
        project_id="alpha",
        title=title,
        summary="Curated result",
        readiness="ready",
        sections=tuple(
            ArticleSection(
                section_id=f"section-{index}",
                title=f"Section {index}",
                section_type="decision",
                body="Curated body",
                evidence_ids=evidence_ids if index == 0 else (),
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


def _validation_report(*findings: ArticleValidationFinding) -> ArticleValidationReport:
    return ArticleValidationReport(title_checked=True, diagrams_checked=True, findings=findings)


def test_missing_article_yields_insufficient_evidence_without_generic_sections():
    audit = audit_project_content(
        _project(), _manifest(), None, (), (), validation_report=_validation_report()
    )

    assert audit.readiness == "insufficient-evidence"
    assert "generic-section" not in audit.findings


def test_missing_referenced_evidence_is_review_required():
    audit = audit_project_content(_project(), _manifest(), _article("ev-missing"), (), (), validation_report=_validation_report())

    assert audit.readiness == "review-required"
    assert audit.missing_evidence_ids == ("ev-missing",)


def test_contradictory_referenced_evidence_and_ambiguous_mapping_require_review():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-contradiction"),
        (_evidence("ev-contradiction", role="contradicts"),),
        (SessionMapping("session-private-01", "alpha", "ambiguous"),),
        validation_report=_validation_report(),
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
        validation_report=_validation_report(),
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
        validation_report=_validation_report(),
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
        validation_report=_validation_report(
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


def test_validation_report_missing_or_unchecked_is_review_required_even_with_valid_evidence():
    missing = audit_project_content(
        _project(), _manifest(), _article("ev-support", title=""), (_evidence("ev-support"),), ()
    )
    unchecked = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support"),
        (_evidence("ev-support"),),
        (),
        validation_report=ArticleValidationReport(title_checked=False, diagrams_checked=True, findings=()),
    )

    assert missing.readiness == "review-required"
    assert missing.findings == ("validation-report-missing",)
    assert unchecked.readiness == "review-required"
    assert unchecked.findings == ("title-validation-unchecked",)


def test_duplicate_project_evidence_and_article_references_require_review():
    duplicate_evidence = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-duplicate"),
        (_evidence("ev-duplicate"), _evidence("ev-duplicate")),
        (),
        validation_report=_validation_report(),
    )
    duplicate_reference = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support", "ev-support"),
        (_evidence("ev-support"),),
        (),
        validation_report=_validation_report(),
    )

    assert duplicate_evidence.readiness == "review-required"
    assert "duplicate-evidence-id" in duplicate_evidence.findings
    assert duplicate_reference.readiness == "review-required"
    assert "duplicate-evidence-reference" in duplicate_reference.findings


def test_unreferenced_contradiction_and_ambiguous_no_article_take_review_precedence():
    contradiction = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support"),
        (_evidence("ev-support"), _evidence("ev-unresolved", role="contradicts")),
        (),
        validation_report=_validation_report(),
    )
    no_article = audit_project_content(
        _project(),
        _manifest(),
        None,
        (),
        (SessionMapping("private-ambiguous", None, "ambiguous"),),
    )

    assert contradiction.readiness == "review-required"
    assert "contradictory-evidence" in contradiction.findings
    assert no_article.readiness == "review-required"
    assert "ambiguous-session-mapping" in no_article.findings


def test_article_evidence_and_manifest_project_mismatches_remain_safety_findings():
    wrong_manifest = SourceManifest(
        project_id="beta",
        files=(),
        predecessor_ids=(),
        git_head_fingerprint="head",
        git_common_dir_fingerprint="common",
    )
    foreign_evidence = EvidenceRecord(
        evidence_id="ev-foreign",
        project_id="beta",
        label="Foreign evidence",
        source_type="session",
        source_locator="/private/sessions/beta.jsonl:1",
        observed_at="2026-08-27T10:00:00Z",
        privacy_class="private",
        content_hash="b" * 64,
    )
    foreign_article = ProjectArticle(
        project_id="beta",
        title="Foreign",
        summary="Foreign",
        readiness="ready",
        sections=(),
    )

    audit = audit_project_content(
        _project(),
        wrong_manifest,
        foreign_article,
        (foreign_evidence,),
        (),
        validation_report=_validation_report(),
    )

    assert audit.readiness == "review-required"
    assert {"article-project-mismatch", "manifest-project-mismatch"} <= set(audit.findings)
