import tracemalloc

from atlas_worker.backfill import (
    automatic_merge_claims,
    content_checksum,
    extract_signal_claims,
    review_claims,
    should_skip_session,
    updated_cursors,
)
from atlas_worker.models import EvidenceClaim
from tests.worker.helpers import make_session_event


def test_unchanged_checksum_skips_session_without_persisting_a_cursor_file(tmp_path):
    session_path = tmp_path / "session.jsonl"
    session_path.write_text('{"type": "session_meta"}\n', encoding="utf-8")
    checksum = content_checksum(session_path)
    cursors = {str(session_path): checksum}

    assert should_skip_session(session_path, cursors)

    session_path.write_text('{"type": "session_meta"}\n{"type": "turn_context"}\n', encoding="utf-8")
    assert not should_skip_session(session_path, cursors)
    assert not (tmp_path / "session-cursor.json").exists()


def test_updated_cursors_returns_hashes_without_mutating_input(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    cursors = {"existing": "checksum"}

    updated = updated_cursors((first, second), cursors)

    assert cursors == {"existing": "checksum"}
    assert updated == {
        "existing": "checksum",
        str(first): content_checksum(first),
        str(second): content_checksum(second),
    }


def test_routine_turn_is_ignored_but_rollback_is_selected_without_raw_text_retention():
    raw_text = "새 시안 말고 이전 탐색 구조로 롤백해"
    claims = extract_signal_claims(
        (make_session_event("파일 목록 보여줘"), make_session_event(raw_text, session_id="s2"))
    )

    assert [claim.claim_type for claim in claims] == ["rollback"]
    assert claims[0].value == "rollback requested"
    assert raw_text not in repr(claims[0])


def test_evidence_id_is_deterministic_metadata_hash_not_raw_text():
    first = make_session_event("이전 시안으로 롤백해", session_id="s1")
    second = make_session_event("rollback and add private wording", session_id="s1")

    first_claim = extract_signal_claims((first,))[0]
    second_claim = extract_signal_claims((second,))[0]

    assert first_claim.evidence_id == second_claim.evidence_id
    assert len(first_claim.evidence_id) == 64


def test_same_session_assistant_pass_and_committed_architecture_choice_reach_auto_merge_threshold():
    failure_claim = extract_signal_claims(
        (
            make_session_event("테스트 실패", line_number=1),
            make_session_event("테스트 통과", role="assistant", line_number=2),
        )
    )[0]
    decision_claim = extract_signal_claims((make_session_event("이 아키텍처를 채택하기로 결정"),))[0]

    assert failure_claim.confidence == 0.85
    assert decision_claim.confidence == 0.85
    assert automatic_merge_claims((failure_claim, decision_claim)) == (failure_claim, decision_claim)


def test_confirmed_correction_reaches_the_higher_auto_merge_confidence():
    claim = extract_signal_claims(
        (
            make_session_event("다시 수정해", session_id="s1"),
            make_session_event("수정 완료", session_id="s1", role="assistant"),
        )
    )[0]

    assert claim.confidence == 0.90
    assert automatic_merge_claims((claim,)) == (claim,)


def test_cross_session_and_user_only_confirmations_do_not_promote_claims():
    cross_session_failure = extract_signal_claims(
        (
            make_session_event("테스트 실패", session_id="s1"),
            make_session_event("테스트 통과", session_id="s2", role="assistant"),
        )
    )
    user_only_revision = extract_signal_claims(
        (
            make_session_event("다시 수정해", session_id="s1"),
            make_session_event("수정 완료", session_id="s1"),
        )
    )
    cross_project_failure = extract_signal_claims(
        (
            make_session_event("테스트 실패", session_id="s3", cwd="/workspace/projects/alpha"),
            make_session_event(
                "테스트 통과",
                session_id="s3",
                cwd="/workspace/projects/beta",
                role="assistant",
            ),
        )
    )

    assert cross_session_failure == ()
    assert user_only_revision == ()
    assert cross_project_failure == ()


def test_generic_decision_question_and_unverified_single_signals_are_ignored():
    claims = extract_signal_claims(
        (
            make_session_event("대안 중 무엇을 선택할까?"),
            make_session_event("테스트 실패"),
            make_session_event("다시 수정해"),
        )
    )

    assert claims == ()


def test_negative_deferred_and_quoted_decision_language_is_ignored():
    negative_texts = (
        "이 아키텍처를 채택하기로 결정하지 마",
        "아키텍처는 선택하지 않음",
        "아직 아키텍처 결정 안 함",
        "아키텍처 결정 보류",
        "We decide not to adopt this architecture",
        "Should we decide to adopt this architecture?",
        "The architecture trade-off decision is deferred",
        "「아키텍처는 X로 결정했다」",
        "`아키텍처는 X로 결정했다`",
    )

    for index, text in enumerate(negative_texts):
        assert extract_signal_claims((make_session_event(text, session_id=f"negative-{index}"),)) == ()


def test_punctuation_free_english_and_korean_questions_are_ignored():
    question_texts = (
        "Do we adopt this architecture",
        "Should we choose X as the architecture",
        "Can we select Y for the architecture",
        "Which alternative do we choose for the architecture",
        "아키텍처를 채택하기로 결정해도 되나요",
    )

    for index, text in enumerate(question_texts):
        assert extract_signal_claims((make_session_event(text, session_id=f"question-{index}"),)) == ()


def test_committed_architecture_direct_adoption_and_tradeoff_decisions_remain_auto_eligible():
    claims = tuple(
        extract_signal_claims((make_session_event(text, session_id=f"positive-{index}"),))[0]
        for index, text in enumerate(
            (
                "아키텍처는 X로 결정했다",
                "Y를 채택한다.",
                "아키텍처 trade-off를 검토한 뒤 X로 결정했다",
                "We adopted X for the architecture",
                "Choose X as the architecture",
            )
        )
    )

    assert [claim.claim_type for claim in claims] == ["decision"] * 5
    assert [claim.confidence for claim in claims] == [0.85] * 5


def test_three_same_target_revisions_and_multiple_visual_alternatives_are_review_candidates():
    repeated_claims = extract_signal_claims(
        (
            make_session_event("atlas_worker/backfill.py 다시 수정해", line_number=1),
            make_session_event("atlas_worker/backfill.py 다시 수정해", line_number=2),
            make_session_event("atlas_worker/backfill.py 다시 수정해", line_number=3),
        )
    )
    visual_claims = extract_signal_claims((make_session_event("두 시안의 visual alternatives를 비교해"),))

    assert [claim.confidence for claim in repeated_claims] == [0.75]
    assert [claim.value for claim in repeated_claims] == ["revision corroborated"]
    assert [claim.confidence for claim in visual_claims] == [0.75]
    assert review_claims(repeated_claims + visual_claims) == repeated_claims + visual_claims


def test_confidence_boundaries_keep_revision_for_review_and_ignore_session_length():
    revision_claim = extract_signal_claims((make_session_event("여러 시안으로 재설계해"),))[0]
    routine_events = tuple(make_session_event(f"routine {index}", session_id=str(index)) for index in range(100))
    low_confidence_claim = EvidenceClaim("history", "unverified", "session", 0.59, "low")

    assert revision_claim.confidence == 0.75
    assert review_claims((revision_claim,)) == (revision_claim,)
    assert automatic_merge_claims((revision_claim,)) == ()
    assert review_claims((low_confidence_claim,)) == ()
    assert automatic_merge_claims((low_confidence_claim,)) == ()
    assert extract_signal_claims(routine_events) == ()


def test_equivalent_windows_source_paths_produce_the_same_evidence_id():
    first = make_session_event(
        "이전 시안으로 롤백해",
        source_path=r"C:\\Sessions\\old\\..\\s1.jsonl",
    )
    second = make_session_event(
        "rollback",
        source_path="c:/sessions/s1.jsonl",
    )

    assert extract_signal_claims((first,))[0].evidence_id == extract_signal_claims((second,))[0].evidence_id


def test_extractor_does_not_retain_the_full_raw_event_stream():
    def events():
        for index in range(2_000):
            yield make_session_event("routine " + ("x" * 8_000), session_id=str(index))

    tracemalloc.start()
    try:
        claims = extract_signal_claims(events())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert claims == ()
    assert peak < 4_000_000
