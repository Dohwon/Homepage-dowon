"""Private evidence-readiness audit for curated Project Atlas articles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re
from typing import Literal

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


def audit_project_content(
    project: ProjectRef,
    manifest: SourceManifest,
    article: ProjectArticle | None,
    evidence: Iterable[EvidenceRecord],
    mappings: Sequence[SessionMapping],
    *,
    validation_findings: Iterable[ArticleValidationFinding] = (),
) -> ContentAudit:
    """Return private readiness without manufacturing article content or public data."""
    project_evidence = tuple(
        sorted(
            (record for record in evidence if record.project_id == project.project_id),
            key=lambda record: (record.evidence_id, record.claim_role, record.content_hash),
        )
    )
    findings = {finding.audit_code() for finding in validation_findings}
    if manifest.project_id != project.project_id:
        findings.add("manifest-project-mismatch")

    session_stats, unmapped_session_ids, ambiguous = _session_audit(project.project_id, mappings)
    if ambiguous:
        findings.add("ambiguous-session-mapping")

    if article is None:
        findings.add("missing-curated-article")
        return _audit(
            project.project_id,
            "insufficient-evidence",
            project_evidence,
            session_stats,
            (),
            unmapped_session_ids,
            findings,
        )

    if article.project_id != project.project_id:
        findings.add("article-project-mismatch")
    referenced_ids = _referenced_evidence_ids(article)
    if not referenced_ids:
        findings.add("no-curated-evidence")

    evidence_by_id: dict[str, list[EvidenceRecord]] = {}
    for record in project_evidence:
        evidence_by_id.setdefault(record.evidence_id, []).append(record)
    missing_ids = tuple(
        evidence_id for evidence_id in referenced_ids if not evidence_by_id.get(evidence_id)
    )
    if missing_ids:
        findings.add("missing-evidence")
    resolved = tuple(
        record
        for evidence_id in referenced_ids
        for record in evidence_by_id.get(evidence_id, ())
    )
    if any(len(evidence_by_id[evidence_id]) != 1 for evidence_id in referenced_ids if evidence_id in evidence_by_id):
        findings.add("ambiguous-evidence-id")
    if any(record.claim_role == "contradicts" for record in resolved):
        findings.add("contradictory-evidence")
    if (
        referenced_ids
        and not any(record.claim_role == "supports" for record in resolved)
        and not any(record.claim_role == "contradicts" for record in resolved)
    ):
        findings.add("no-supporting-evidence")

    readiness = "ready"
    review_findings = findings - {"missing-curated-article", "no-curated-evidence", "no-supporting-evidence"}
    if review_findings:
        readiness = "review-required"
    elif not referenced_ids or "no-supporting-evidence" in findings:
        readiness = "insufficient-evidence"
    return _audit(
        project.project_id,
        readiness,
        project_evidence,
        session_stats,
        missing_ids,
        unmapped_session_ids,
        findings,
    )


def _referenced_evidence_ids(article: ProjectArticle) -> tuple[str, ...]:
    ids = {
        evidence_id
        for section in article.sections
        for evidence_id in section.evidence_ids
    }
    ids.update(
        evidence_id
        for decision in article.decision_index
        for evidence_id in decision.evidence_ids
    )
    return tuple(sorted(ids))


def _session_audit(
    project_id: str, mappings: Sequence[SessionMapping]
) -> tuple[dict[str, int], tuple[str, ...], bool]:
    relevant = tuple(
        mapping
        for mapping in mappings
        if mapping.project_id in {project_id, None}
    )
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
