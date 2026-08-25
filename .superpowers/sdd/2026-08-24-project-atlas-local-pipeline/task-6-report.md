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
