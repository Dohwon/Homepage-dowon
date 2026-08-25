"""Selective, non-persistent extraction of local session history signals."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .models import EvidenceClaim, SessionEvent


AUTO_MERGE_CONFIDENCE = 0.85
REVIEW_CONFIDENCE = 0.60
CHECKSUM_CHUNK_SIZE = 64 * 1024

SIGNAL_RULES = {
    "rollback": re.compile(r"롤백|되돌려|이전 (?:버전|시안)|revert|rollback", re.I),
    "revision": re.compile(r"다른 시안|다시 수정|여러 시안|재설계|방향 변경", re.I),
    "failure": re.compile(r"테스트 실패|회귀|오류|깨졌|실패 원인", re.I),
    "decision": re.compile(r"결정|채택|선택|trade-?off|대안", re.I),
}

_PASS_RULE = re.compile(r"테스트 (?:통과|성공)|\btests? (?:pass|passed)|\bpassed\b", re.I)
_CORRECTION_COMPLETE_RULE = re.compile(r"(?:수정|변경|적용).{0,20}(?:완료|반영)|\b(?:fixed|implemented)\b", re.I)


@dataclass(frozen=True)
class BackfillCandidates:
    automatic_merge: tuple[EvidenceClaim, ...]
    review: tuple[EvidenceClaim, ...]


def content_checksum(path: Path) -> str:
    """Hash a session incrementally so checksum creation does not read it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_skip_session(path: Path, cursors: Mapping[str, str]) -> bool:
    """Return whether an in-memory cursor has the current content checksum."""
    return cursors.get(str(path)) == content_checksum(path)


def updated_cursors(paths: Iterable[Path], cursors: Mapping[str, str]) -> dict[str, str]:
    """Return a new in-memory checksum cursor without writing session-cursor.json."""
    updated = dict(cursors)
    for path in paths:
        updated[str(path)] = content_checksum(path)
    return updated


def extract_signal_claims(events: Iterable[SessionEvent]) -> tuple[EvidenceClaim, ...]:
    """Return only high-signal claims with normalized values and local pointers."""
    retained = tuple(events)
    claims: list[EvidenceClaim] = []
    for index, event in enumerate(retained):
        claim_type = _signal_type(event.text)
        if claim_type is None:
            continue
        confidence, value = _claim_details(claim_type, event, retained[index + 1 :])
        claims.append(
            EvidenceClaim(
                field="history",
                value=value,
                source_class="session",
                confidence=confidence,
                evidence_id=_evidence_id(event, claim_type),
                claim_type=claim_type,
                event_date=event.timestamp,
                source_path=event.source_path,
            )
        )
    return tuple(claims)


def automatic_merge_claims(claims: Iterable[EvidenceClaim]) -> tuple[EvidenceClaim, ...]:
    """Select claims eligible for a later merge; this function performs no writes."""
    return tuple(claim for claim in claims if claim.confidence >= AUTO_MERGE_CONFIDENCE)


def review_claims(claims: Iterable[EvidenceClaim]) -> tuple[EvidenceClaim, ...]:
    """Select corroboration candidates without writing any project memory."""
    return tuple(
        claim
        for claim in claims
        if REVIEW_CONFIDENCE <= claim.confidence < AUTO_MERGE_CONFIDENCE
    )


def classify_backfill_claims(claims: Iterable[EvidenceClaim]) -> BackfillCandidates:
    """Partition extracted claims into later automatic and reviewed workflows."""
    retained = tuple(claims)
    return BackfillCandidates(
        automatic_merge=automatic_merge_claims(retained),
        review=review_claims(retained),
    )


def _signal_type(text: str) -> str | None:
    for claim_type, rule in SIGNAL_RULES.items():
        if rule.search(text):
            return claim_type
    return None


def _claim_details(
    claim_type: str,
    event: SessionEvent,
    following: tuple[SessionEvent, ...],
) -> tuple[float, str]:
    if claim_type == "rollback":
        return 0.95, "rollback requested"
    if claim_type == "failure":
        if any(_PASS_RULE.search(candidate.text) for candidate in following):
            return 0.85, "failure resolved"
        return 0.75, "failure observed"
    if claim_type == "decision":
        return 0.85, "architecture decision recorded"
    if event.role == "user" and any(
        _CORRECTION_COMPLETE_RULE.search(candidate.text) for candidate in following
    ):
        return 0.90, "revision confirmed"
    return 0.75, "revision requested"


def _evidence_id(event: SessionEvent, claim_type: str) -> str:
    metadata = {
        "claim_type": claim_type,
        "line_number": event.line_number,
        "session_id": event.session_id,
        "source_path": event.source_path.replace("\\", "/"),
        "timestamp": event.timestamp,
    }
    encoded = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
