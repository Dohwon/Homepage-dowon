from atlas_worker.decision_episodes import (
    MAX_EPISODE_EVENTS,
    MAX_EXCERPT_CHARS,
    extract_decision_episodes,
    plan_private_review_queue_write,
    private_review_queue_record,
    write_private_review_queue,
)
from dataclasses import replace

import pytest
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


@pytest.mark.parametrize("future_result", ("확인해 보겠습니다", "검증하겠습니다", "반영하겠습니다"))
def test_future_completion_intent_remains_a_candidate(future_result):
    episode = extract_decision_episodes(
        _trace(_event("이 문제가 안 돼", line=1), _event(future_result, role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "candidate"


def test_max_boundary_rollover_restarts_on_the_same_user_open_cue():
    trace = _trace(
        _event("첫 문제를 수정해", line=1),
        *(_event("계속 조사 중", role="assistant", line=line) for line in range(2, MAX_EPISODE_EVENTS)),
        _event("다른 제약도 해결해", line=MAX_EPISODE_EVENTS),
        _event("검증 완료", role="assistant", line=MAX_EPISODE_EVENTS + 1),
    )

    first, second = extract_decision_episodes(trace, "atlas")

    assert (first.status, len(first.events)) == ("candidate", MAX_EPISODE_EVENTS - 1)
    assert (second.status, len(second.events)) == ("supported", 2)
    assert second.events[0].excerpt == "다른 제약도 해결해"


def test_event_text_digest_and_ordinal_prevent_same_metadata_collisions():
    trace = _trace(
        _event("문제가 생겼어", line=1),
        _event("서로 다른 완료 결과", role="assistant", line=2),
        _event("검증 완료", role="assistant", line=2),
    )

    episode = extract_decision_episodes(trace, "atlas")[0]

    assert len(episode.evidence_ids) == len(set(episode.evidence_ids))


def test_private_episode_and_queue_fail_closed_on_duplicate_evidence_ids():
    episode = extract_decision_episodes(
        _trace(_event("문제가 생겼어", line=1), _event("검증 완료", role="assistant", line=2)),
        "atlas",
    )[0]
    duplicate = replace(episode, evidence_ids=(episode.evidence_ids[0], episode.evidence_ids[0]))

    with pytest.raises(ValueError, match="duplicate evidence"):
        private_review_queue_record(duplicate)


def test_private_queue_writer_confines_destination_and_dry_run_is_durable_noop(tmp_path):
    episode = extract_decision_episodes(
        _trace(_event("문제가 생겼어", line=1), _event("검증 완료", role="assistant", line=2)),
        "atlas",
    )[0]

    planned = plan_private_review_queue_write(tmp_path, episode)
    dry_run = write_private_review_queue(tmp_path, episode, dry_run=True)
    assert not planned.path.exists()
    assert not planned.path.parent.exists()
    changed = write_private_review_queue(tmp_path, episode)

    assert planned.path.parent == tmp_path / ".knowledge-worker" / "review-queue"
    assert dry_run == ()
    assert changed == (planned.path,)
    assert planned.path.is_file()
    assert "/private/codex" in planned.path.read_text(encoding="utf-8")


def test_private_queue_writer_rejects_project_traversal_symlink_and_destination_escape(tmp_path):
    base = extract_decision_episodes(
        _trace(_event("문제가 생겼어", line=1), _event("검증 완료", role="assistant", line=2)),
        "atlas",
    )[0]
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".knowledge-worker").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        plan_private_review_queue_write(tmp_path, base)
    with pytest.raises(ValueError, match="stable slug"):
        extract_decision_episodes(_trace(_event("문제가 생겼어", line=1)), "../../public")
    with pytest.raises(ValueError, match="episode id"):
        plan_private_review_queue_write(tmp_path / "clean", replace(base, episode_id="../../public"))
