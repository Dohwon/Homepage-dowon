"""Evidence-backed public tag selection."""

from __future__ import annotations

from collections import defaultdict
import unicodedata
from typing import Iterable

from .evidence import SOURCE_PRIORITY
from .models import PublicProject, TAG_LIMITS, TagCandidate, TagSet


TAG_DECISIONS = frozenset({"infer", "approve", "reject"})


def normalize_tag_label(label: str) -> str:
    """Return a Unicode, case, and whitespace-stable tag identity."""
    return _display_label(label).casefold()


def display_tag_label(label: str) -> str:
    """Return a normalized display label without changing its chosen case."""
    return _display_label(label)


def select_tags(project: PublicProject, candidates: Iterable[TagCandidate]) -> TagSet:
    """Select manual baseline tags plus sufficiently corroborated local evidence."""
    candidate_groups: dict[tuple[str, str], list[TagCandidate]] = defaultdict(list)
    rejected: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if candidate.decision == "reject":
            rejected.add(key)
        else:
            candidate_groups[key].append(candidate)

    selected: dict[str, tuple[str, ...]] = {}
    for kind, (minimum, maximum) in TAG_LIMITS.items():
        baseline = _baseline_tags(project, kind)
        options: dict[str, _TagOption] = {
            identity: _TagOption(identity, _choose_display(labels), (2, 0, 0, 0.0))
            for identity, labels in baseline.items()
            if (kind, identity) not in rejected
        }
        inferred = [
            option
            for (candidate_kind, _), group in candidate_groups.items()
            if candidate_kind == kind
            and (option := _supported_option(group)) is not None
            and (kind, option.identity) not in rejected
        ]
        for option in sorted(inferred, key=lambda item: (-item.rank[0], -item.rank[1], -item.rank[2], -item.rank[3], item.identity)):
            if option.identity not in options and len(options) < maximum:
                options[option.identity] = option

        values = tuple(options[identity].label for identity in sorted(options))
        if len(values) < minimum:
            raise ValueError(
                f"not public-ready: {kind} requires at least {minimum} supported tag"
                f"{'s' if minimum != 1 else ''}"
            )
        selected[kind] = values

    return TagSet(**selected)


class _TagOption:
    def __init__(self, identity: str, label: str, rank: tuple[int, int, int, float]) -> None:
        self.identity = identity
        self.label = label
        self.rank = rank


def _candidate_key(candidate: TagCandidate) -> tuple[str, str]:
    if candidate.kind not in TAG_LIMITS:
        raise ValueError(f"Unknown kind: {candidate.kind}")
    if candidate.source_class not in SOURCE_PRIORITY:
        raise ValueError(f"Unknown source_class: {candidate.source_class}")
    if candidate.decision not in TAG_DECISIONS:
        raise ValueError(f"Unknown decision: {candidate.decision}")
    if candidate.decision != "infer" and candidate.source_class != "profile":
        raise ValueError("Manual decision requires source_class: profile")
    if not isinstance(candidate.evidence_id, str) or not candidate.evidence_id.strip():
        raise ValueError("Tag evidence_id must be a non-empty string")
    return candidate.kind, normalize_tag_label(candidate.label)


def _baseline_tags(project: PublicProject, kind: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for label in getattr(project.tags, kind):
        grouped[normalize_tag_label(label)].append(display_tag_label(label))
    return grouped


def _supported_option(candidates: list[TagCandidate]) -> _TagOption | None:
    approvals = [candidate for candidate in candidates if candidate.decision == "approve"]
    evidence = _unique_evidence(candidates)
    source_classes = {source_class for source_class, _ in evidence}
    evidence_ids = {evidence_id for _, evidence_id in evidence}
    approved = bool(approvals)
    if not approved and (len(source_classes) < 2 or len(evidence_ids) < 2):
        return None
    labels = [display_tag_label(candidate.label) for candidate in candidates]
    identity = normalize_tag_label(candidates[0].label)
    confidence = max(evidence.values())
    return _TagOption(
        identity,
        _choose_display(labels),
        (1 if approved else 0, len(source_classes), len(evidence_ids), confidence),
    )


def _unique_evidence(candidates: Iterable[TagCandidate]) -> dict[tuple[str, str], float]:
    evidence: dict[tuple[str, str], float] = {}
    for candidate in candidates:
        key = (candidate.source_class, candidate.evidence_id)
        evidence[key] = max(evidence.get(key, float("-inf")), candidate.confidence)
    return evidence


def _choose_display(labels: Iterable[str]) -> str:
    return min(labels, key=lambda label: (normalize_tag_label(label), label))


def _display_label(label: str) -> str:
    if not isinstance(label, str):
        raise ValueError("Tag label must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", label).split())
    if not normalized:
        raise ValueError("Tag label must be non-empty")
    return normalized
