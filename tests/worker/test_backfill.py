from atlas_worker.backfill import (
    automatic_merge_claims,
    content_checksum,
    extract_signal_claims,
    review_claims,
    should_skip_session,
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


def test_failure_followed_by_pass_and_architecture_choice_reach_auto_merge_threshold():
    failure_claim = extract_signal_claims(
        (make_session_event("테스트 실패"), make_session_event("테스트 통과", session_id="s2"))
    )[0]
    decision_claim = extract_signal_claims((make_session_event("이 아키텍처를 채택하기로 결정"),))[0]

    assert failure_claim.confidence == 0.85
    assert decision_claim.confidence == 0.85
    assert automatic_merge_claims((failure_claim, decision_claim)) == (failure_claim, decision_claim)


def test_confirmed_correction_reaches_the_higher_auto_merge_confidence():
    claim = extract_signal_claims(
        (
            make_session_event("다시 수정해", session_id="s1"),
            make_session_event("수정 완료", session_id="s1"),
        )
    )[0]

    assert claim.confidence == 0.90
    assert automatic_merge_claims((claim,)) == (claim,)


def test_confidence_boundaries_keep_revision_for_review_and_ignore_session_length():
    revision_claim = extract_signal_claims((make_session_event("다른 시안으로 재설계해"),))[0]
    routine_events = tuple(make_session_event(f"routine {index}", session_id=str(index)) for index in range(100))
    low_confidence_claim = EvidenceClaim("history", "unverified", "session", 0.59, "low")

    assert revision_claim.confidence == 0.75
    assert review_claims((revision_claim,)) == (revision_claim,)
    assert automatic_merge_claims((revision_claim,)) == ()
    assert review_claims((low_confidence_claim,)) == ()
    assert automatic_merge_claims((low_confidence_claim,)) == ()
    assert extract_signal_claims(routine_events) == ()
