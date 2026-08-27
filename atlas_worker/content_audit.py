"""Private evidence-readiness audit for curated Project Atlas articles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re
from typing import Literal, Protocol

from .models import ContentAudit, EvidenceRecord, ProjectArticle, ProjectRef, SessionMapping
from .source_manifest import SourceManifest


ValidationKind = Literal["title", "diagram"]
_FINDING_CODE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class ArticleValidationFinding:
    """A non-reversible Task 5 validation result accepted by the audit seam."""

    kind: ValidationKind
    code: str

    def __post_init__(self) -> None:
        if self.kind not in {"title", "diagram"}:
            raise ValueError("validation finding kind must be title or diagram")
        if not _FINDING_CODE.fullmatch(self.code):
            raise ValueError("validation finding code must be a stable non-reversible identifier")

    def audit_code(self) -> str:
        return f"{self.kind}:{self.code}"


@dataclass(frozen=True)
class ArticleValidationReport:
    """Typed result returned by the Task 5 title/SVG validator."""

    title_checked: bool
    diagrams_checked: bool
    findings: tuple[ArticleValidationFinding, ...]


class ArticleValidator(Protocol):
    """Task 5 seam that validates a loaded article before readiness is granted."""

    def __call__(self, article: ProjectArticle) -> ArticleValidationReport:
        """Return complete title and diagram validation evidence."""


def audit_project_content(
    project: ProjectRef,
    manifest: SourceManifest,
    article: ProjectArticle | None,
    evidence: Iterable[EvidenceRecord],
    mappings: Sequence[SessionMapping],
    *,
    article_validator: ArticleValidator | None = None,
) -> ContentAudit:
    """Return private readiness without manufacturing article content or public data."""
    all_evidence = tuple(evidence)
    project_evidence = tuple(
        sorted(
            (record for record in all_evidence if record.project_id == project.project_id),
            key=lambda record: (record.evidence_id, record.claim_role, record.content_hash),
        )
    )
    findings: set[str] = set()
    if manifest.project_id != project.project_id:
        findings.add("manifest-project-mismatch")

    session_stats, unmapped_session_ids, ambiguous = _session_audit(project.project_id, mappings)
    if ambiguous:
        findings.add("ambiguous-session-mapping")

    referenced_ids: tuple[str, ...] = ()
    if article is None:
        findings.add("missing-curated-article")
    else:
        findings.update(_validator_findings(article, article_validator))
        if not article.title.strip():
            findings.add("title:blank-title")
        if article.project_id != project.project_id:
            findings.add("article-project-mismatch")
        referenced_ids = _referenced_evidence_ids(article)
        if not referenced_ids:
            findings.add("no-curated-evidence")
        if len(referenced_ids) != len(set(referenced_ids)):
            findings.add("duplicate-evidence-reference")

    evidence_by_id = _evidence_by_id(project_evidence)
    if any(len(records) > 1 for records in evidence_by_id.values()):
        findings.add("duplicate-evidence-id")
    if any(record.claim_role == "contradicts" for record in project_evidence):
        findings.add("contradictory-evidence")
    referenced_set = set(referenced_ids)
    if any(
        record.evidence_id in referenced_set and record.project_id != project.project_id
        for record in all_evidence
    ):
        findings.add("evidence-project-mismatch")

    missing_ids = tuple(
        sorted({evidence_id for evidence_id in referenced_ids if evidence_id not in evidence_by_id})
    )
    if missing_ids:
        findings.add("missing-evidence")
    resolved = tuple(
        record for evidence_id in referenced_ids for record in evidence_by_id.get(evidence_id, ())
    )
    if (
        referenced_ids
        and not any(record.claim_role == "supports" for record in resolved)
        and not any(record.claim_role == "contradicts" for record in resolved)
    ):
        findings.add("no-supporting-evidence")

    return _audit(
        project.project_id,
        _readiness(findings, article),
        project_evidence,
        session_stats,
        missing_ids,
        unmapped_session_ids,
        findings,
    )


def _validator_findings(
    article: ProjectArticle, validator: ArticleValidator | None
) -> set[str]:
    if validator is None:
        return {"article-validator-missing"}
    if not callable(validator):
        return {"article-validator-invalid"}
    try:
        report = validator(article)
    except Exception:
        return {"article-validation-failed"}
    if not _is_well_formed_report(report):
        return {"article-validation-malformed"}
    findings = {finding.audit_code() for finding in report.findings}
    if not report.title_checked:
        findings.add("title-validation-unchecked")
    if not report.diagrams_checked:
        findings.add("diagram-validation-unchecked")
    return findings


def _is_well_formed_report(report: object) -> bool:
    return bool(
        type(report) is ArticleValidationReport
        and type(report.title_checked) is bool
        and type(report.diagrams_checked) is bool
        and type(report.findings) is tuple
        and all(type(finding) is ArticleValidationFinding for finding in report.findings)
    )


def _referenced_evidence_ids(article: ProjectArticle) -> tuple[str, ...]:
    return tuple(
        evidence_id
        for section in article.sections
        for evidence_id in section.evidence_ids
    ) + tuple(
        evidence_id
        for decision in article.decision_index
        for evidence_id in decision.evidence_ids
    )


def _evidence_by_id(evidence: Sequence[EvidenceRecord]) -> dict[str, tuple[EvidenceRecord, ...]]:
    values: dict[str, list[EvidenceRecord]] = {}
    for record in evidence:
        values.setdefault(record.evidence_id, []).append(record)
    return {key: tuple(records) for key, records in values.items()}


def _readiness(
    findings: set[str], article: ProjectArticle | None
) -> Literal["ready", "insufficient-evidence", "review-required"]:
    insufficient = {"missing-curated-article", "no-curated-evidence", "no-supporting-evidence"}
    if findings - insufficient:
        return "review-required"
    if article is None or findings & insufficient:
        return "insufficient-evidence"
    return "ready"


def _session_audit(
    project_id: str, mappings: Sequence[SessionMapping]
) -> tuple[dict[str, int], tuple[str, ...], bool]:
    relevant = tuple(mapping for mapping in mappings if mapping.project_id in {project_id, None})
    unmapped = tuple(
        sorted(
            mapping.session_id
            for mapping in relevant
            if mapping.reason == "unmapped" and mapping.session_id
        )
    )
    ambiguous = any(mapping.reason == "ambiguous" for mapping in relevant)
    return (
        {
            "ambiguous": sum(mapping.reason == "ambiguous" for mapping in relevant),
            "mapped": sum(mapping.project_id == project_id for mapping in relevant),
            "total": len(relevant),
            "unmapped": len(unmapped),
        },
        unmapped,
        ambiguous,
    )


def _audit(
    project_id: str,
    readiness: Literal["ready", "insufficient-evidence", "review-required"],
    evidence: Sequence[EvidenceRecord],
    session_stats: dict[str, int],
    missing_evidence_ids: tuple[str, ...],
    unmapped_session_ids: tuple[str, ...],
    findings: set[str],
) -> ContentAudit:
    roles = Counter(record.claim_role for record in evidence)
    counts = {
        "context": roles["context"],
        "contradicts": roles["contradicts"],
        "supports": roles["supports"],
        "total": len(evidence),
    }
    if roles["supersedes"]:
        counts["supersedes"] = roles["supersedes"]
    return ContentAudit(
        project_id=project_id,
        readiness=readiness,
        evidence_counts=counts,
        session_stats=session_stats,
        missing_evidence_ids=missing_evidence_ids,
        unmapped_session_ids=unmapped_session_ids,
        findings=tuple(sorted(findings)),
    )
