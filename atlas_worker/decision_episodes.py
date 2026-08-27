"""Private, bounded decision-episode extraction for Atlas review workflows."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal

from .models import SessionEvent, SessionTrace
from .sessions import normalize_local_path


OPEN_CUES = re.compile(
    r"문제|제약|왜|대안|바꿔|수정|롤백|결정|선택|채택|실패|겹쳐|따라오지|안\s*돼",
    re.I,
)
_SUPPORTED_CLOSE_CUES = re.compile(r"검증|통과|완료|반영|확인", re.I)
_CANDIDATE_CLOSE_CUES = re.compile(r"보류|미해결", re.I)
_RESULT_ROLES = frozenset({"assistant", "tool"})

MAX_EPISODE_EVENTS = 24
MAX_EXCERPT_CHARS = 280
DecisionEpisodeStatus = Literal["supported", "candidate"]


@dataclass(frozen=True)
class PrivateEpisodeEvent:
    """Bounded local review evidence. All fields are private provenance."""

    evidence_id: str
    session_id: str
    timestamp: str
    role: str
    source_path: str
    line_number: int
    excerpt: str


@dataclass(frozen=True)
class DecisionEpisode:
    """A private candidate or supported decision trace with no public projection."""

    episode_id: str
    project_id: str
    status: DecisionEpisodeStatus
    evidence_ids: tuple[str, ...]
    events: tuple[PrivateEpisodeEvent, ...]


@dataclass(frozen=True)
class PrivateReviewQueueRecord:
    """Private-only record for `.knowledge-worker/review-queue/` persistence."""

    relative_path: str
    project_id: str
    episode_id: str
    status: DecisionEpisodeStatus
    evidence_ids: tuple[str, ...]
    session_ids: tuple[str, ...]
    events: tuple[PrivateEpisodeEvent, ...]

    def to_private_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "episode_id": self.episode_id,
            "status": self.status,
            "evidence_ids": list(self.evidence_ids),
            "session_ids": list(self.session_ids),
            "events": [
                {
                    "evidence_id": event.evidence_id,
                    "timestamp": event.timestamp,
                    "role": event.role,
                    "source_path": event.source_path,
                    "line_number": event.line_number,
                    "excerpt": event.excerpt,
                }
                for event in self.events
            ],
        }


def extract_decision_episodes(
    trace: SessionTrace, project_id: str
) -> tuple[DecisionEpisode, ...]:
    """Extract bounded private episodes; only validated assistant/tool closes support one."""
    episodes: list[DecisionEpisode] = []
    window: list[SessionEvent] = []
    for event in trace.events:
        if not window:
            if event.role == "user" and OPEN_CUES.search(event.text):
                window.append(event)
            continue

        window.append(event)
        if _CANDIDATE_CLOSE_CUES.search(event.text):
            episodes.append(_episode(project_id, window, "candidate"))
            window = []
        elif len(window) >= MAX_EPISODE_EVENTS:
            episodes.append(_episode(project_id, window, "candidate"))
            window = []
        elif event.role in _RESULT_ROLES and _SUPPORTED_CLOSE_CUES.search(event.text):
            episodes.append(_episode(project_id, window, "supported"))
            window = []

    if window:
        episodes.append(_episode(project_id, window, "candidate"))
    return tuple(episodes)


def private_review_queue_record(episode: DecisionEpisode) -> PrivateReviewQueueRecord:
    """Prepare, but do not publish or write, a review-queue-only record."""
    return PrivateReviewQueueRecord(
        relative_path=f".knowledge-worker/review-queue/{episode.project_id}-{episode.episode_id}.json",
        project_id=episode.project_id,
        episode_id=episode.episode_id,
        status=episode.status,
        evidence_ids=episode.evidence_ids,
        session_ids=tuple(sorted({event.session_id for event in episode.events if event.session_id})),
        events=episode.events,
    )


def _episode(
    project_id: str, events: list[SessionEvent], status: DecisionEpisodeStatus
) -> DecisionEpisode:
    private_events = tuple(_private_event(project_id, event) for event in events)
    evidence_ids = tuple(event.evidence_id for event in private_events)
    return DecisionEpisode(
        episode_id=_episode_id(project_id, status, evidence_ids),
        project_id=project_id,
        status=status,
        evidence_ids=evidence_ids,
        events=private_events,
    )


def _private_event(project_id: str, event: SessionEvent) -> PrivateEpisodeEvent:
    metadata = {
        "project_id": project_id,
        "session_id": event.session_id,
        "timestamp": event.timestamp,
        "role": event.role,
        "source_path": normalize_local_path(event.source_path),
        "line_number": event.line_number,
    }
    encoded = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return PrivateEpisodeEvent(
        evidence_id=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        session_id=event.session_id,
        timestamp=event.timestamp,
        role=event.role,
        source_path=event.source_path,
        line_number=event.line_number,
        excerpt=event.text[:MAX_EXCERPT_CHARS],
    )


def _episode_id(
    project_id: str, status: DecisionEpisodeStatus, evidence_ids: tuple[str, ...]
) -> str:
    encoded = json.dumps(
        {"project_id": project_id, "status": status, "evidence_ids": evidence_ids},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
