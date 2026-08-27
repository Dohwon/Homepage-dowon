from atlas_worker.decision_episodes import (
    MAX_EPISODE_EVENTS,
    MAX_EXCERPT_CHARS,
    create_private_runtime_context,
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


def _private_runtime_context(workspace_root, *public_output_roots):
    workspace_root.mkdir(parents=True, exist_ok=True)
    for public_output_root in public_output_roots:
        public_output_root.mkdir(parents=True, exist_ok=True)
    return create_private_runtime_context(
        workspace_root,
        public_output_roots=public_output_roots,
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


@pytest.mark.parametrize(
    "not_completed",
    ("확인", "확인 필요", "확인 요청", "확인해 보겠습니다", "검증 필요", "unresolved", "deferred"),
)
def test_non_completed_confirmation_language_remains_candidate(not_completed):
    episode = extract_decision_episodes(
        _trace(_event("이 문제가 안 돼", line=1), _event(not_completed, role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "candidate"


@pytest.mark.parametrize("completed", ("확인했습니다", "확인 완료", "확인됨"))
def test_completed_confirmation_results_are_supported(completed):
    episode = extract_decision_episodes(
        _trace(_event("이 문제가 안 돼", line=1), _event(completed, role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "supported"


@pytest.mark.parametrize("completed", ("테스트 통과", "검증 완료", "반영 완료"))
def test_completed_validation_results_are_supported(completed):
    episode = extract_decision_episodes(
        _trace(_event("이 문제가 안 돼", line=1), _event(completed, role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "supported"


@pytest.mark.parametrize(
    "not_completed",
    (
        "테스트 통과 여부를 확인할 필요가 있습니다",
        "검증 완료 여부를 확인해",
        "테스트 통과 필요",
        "검증 예정",
    ),
)
def test_completion_questions_and_deferred_grammar_remain_candidates(not_completed):
    episode = extract_decision_episodes(
        _trace(_event("이 문제가 안 돼", line=1), _event(not_completed, role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "candidate"


@pytest.mark.parametrize(
    "negative_open",
    (
        "문제가 없습니다",
        "제약 없음",
        "실패하지 않았습니다",
        "수정 불필요",
        "롤백하지 않음",
        "결정하지 않음",
        "실패한 적 없습니다",
        "수정할 필요 없습니다",
        "롤백 안 함",
        "결정 안 함",
        "선택할 필요가 없음",
        "채택하지 않았습니다",
    ),
)
def test_negated_open_cues_do_not_create_supported_episodes(negative_open):
    trace = _trace(_event(negative_open, line=1), _event("확인했습니다", role="assistant", line=2))

    assert extract_decision_episodes(trace, "atlas") == ()


@pytest.mark.parametrize(
    "positive_open",
    ("문제가 있습니다", "이 동작이 안 돼", "실패 원인 해결", "다시 수정해", "롤백해", "결정해"),
)
def test_positive_open_cues_still_create_supported_episodes(positive_open):
    episode = extract_decision_episodes(
        _trace(_event(positive_open, line=1), _event("확인했습니다", role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "supported"


def test_ambiguous_double_negation_does_not_start_a_supported_episode():
    trace = _trace(
        _event("실패하지 않을 필요는 없습니다", line=1),
        _event("확인했습니다", role="assistant", line=2),
    )

    assert extract_decision_episodes(trace, "atlas") == ()


@pytest.mark.parametrize(
    "mixed_open",
    (
        "문제는 없습니다. 하지만 이전 버전으로 롤백해",
        "문제는 없지만 경로가 안 돼",
        "결정 안 함. 다시 수정해",
    ),
)
def test_cue_local_negation_preserves_another_unnegated_open_cue(mixed_open):
    episode = extract_decision_episodes(
        _trace(_event(mixed_open, line=1), _event("확인했습니다.", role="assistant", line=2)),
        "atlas",
    )[0]

    assert episode.status == "supported"


def test_only_locally_negated_cues_do_not_create_an_episode():
    trace = _trace(
        _event("롤백 안 함. 문제도 없습니다", line=1),
        _event("확인했습니다.", role="assistant", line=2),
    )

    assert extract_decision_episodes(trace, "atlas") == ()


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

    context = _private_runtime_context(tmp_path, tmp_path / "public-output")
    planned = plan_private_review_queue_write(context, episode)
    dry_run = write_private_review_queue(context, episode, dry_run=True)
    assert not planned.path.exists()
    assert not planned.path.parent.exists()
    changed = write_private_review_queue(context, episode)

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
    context = _private_runtime_context(tmp_path, tmp_path / "public-output")
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".knowledge-worker").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        plan_private_review_queue_write(context, base)
    with pytest.raises(ValueError, match="stable slug"):
        extract_decision_episodes(_trace(_event("문제가 생겼어", line=1)), "../../public")
    with pytest.raises(ValueError, match="episode id"):
        plan_private_review_queue_write(
            _private_runtime_context(tmp_path / "clean", tmp_path / "clean-public"),
            replace(base, episode_id="../../public"),
        )


def test_private_queue_writer_rejects_raw_path_and_requires_public_roots(tmp_path):
    episode = extract_decision_episodes(
        _trace(_event("문제가 생겼어", line=1), _event("검증 완료", role="assistant", line=2)),
        "atlas",
    )[0]

    with pytest.raises(TypeError, match="PrivateRuntimeContext"):
        plan_private_review_queue_write(tmp_path, episode)
    with pytest.raises(TypeError, match="PrivateRuntimeContext"):
        write_private_review_queue(tmp_path, episode)
    with pytest.raises(ValueError, match="public output root"):
        create_private_runtime_context(tmp_path, public_output_roots=())


@pytest.mark.parametrize("public_kind", ("same", "queue-descendant"))
def test_private_runtime_context_rejects_public_queue_overlap(tmp_path, public_kind):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    public_root = (
        workspace_root
        if public_kind == "same"
        else workspace_root / ".knowledge-worker" / "review-queue" / "public-output"
    )
    public_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="overlap"):
        create_private_runtime_context(workspace_root, public_output_roots=(public_root,))


def test_private_runtime_context_rejects_workspace_nested_under_public_root(tmp_path):
    public_root = tmp_path / "service-output"
    workspace_root = public_root / "runtime"
    workspace_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="overlap"):
        create_private_runtime_context(workspace_root, public_output_roots=(public_root,))


@pytest.mark.parametrize("service_inside_workspace", (True, False))
def test_private_runtime_context_allows_disjoint_service_output_and_private_write(
    tmp_path, service_inside_workspace
):
    workspace_root = tmp_path / "codex"
    service_root = workspace_root / "portfolio-homepage" if service_inside_workspace else tmp_path / "service"
    context = _private_runtime_context(workspace_root, service_root)
    episode = extract_decision_episodes(
        _trace(_event("문제가 생겼어", line=1), _event("검증 완료", role="assistant", line=2)),
        "atlas",
    )[0]

    planned = plan_private_review_queue_write(context, episode)
    assert write_private_review_queue(context, episode, dry_run=True) == ()
    assert not planned.path.exists()
    assert not planned.path.is_relative_to(service_root)
    assert write_private_review_queue(context, episode) == (planned.path,)


def test_public_bundle_reproduction_rejects_context_and_writes_nothing(tmp_path):
    public_service_root = tmp_path / "service-output"
    public_bundle_workspace = public_service_root / "public-bundle"
    public_bundle_workspace.mkdir(parents=True)

    with pytest.raises(ValueError, match="overlap"):
        create_private_runtime_context(
            public_bundle_workspace,
            public_output_roots=(public_service_root,),
        )

    assert not (public_bundle_workspace / ".knowledge-worker").exists()


def test_private_runtime_context_rejects_symlink_workspace_or_public_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    workspace_link = tmp_path / "workspace-link"
    public_link = tmp_path / "public-link"
    workspace_link.symlink_to(target, target_is_directory=True)
    public_link.symlink_to(target, target_is_directory=True)
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(ValueError, match="symlink"):
        create_private_runtime_context(workspace_link, public_output_roots=(target,))
    with pytest.raises(ValueError, match="symlink"):
        create_private_runtime_context(workspace_root, public_output_roots=(public_link,))
