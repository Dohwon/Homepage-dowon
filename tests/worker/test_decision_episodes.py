from atlas_worker.decision_episodes import (
    MAX_EPISODE_EVENTS,
    MAX_EXCERPT_CHARS,
    extract_decision_episodes,
    private_review_queue_record,
)
from atlas_worker.models import SessionEvent, SessionTrace


def _event(text: str, *, role: str = "user", line: int = 1) -> SessionEvent:
    return SessionEvent(
        session_id="session-private-01",
        timestamp=f"2026-08-27T10:00:{line:02d}Z",
        cwd="/workspace/projects/atlas",
        role=role,
        text=text,
        source_path="/private/codex/sessions/session-private-01.jsonl",
        line_number=line,
    )


def _trace(*events: SessionEvent) -> SessionTrace:
    return SessionTrace(
        session_id="session-private-01",
        parent_session_id="",
        cwd="/workspace/projects/atlas",
        changed_paths=(),
        git_common_dirs=(),
        events=events,
    )


def test_revision_loop_is_one_supported_episode_with_multiple_turns():
    trace = _trace(
        _event("왼쪽 목차가 따라오지 않아", line=1),
        _event("sticky offset을 수정하겠습니다", role="assistant", line=2),
        _event("헤더와 겹쳐. 다시 수정해", line=3),
        _event("회귀 테스트까지 통과했습니다", role="assistant", line=4),
    )

    episodes = extract_decision_episodes(trace, "atlas")

    assert len(episodes) == 1
    assert episodes[0].status == "supported"
    assert len(episodes[0].evidence_ids) == 4


def test_no_decision_language_creates_no_episode():
    trace = _trace(
        _event("파일 목록 보여줘", line=1),
        _event("목록입니다", role="assistant", line=2),
    )

    assert extract_decision_episodes(trace, "alpha") == ()


def test_unresolved_and_max_boundaries_remain_candidates_with_bounded_private_excerpts():
    unresolved = _trace(
        _event("이 동작이 안 돼", line=1),
        _event("원인은 아직 미해결입니다", role="assistant", line=2),
    )
    long_text = "x" * (MAX_EXCERPT_CHARS + 20)
    bounded = _trace(
        _event("이 선택을 바꿔", line=1),
        *(_event(long_text, role="assistant", line=index) for index in range(2, MAX_EPISODE_EVENTS + 1)),
    )

    unresolved_episode = extract_decision_episodes(unresolved, "atlas")[0]
    bounded_episode = extract_decision_episodes(bounded, "atlas")[0]
    unfinished_episode = extract_decision_episodes(
        _trace(_event("이 제약을 해결해", line=1), _event("조사 중입니다", role="assistant", line=2)),
        "atlas",
    )[0]

    assert unresolved_episode.status == "candidate"
    assert bounded_episode.status == "candidate"
    assert unfinished_episode.status == "candidate"
    assert len(bounded_episode.evidence_ids) == MAX_EPISODE_EVENTS
    assert all(len(event.excerpt) <= MAX_EXCERPT_CHARS for event in bounded_episode.events)


def test_event_evidence_ids_are_deterministic_metadata_hashes_and_queue_record_is_private_only():
    trace = _trace(
        _event("문제가 생겼어", line=1),
        _event("검증 통과", role="assistant", line=2),
    )

    first = extract_decision_episodes(trace, "atlas")[0]
    second = extract_decision_episodes(trace, "atlas")[0]
    record = private_review_queue_record(first)
    payload = record.to_private_dict()

    assert first.evidence_ids == second.evidence_ids
    assert all(len(evidence_id) == 64 for evidence_id in first.evidence_ids)
    assert ".knowledge-worker/review-queue/" in record.relative_path
    assert "/private/codex" in str(payload)
    assert "session-private-01" in str(payload)
    assert not hasattr(first, "to_public_dict")
    assert not hasattr(record, "to_public_dict")
