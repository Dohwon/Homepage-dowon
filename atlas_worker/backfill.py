"""Selective, non-persistent extraction of local session history signals."""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .models import EvidenceClaim, SessionEvent
from .sessions import normalize_local_path


AUTO_MERGE_CONFIDENCE = 0.85
REVIEW_CONFIDENCE = 0.60
CHECKSUM_CHUNK_SIZE = 64 * 1024
MAX_ACTIVE_CONTEXTS = 128
MAX_TARGETS_PER_CONTEXT = 64
_RESULT_ROLES = {"assistant", "tool"}

SIGNAL_RULES = {
    "rollback": re.compile(r"롤백|되돌려|이전 (?:버전|시안)|revert|rollback", re.I),
    "revision": re.compile(
        r"다른 시안|다시 수정|여러 시안|두 시안|세 시안|재설계|방향 변경|visual alternatives?|design alternatives?",
        re.I,
    ),
    "failure": re.compile(r"테스트 실패|회귀|오류|깨졌|실패 원인", re.I),
    "decision": re.compile(r"결정|채택|선택|trade-?off|대안|\b(?:decide|decision|adopt|select)\b", re.I),
}

_PASS_RULE = re.compile(r"테스트 (?:통과|성공)|\btests? (?:pass|passed)|\bpassed\b", re.I)
_CORRECTION_COMPLETE_RULE = re.compile(r"(?:수정|변경|적용).{0,20}(?:완료|반영)|\b(?:fixed|implemented)\b", re.I)
_COMMITTED_DECISION_RULE = re.compile(
    r"채택(?:하기로|했다|함|한다)|결정(?:하기로|했다|함|한다)|선택(?:하기로|했다|함|한다)|\b(?:adopt(?:ed|s)?|decide(?:d|s)?|select(?:ed|s)?)\b",
    re.I,
)
_ARCHITECTURE_CONTEXT_RULE = re.compile(r"아키텍처|architecture|시스템\s*구조|system\s*design|설계\s*구조", re.I)
_DIRECT_ADOPTION_RULE = re.compile(r"(?:^|\s)\S+(?:을|를)\s+채택한다(?=\s|[.!]|$)")
_NON_COMMITTED_DECISION_RULE = re.compile(
    r"[?？]|할까|인가|(?:결정|선택|채택)\s*(?:하)?지\s*(?:마|말|않(?:음|는다|았다)?|못)"
    r"|(?:결정|선택|채택)\s*(?:안|않|못)\s*(?:함|됨|있음)?|(?:결정|선택|채택)\s*보류"
    r"|\b(?:do\s+not|don't|not|never)\b.*\b(?:decide|decision|select|adopt)\b"
    r"|\b(?:decide|decision|select|adopt)\b.*\b(?:not|defer(?:red|ring)?|postpone(?:d|ment)?)\b"
    r"|\b(?:defer(?:red|ring)?|postpone(?:d|ment)?)\b.*\b(?:decision|decide|select|adopt)\b"
    r"|\b(?:should|can|could|would)\b.*\b(?:decide|decision|select|adopt)\b",
    re.I,
)
_QUOTED_TEXT_RULE = re.compile(r"[\"'`“”‘’「」『』]")
_MULTIPLE_VISUAL_RULE = re.compile(r"(?:두|세|2|3|여러|multiple)\s*(?:개\s*)?(?:시안|visual alternatives?|design alternatives?)", re.I)
_TARGET_RULE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|js|jsx|ts|tsx|css|html|json|yaml|yml|md))\b",
    re.I,
)


@dataclass(frozen=True)
class BackfillCandidates:
    automatic_merge: tuple[EvidenceClaim, ...]
    review: tuple[EvidenceClaim, ...]


@dataclass(frozen=True)
class _PendingEvidence:
    session_id: str
    timestamp: str
    source_path: str
    line_number: int


@dataclass
class _ContextState:
    pending_failure: _PendingEvidence | None = None
    pending_revision: _PendingEvidence | None = None
    revision_targets: OrderedDict[str, int] = field(default_factory=OrderedDict)


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
    """Incrementally extract high-signal claims without retaining raw event text."""
    claims: list[EvidenceClaim] = []
    states: OrderedDict[tuple[str, str], _ContextState] = OrderedDict()
    for event in events:
        state = _state_for_event(states, event)
        if state is not None and event.role in _RESULT_ROLES:
            _apply_result_confirmation(claims, state, event)

        claim_type = _signal_type(event.text)
        if claim_type is None:
            continue

        if claim_type == "rollback":
            claims.append(_claim_from_event(event, "rollback", 0.95, "rollback requested"))
        elif claim_type == "decision" and _is_committed_architecture_decision(event.text):
            claims.append(_claim_from_event(event, "decision", 0.85, "architecture decision recorded"))
        elif claim_type == "failure" and state is not None:
            state.pending_failure = _pending_evidence(event)
        elif claim_type == "revision" and state is not None:
            _record_revision(claims, state, event)
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


def _state_for_event(
    states: OrderedDict[tuple[str, str], _ContextState], event: SessionEvent
) -> _ContextState | None:
    if not event.session_id or not event.cwd:
        return None
    key = (event.session_id, normalize_local_path(event.cwd))
    if not key[1]:
        return None
    state = states.pop(key, None)
    if state is None:
        state = _ContextState()
    states[key] = state
    while len(states) > MAX_ACTIVE_CONTEXTS:
        states.popitem(last=False)
    return state


def _apply_result_confirmation(
    claims: list[EvidenceClaim], state: _ContextState, event: SessionEvent
) -> None:
    if state.pending_failure is not None and _PASS_RULE.search(event.text):
        claims.append(_claim_from_pending(state.pending_failure, "failure", 0.85, "failure resolved"))
        state.pending_failure = None
    if state.pending_revision is not None and _CORRECTION_COMPLETE_RULE.search(event.text):
        claims.append(_claim_from_pending(state.pending_revision, "revision", 0.90, "revision confirmed"))
        state.pending_revision = None


def _record_revision(claims: list[EvidenceClaim], state: _ContextState, event: SessionEvent) -> None:
    if event.role == "user":
        state.pending_revision = _pending_evidence(event)
    if _MULTIPLE_VISUAL_RULE.search(event.text):
        claims.append(_claim_from_event(event, "revision", 0.75, "multiple visual alternatives"))
        return

    target = _target_from(event.text)
    if target is None:
        return
    count = state.revision_targets.pop(target, 0) + 1
    state.revision_targets[target] = count
    while len(state.revision_targets) > MAX_TARGETS_PER_CONTEXT:
        state.revision_targets.popitem(last=False)
    if count == 3:
        claims.append(_claim_from_event(event, "revision", 0.75, "revision corroborated"))


def _is_committed_architecture_decision(text: str) -> bool:
    return bool(
        _COMMITTED_DECISION_RULE.search(text)
        and (_ARCHITECTURE_CONTEXT_RULE.search(text) or _DIRECT_ADOPTION_RULE.search(text))
        and not _NON_COMMITTED_DECISION_RULE.search(text)
        and not _QUOTED_TEXT_RULE.search(text)
    )


def _target_from(text: str) -> str | None:
    match = _TARGET_RULE.search(text)
    return normalize_local_path(match.group(1)) if match is not None else None


def _pending_evidence(event: SessionEvent) -> _PendingEvidence:
    return _PendingEvidence(
        session_id=event.session_id,
        timestamp=event.timestamp,
        source_path=event.source_path,
        line_number=event.line_number,
    )


def _claim_from_event(
    event: SessionEvent, claim_type: str, confidence: float, value: str
) -> EvidenceClaim:
    return _claim_from_metadata(
        _pending_evidence(event), claim_type, confidence, value
    )


def _claim_from_pending(
    evidence: _PendingEvidence, claim_type: str, confidence: float, value: str
) -> EvidenceClaim:
    return _claim_from_metadata(evidence, claim_type, confidence, value)


def _claim_from_metadata(
    evidence: _PendingEvidence, claim_type: str, confidence: float, value: str
) -> EvidenceClaim:
    return EvidenceClaim(
        field="history",
        value=value,
        source_class="session",
        confidence=confidence,
        evidence_id=_evidence_id(evidence, claim_type),
        claim_type=claim_type,
        event_date=evidence.timestamp,
        source_path=evidence.source_path,
    )


def _evidence_id(event: _PendingEvidence, claim_type: str) -> str:
    metadata = {
        "claim_type": claim_type,
        "line_number": event.line_number,
        "session_id": event.session_id,
        "source_path": normalize_local_path(event.source_path),
        "timestamp": event.timestamp,
    }
    encoded = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
