# Task 5 Report: Streaming Session Mapping and Selective Backfill

## Status

Implemented local-only session normalization, deterministic project mapping, checksum cursor helpers, and selective signal extraction. This task does not write project memory or `session-cursor.json`.

## TDD Evidence

- RED: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v` failed during collection with the expected missing `atlas_worker.sessions` and `atlas_worker.backfill` modules.
- Focused GREEN: the same command passed `12/12` after the minimal implementation.
- Full suite: `.venv/bin/python -m pytest -v` passed `61/61` with one existing Linux platform-conditional Windows case-semantics skip.

## Delivered

- `iter_session_events()` opens JSONL once and yields line-by-line. It normalizes only `session_meta`, `turn_context`, and message-style `response_item` records; malformed JSON produces an `invalid_json` event containing only local source pointer and line number.
- `map_session()` normalizes separators and dot segments, considers current roots and explicit historical aliases, chooses the deepest matching component prefix deterministically, and never uses substring matching.
- `content_checksum()`, `should_skip_session()`, and `updated_cursors()` use chunked SHA-256 hashing and only in-memory cursor mappings.
- `extract_signal_claims()` emits normalized, non-verbatim values. Evidence IDs hash session metadata, timestamp, local source pointer, line number, and claim type; raw event text is excluded.
- Confidence routing is explicit: rollback `0.95`, confirmed correction `0.90`, resolved failure/architecture decision `0.85`, review-level revision/unresolved failure `0.75`, and no claim from session length or routine turns.

## Coverage

Tests cover a generated 10,000-line fixture, malformed-line sanitization, retained record shapes, historical aliases, longest component match, substring rejection, checksum skip, no cursor-file write, raw-text exclusion, deterministic evidence IDs, and automatic/review/ignored confidence boundaries.

## Concerns

Session text remains only inside transient `SessionEvent` values while extraction runs. Later tasks must preserve the normalized `EvidenceClaim` boundary and must not serialize session text or local source pointers into public artifacts.

## Fix Round 1

### RED

- `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v` failed five regression checks as intended: cross-session/user-only confirmation promoted claims, generic decision and single unverified signals emitted claims, repeated revisions emitted three claims, equivalent Windows pointers hashed differently, and `tuple(events)` retained the 16 MB raw-event fixture.

### GREEN

- `extract_signal_claims()` is now an incremental bounded-memory state machine. It holds at most 128 active `(session_id, normalized_cwd)` contexts and 64 normalized edit targets per context; pending records retain only session metadata, timestamps, local source pointers, and line numbers.
- `.85` failure resolution and `.90` correction confirmation require the same non-empty session/cwd context and a later `assistant` or `tool` result. Cross-session, cross-cwd, user-only, and metadata-incomplete inputs do not auto-promote.
- `.85` decisions require committed architecture wording and reject questions, negations, and quoted text. `.75` revision claims require three same-target revisions or explicit multiple visual alternatives; a single revision/failure no longer creates memory.
- Evidence hashes now use lexical path canonicalization with dot-segment collapse, slash normalization, and Windows drive-case folding, without filesystem resolution.
- Added cursor immutability/hash coverage and direct `ProjectRef.aliases` mixed-separator nested-cwd coverage.

### Verification

- Focused suite: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v` passed `19/19`.
- Full suite: `.venv/bin/python -m pytest -v` passed `68/68` with one existing Linux platform-conditional Windows case-semantics skip.

### Self-Review

- Confirmed no `tuple(events)` or raw-text field occurs in pending state, no filesystem path resolution is used by evidence normalization, and qualification is scoped by session plus normalized cwd before automatic confidence is emitted.

## Fix Round 2

### RED

- The focused suite reproduced the unresolved polarity defect: `"이 아키텍처를 채택하기로 결정하지 마"` emitted an auto-eligible decision, while direct declarative adoption was not recognized.
- A follow-up RED check established that direct adoption with terminal punctuation (`"Y를 채택한다."`) was excluded by the prior boundary regex.

### GREEN

- Decision candidate recognition now includes English decision/adoption/selection equivalents, but auto-eligibility requires commitment plus architecture context or a direct Korean adoption declaration.
- A dedicated non-commitment guard rejects Korean imperative/negative/deferred forms (`결정하지 마`, `선택하지 않음`, `아직 결정 안 함`, `보류`), equivalent English negative/question/defer forms, and straight, curly, CJK, and backtick quotes.
- Positive regressions retain exactly `0.85` for `아키텍처는 X로 결정했다`, punctuated `Y를 채택한다.`, and a committed architecture trade-off decision.

### Verification

- Focused suite: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v` passed `21/21`.
- Full suite: `.venv/bin/python -m pytest -v` passed `70/70` with one existing Linux platform-conditional Windows case-semantics skip.

### Self-Review

- Reviewed commitment, direct-adoption, non-commitment, and quote guards together. Negative/deferred/question/quoted text is rejected before a decision claim is emitted; only declarative commitments remain eligible.

## Fix Round 3

### RED

- The focused suite reproduced punctuation-free English interrogative auto-promotion with `Do we adopt this architecture`; positive coverage also exposed that `We adopted X for the architecture` was not recognized as a decision signal.

### GREEN

- The non-commitment guard now rejects leading English auxiliary questions (`do/does/did/should/can/could/would/will/may/might/is/are`) and WH questions (`which/what/who/where/when/why/how`) when they contain decision language, independent of trailing punctuation.
- Korean terminal question endings (`나요`, `가요`, `까요`, `습니까`, `인가요`) now exclude decision claims without requiring `?`.
- Decision signal recognition covers English committed inflections and choice terms. Positive `.85` coverage preserves architecture decisions, direct Korean adoption, committed trade-offs, `We adopted X for the architecture`, and `Choose X as the architecture`.

### Verification

- Focused suite: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v` passed `22/22`.
- Full suite: `.venv/bin/python -m pytest -v` passed `71/71` with one existing Linux platform-conditional Windows case-semantics skip.

### Self-Review

- Confirmed interrogative rules are anchored to leading English auxiliary/WH constructions or Korean terminal endings, while declarative English adoption and explicit architecture choice statements remain eligible.

## Fix Round 4

### RED

- Command: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v`
- Exit code: `1`
- Exact output: `========================= 3 failed, 38 passed in 1.35s =========================`
- Failures: `Have we selected X for the architecture` and `Has the architecture adopted X` each emitted a `0.85` decision claim; `We chose X after evaluating the trade-off` emitted no decision claim.

### GREEN

- Replaced the piecemeal auxiliary/WH branches with one sentence-leading English interrogative guard covering BE, DO, HAVE, modal, and WH forms independent of punctuation.
- Added irregular `chose`/`chosen` commitment recognition and explicit trade-off decision context while retaining the existing Korean non-commitment, question, and quote guards.
- Command: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v`
- Exit code: `0`
- Exact output: `============================== 41 passed in 1.27s ==============================`

### Full Suite

- Command: `.venv/bin/python -m pytest -v`
- Exit code: `0`
- Exact output: `======================== 90 passed, 1 skipped in 1.42s =========================`
- Skip: existing Linux platform-conditional Windows case-semantics test.

### Self-Review

- Confirmed the interrogative guard is anchored at sentence start, contains every requested BE, DO, HAVE, modal, and WH lead, and does not reject declarations merely containing those words later.
- Confirmed the diff leaves session streaming, cursor handling, confidence routing, and privacy boundaries unchanged.
