from pathlib import Path

import pytest

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


def _clean_validator(article: ProjectArticle) -> ArticleValidationReport:
    return _validation_report()


def test_missing_article_yields_insufficient_evidence_without_generic_sections():
    audit = audit_project_content(_project(), _manifest(), None, (), ())

    assert audit.readiness == "insufficient-evidence"
    assert "generic-section" not in audit.findings


def test_missing_referenced_evidence_is_review_required():
    audit = audit_project_content(
        _project(), _manifest(), _article("ev-missing"), (), (), article_validator=_clean_validator
    )

    assert audit.readiness == "review-required"
    assert audit.missing_evidence_ids == ("ev-missing",)


def test_contradictory_referenced_evidence_and_ambiguous_mapping_require_review():
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-contradiction"),
        (_evidence("ev-contradiction", role="contradicts"),),
        (SessionMapping("session-private-01", "alpha", "ambiguous"),),
        article_validator=_clean_validator,
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
        article_validator=_clean_validator,
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
        article_validator=_clean_validator,
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
        article_validator=lambda _: _validation_report(
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


def test_article_validator_missing_or_unchecked_is_review_required_even_with_valid_evidence():
    missing = audit_project_content(
        _project(), _manifest(), _article("ev-support", title=""), (_evidence("ev-support"),), ()
    )
    unchecked = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support"),
        (_evidence("ev-support"),),
        (),
        article_validator=lambda _: ArticleValidationReport(
            title_checked=False, diagrams_checked=True, findings=()
        ),
    )

    assert missing.readiness == "review-required"
    assert missing.findings == ("article-validator-missing", "title:blank-title")
    assert unchecked.readiness == "review-required"
    assert unchecked.findings == ("title-validation-unchecked",)


def test_duplicate_project_evidence_and_article_references_require_review():
    duplicate_evidence = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-duplicate"),
        (_evidence("ev-duplicate"), _evidence("ev-duplicate")),
        (),
        article_validator=_clean_validator,
    )
    duplicate_reference = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support", "ev-support"),
        (_evidence("ev-support"),),
        (),
        article_validator=_clean_validator,
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
        article_validator=_clean_validator,
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
        article_validator=_clean_validator,
    )

    assert audit.readiness == "review-required"
    assert {"article-project-mismatch", "manifest-project-mismatch"} <= set(audit.findings)


def test_article_validator_is_invoked_and_blank_title_overrides_a_clean_result():
    calls: list[ProjectArticle] = []
    article = _article("ev-support", title="")

    def validator(candidate: ProjectArticle) -> ArticleValidationReport:
        calls.append(candidate)
        return _validation_report()

    audit = audit_project_content(
        _project(), _manifest(), article, (_evidence("ev-support"),), (), article_validator=validator
    )

    assert calls == [article]
    assert audit.readiness == "review-required"
    assert "title:blank-title" in audit.findings


def test_validator_missing_static_malformed_and_raising_inputs_fail_closed():
    article = _article("ev-support")
    missing = audit_project_content(_project(), _manifest(), article, (_evidence("ev-support"),), ())
    static = audit_project_content(
        _project(),
        _manifest(),
        article,
        (_evidence("ev-support"),),
        (),
        article_validator=_validation_report(),
    )
    malformed = audit_project_content(
        _project(),
        _manifest(),
        article,
        (_evidence("ev-support"),),
        (),
        article_validator=lambda _: object(),
    )

    def raises(_: ProjectArticle) -> ArticleValidationReport:
        raise RuntimeError("private validator failure")

    failed = audit_project_content(
        _project(), _manifest(), article, (_evidence("ev-support"),), (), article_validator=raises
    )

    assert missing.findings == ("article-validator-missing",)
    assert static.findings == ("article-validator-invalid",)
    assert malformed.findings == ("article-validation-malformed",)
    assert failed.findings == ("article-validation-failed",)


def test_no_article_skips_validator_findings_but_real_safety_findings_take_precedence():
    calls: list[ProjectArticle] = []

    def should_not_run(article: ProjectArticle) -> ArticleValidationReport:
        calls.append(article)
        return _validation_report()

    clean = audit_project_content(_project(), _manifest(), None, (), (), article_validator=should_not_run)
    contradictory = audit_project_content(
        _project(), _manifest(), None, (_evidence("ev-contradiction", role="contradicts"),), ()
    )

    assert clean.readiness == "insufficient-evidence"
    assert "validation-report-missing" not in clean.findings
    assert calls == []
    assert contradictory.readiness == "review-required"
    assert "contradictory-evidence" in contradictory.findings


@pytest.mark.parametrize(
    "malformed_findings",
    (
        [],
        {ArticleValidationFinding("title", "blank-title")},
        (finding for finding in (ArticleValidationFinding("title", "blank-title"),)),
        "title:blank-title",
        (("title", "blank-title"),),
    ),
)
def test_validator_report_requires_exact_tuple_of_typed_findings(malformed_findings):
    audit = audit_project_content(
        _project(),
        _manifest(),
        _article("ev-support"),
        (_evidence("ev-support"),),
        (),
        article_validator=lambda _: ArticleValidationReport(
            title_checked=True, diagrams_checked=True, findings=malformed_findings
        ),
    )

    assert audit.readiness == "review-required"
    assert audit.findings == ("article-validation-malformed",)
