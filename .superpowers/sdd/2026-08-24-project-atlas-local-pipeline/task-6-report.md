# Task 6 Report: Idempotent Project Memory and SVG Updates

## Status

Implemented local, evidence-backed Markdown updates and deterministic accessible SVG rendering. Unit tests use only `tmp_path` fixtures; no real workspace project memory was written.

## TDD Evidence

- RED: `.venv/bin/python -m pytest tests/worker/test_visuals.py -v` failed during collection with the expected missing `atlas_worker.memory_writer` module.
- Focused GREEN: the same command passed `9/9`, including a second identical update with no changed files.
- Full suite: `.venv/bin/python -m pytest -v` passed `125` with one existing Linux platform-conditional skip.

## Delivered

- `update_project_memory()` selects only `>= 0.85` decision, rollback, revision, and resolved-failure claims. It routes each claim to the matching Markdown file and never creates evidence-free files.
- Managed event blocks use stable evidence IDs, replace matching blocks in place, append new blocks in deterministic order, report normalized relative paths, and preserve un-managed bytes except for required append separators.
- Malformed, duplicate, nested, mismatched, or unbalanced Atlas markers raise before a write plan is committed. Dry runs compute the same stable changes without directory creation or file writes.
- `render_problem_solving_svg()` emits fixed Constraint, Attempt, Revision, Decision, and Result nodes with stable IDs, title/description accessibility linkage, light/dark CSS variables, deterministic wrapping, XML escaping, local-path redaction, and no executable or external-resource markup.

## Coverage

Focused tests cover selective file creation, managed-text preservation, replacement, malformed and duplicate marker fail-safe behavior, no-write dry runs, review-only rejection, second-run idempotence, routing, SVG XML parsing, accessibility metadata, ordering, escaping, local-path exclusion, and active/external markup exclusion.

## Concerns

The writer intentionally retains local Atlas control comments. Task 8 must strip those comments before public rendering and run the privacy gate on the resulting artifact.

## Fix Round 1

### RED

- `.venv/bin/python -m pytest tests/worker/test_visuals.py tests/worker/test_backfill.py tests/worker/test_memory.py -v` failed `12` checks as intended. The failures reproduced EOF insertion after `## References`, loss of decision/revision events after the real backfill-to-merge boundary, absence of explicit selection, incomplete root-path redaction, and the ineffective event-attribute regex.

### GREEN

- New managed blocks now enter the single exact target H2 before the next H1/H2. Duplicate target headings and unmatched fenced Markdown fail safely before any write; missing target H2 still creates a new target section at EOF.
- Backfill history fields are now `history:<evidence_id>`, so `merge_claims()` retains every distinct historical event while existing field-based precedence remains backward-compatible for non-history claims.
- `EvidenceClaim.selected` is a local-only, default-false signal. The writer accepts a selected review claim or an automatic `>= 0.85` claim; unselected review claims remain unwritten. It is not part of public project serialization.
- SVG text redaction now handles root and delimiter-adjacent POSIX/Windows/UNC paths while preserving ordinary HTTP(S) text. The event-attribute assertion uses a real word-boundary/whitespace regex and a matching `onload` probe.

### Verification

- Focused suite: `.venv/bin/python -m pytest tests/worker/test_visuals.py tests/worker/test_backfill.py tests/worker/test_memory.py -v` passed `88/88`.
- Full suite: `.venv/bin/python -m pytest -v` passed `129` with one existing Linux platform-conditional Windows case-semantics skip.

### Self-Review

- Confirmed generated Markdown inserts before a later References H2 and leaves surrounding user text unchanged except for required insertion separators.
- Confirmed the e2e test uses actual `extract_signal_claims()` output, then `merge_claims()`, rather than synthetic winner keys; decision, revision, and rollback reach their respective files.
- Confirmed `selected` is absent from `PublicProject.to_dict()` and neither the writer nor tests touch a real project memory path.
