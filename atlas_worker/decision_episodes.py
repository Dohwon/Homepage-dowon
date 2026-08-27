"""Private, bounded decision-episode extraction and review-queue writes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal

from .fs_safety import FileWrite, commit_file_transaction, require_write_destination
from .manifest import require_no_symlink_path
from .models import SessionEvent, SessionTrace
from .sessions import normalize_local_path


OPEN_CUES = re.compile(
    r"문제|제약|왜|대안|바꿔|수정|롤백|결정|선택|채택|실패|겹쳐|따라오지|안\s*돼",
    re.I,
)
_NEGATABLE_OPEN_CUES = frozenset(("문제", "제약", "실패", "수정", "롤백", "결정", "선택", "채택"))
_LOCAL_SENTENCE_BOUNDARY = re.compile(r"[.!?\n;]")
_DIRECT_ABSENCE_SUFFIX = re.compile(
    r"^(?:가|는|도)?\s*없(?:음|습니다)?(?=\s|$|[,.!?;]|지만)",
    re.I,
)
_NEGATED_OPEN_SUFFIX = re.compile(
    r"^[^\n.!?]{0,24}?(?:"
    r"한\s*적\s*(?:이\s*)?없(?:음|습니다)?"
    r"|할\s*필요(?:가|는)?\s*없(?:음|습니다)?"
    r"|필요(?:가|는)\s*없(?:음|습니다)?"
    r"|하지\s*않(?:았(?:습니다|음)?|습니다|음)?"
    r"|안\s*(?:함|했(?:음|습니다)?)"
    r"|불필요"
    r")",
    re.I,
)
_AMBIGUOUS_NEGATED_OPEN_SUFFIX = re.compile(
    r"^[^\n.!?]{0,24}?하지\s*않[^\n.!?]{0,16}?(?:필요|없|불필요)",
    re.I,
)
_SENTENCE_END = r"(?=\s*$|[.!?])"
_FINISHED_SUFFIX = r"(?:했(?:습니다|음|다)?|됨|됐다|되었습니다|되었다)"
_RESULT_END = rf"(?:{_FINISHED_SUFFIX}{_SENTENCE_END}|{_SENTENCE_END})"
_SUPPORTED_CLOSE_CUES = re.compile(
    rf"(?:테스트(?:\s|까지)*(?:통과|성공){_RESULT_END}"
    rf"|검증\s*(?:완료|성공|통과){_RESULT_END}"
    rf"|반영\s*완료{_RESULT_END}"
    rf"|확인(?:\s*완료{_RESULT_END}|{_FINISHED_SUFFIX}{_SENTENCE_END}))",
    re.I,
)
_CANDIDATE_CLOSE_CUES = re.compile(
    r"보류|미해결|unresolved|deferred|(?:확인|검증|테스트|반영|실행).{0,32}(?:보겠|하겠|예정|필요|요청|여부)|(?:시작|실행)\s*예정",
    re.I,
)
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_EPISODE_ID = re.compile(r"^[a-f0-9]{64}$")
_RESULT_ROLES = frozenset({"assistant", "tool"})
_QUEUE_RELATIVE = Path(".knowledge-worker") / "review-queue"
_PRIVATE_RUNTIME_CAPABILITY_TOKEN = object()

MAX_EPISODE_EVENTS = 24
MAX_EXCERPT_CHARS = 280
DecisionEpisodeStatus = Literal["supported", "candidate"]


@dataclass(frozen=True)
class PrivateEpisodeEvent:
    """Bounded local review evidence. All fields are private provenance."""

    evidence_id: str
    event_ordinal: int
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
                    "event_ordinal": event.event_ordinal,
                    "timestamp": event.timestamp,
                    "role": event.role,
                    "source_path": event.source_path,
                    "line_number": event.line_number,
                    "excerpt": event.excerpt,
                }
                for event in self.events
            ],
        }


@dataclass(frozen=True, init=False)
class PrivateRuntimeContext:
    """Validated private-write capability; construct it only through the factory."""

    _workspace_root: Path
    _queue_root: Path
    _capability_token: object

    def __init__(self) -> None:
        raise TypeError("use create_private_runtime_context")


def extract_decision_episodes(
    trace: SessionTrace, project_id: str
) -> tuple[DecisionEpisode, ...]:
    """Extract bounded private episodes; only completed assistant/tool results support one."""
    _require_project_id(project_id)
    episodes: list[DecisionEpisode] = []
    window: list[tuple[int, SessionEvent]] = []
    for ordinal, event in enumerate(trace.events, 1):
        if not window:
            if _is_open_event(event):
                window.append((ordinal, event))
            continue

        if (
            len(window) == MAX_EPISODE_EVENTS - 1
            and _is_open_event(event)
        ):
            episodes.append(_episode(project_id, window, "candidate"))
            window = [(ordinal, event)]
            continue

        window.append((ordinal, event))
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
    """Prepare a private-only review record and reject malformed provenance."""
    _validate_episode(episode)
    return PrivateReviewQueueRecord(
        relative_path=f"{_QUEUE_RELATIVE.as_posix()}/{episode.project_id}-{episode.episode_id}.json",
        project_id=episode.project_id,
        episode_id=episode.episode_id,
        status=episode.status,
        evidence_ids=episode.evidence_ids,
        session_ids=tuple(sorted({event.session_id for event in episode.events if event.session_id})),
        events=episode.events,
    )


def create_private_runtime_context(
    workspace_root: Path,
    *,
    public_output_roots: tuple[Path, ...],
) -> PrivateRuntimeContext:
    """Create the private writer capability after proving it cannot overlap public output."""
    if not public_output_roots:
        raise ValueError("at least one public output root is required")

    private_workspace = _normalize_runtime_directory(workspace_root, "workspace root")
    public_roots = tuple(
        _normalize_runtime_directory(public_root, "public output root")
        for public_root in public_output_roots
    )
    queue_root = private_workspace / _QUEUE_RELATIVE
    require_no_symlink_path(queue_root)

    for public_root in public_roots:
        if _paths_overlap(queue_root, public_root):
            raise ValueError("private review queue overlaps a public output root")
        if _is_within(private_workspace, public_root):
            raise ValueError("private workspace overlaps a public output root")

    return _new_private_runtime_context(private_workspace, queue_root)


def plan_private_review_queue_write(context: PrivateRuntimeContext, episode: DecisionEpisode) -> FileWrite:
    """Plan one private queue write at the fixed workspace-local destination."""
    context = _require_private_runtime_context(context)
    record = private_review_queue_record(episode)
    destination = require_write_destination(
        context._queue_root / f"{record.project_id}-{record.episode_id}.json",
        context._workspace_root,
    )
    payload = json.dumps(
        record.to_private_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ) + "\n"
    return FileWrite(path=destination, content=payload.encode("utf-8"), root=context._workspace_root)


def write_private_review_queue(
    context: PrivateRuntimeContext, episode: DecisionEpisode, *, dry_run: bool = False
) -> tuple[Path, ...]:
    """Atomically persist one private record, or only validate it in dry-run mode."""
    planned = plan_private_review_queue_write(context, episode)
    return () if dry_run else commit_file_transaction((planned,))


def _require_private_runtime_context(context: PrivateRuntimeContext) -> PrivateRuntimeContext:
    if (
        type(context) is not PrivateRuntimeContext
        or context._capability_token is not _PRIVATE_RUNTIME_CAPABILITY_TOKEN
    ):
        raise TypeError("private queue writer requires PrivateRuntimeContext")
    return context


def _new_private_runtime_context(workspace_root: Path, queue_root: Path) -> PrivateRuntimeContext:
    context = object.__new__(PrivateRuntimeContext)
    object.__setattr__(context, "_workspace_root", workspace_root)
    object.__setattr__(context, "_queue_root", queue_root)
    object.__setattr__(context, "_capability_token", _PRIVATE_RUNTIME_CAPABILITY_TOKEN)
    return context


def _normalize_runtime_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    require_no_symlink_path(absolute)
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError:
        raise ValueError(f"{label} must exist") from None
    if not stat.S_ISDIR(mode):
        raise ValueError(f"{label} must be a directory")
    return absolute.resolve(strict=True)


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_within(first, second) or _is_within(second, first)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _episode(
    project_id: str,
    events: list[tuple[int, SessionEvent]],
    status: DecisionEpisodeStatus,
) -> DecisionEpisode:
    private_events = tuple(
        _private_event(project_id, ordinal, event) for ordinal, event in events
    )
    evidence_ids = tuple(event.evidence_id for event in private_events)
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("duplicate evidence IDs in private episode")
    return DecisionEpisode(
        episode_id=_episode_id(project_id, status, evidence_ids),
        project_id=project_id,
        status=status,
        evidence_ids=evidence_ids,
        events=private_events,
    )


def _is_open_event(event: SessionEvent) -> bool:
    return event.role == "user" and _has_open_cue(event.text)


def _has_open_cue(text: str) -> bool:
    for cue_match in OPEN_CUES.finditer(text):
        if not _is_negated_open_cue(text, cue_match):
            return True
    return False


def _is_negated_open_cue(text: str, cue_match: re.Match[str]) -> bool:
    cue = cue_match.group()
    if cue not in _NEGATABLE_OPEN_CUES:
        return False

    suffix = _cue_local_suffix(text, cue_match.end())
    if cue in {"문제", "제약"} and _DIRECT_ABSENCE_SUFFIX.match(suffix):
        return True
    return bool(
        _NEGATED_OPEN_SUFFIX.match(suffix)
        # Ambiguous double negatives are not reliable openings for a public decision.
        or _AMBIGUOUS_NEGATED_OPEN_SUFFIX.match(suffix)
    )


def _cue_local_suffix(text: str, start: int) -> str:
    boundary = _LOCAL_SENTENCE_BOUNDARY.search(text, start)
    end = boundary.start() if boundary else len(text)
    return text[start : min(end, start + 24)]


def _private_event(project_id: str, ordinal: int, event: SessionEvent) -> PrivateEpisodeEvent:
    metadata = {
        "project_id": project_id,
        "event_ordinal": ordinal,
        "session_id": event.session_id,
        "timestamp": event.timestamp,
        "role": event.role,
        "source_path": normalize_local_path(event.source_path),
        "line_number": event.line_number,
        "text_digest": hashlib.sha256(event.text.encode("utf-8")).hexdigest(),
    }
    encoded = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return PrivateEpisodeEvent(
        evidence_id=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        event_ordinal=ordinal,
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


def _require_project_id(project_id: str) -> None:
    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("project_id must be a stable slug")


def _validate_episode(episode: DecisionEpisode) -> None:
    _require_project_id(episode.project_id)
    if not _EPISODE_ID.fullmatch(episode.episode_id):
        raise ValueError("episode id must be a SHA-256 digest")
    if not episode.evidence_ids or len(episode.evidence_ids) != len(set(episode.evidence_ids)):
        raise ValueError("duplicate evidence IDs in private episode")
    if episode.evidence_ids != tuple(event.evidence_id for event in episode.events):
        raise ValueError("private episode evidence does not match its events")
