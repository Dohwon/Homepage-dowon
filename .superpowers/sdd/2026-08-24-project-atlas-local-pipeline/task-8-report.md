# Task 8 Report: Atomic Public Bundle and Incremental Manifest

## Status

Implemented the sole local-to-public filesystem boundary with deterministic rendering, complete privacy/schema validation, content-derived manifests, no-op detection, per-project change reporting, and rename rollback. Tests use only `tmp_path`; the real `public-bundle/` was not read or written.

## TDD Evidence

- Initial RED: `.venv/bin/python -m pytest tests/worker/test_bundle.py -v` failed during collection because `atlas_worker.bundle` did not exist.
- Boundary RED: empty optional Markdown was accepted before the non-empty artifact check was added.
- Full-tree RED: a leaked value in an earlier duplicate JSON key was lost by normal dict parsing before privacy validation.
- Focused GREEN: `.venv/bin/python -m pytest tests/worker/test_bundle.py -v` passed `21/21`.
- Focused regression: model/privacy/bundle coverage passed `45` with `1` Linux platform-conditional skip before the final two bundle cases were added.
- Full suite, run once after code freeze: `.venv/bin/python -m pytest -v` passed `165` with `1` existing Linux platform-conditional skip.

## Delivered

- `BundleContext` carries public projects, structured memories/events, graph data, typed search documents, source hashes, previous manifest, and the `PrivacyGate` used at every rendered artifact boundary.
- Candidate builds delete and recreate safe staging roots, render only the allowlisted JSON/Markdown/SVG layout, strip only exact Atlas managed-comment lines, omit empty optional files, and perform both per-artifact and complete-tree privacy scans.
- Public projects and manifest payloads use their JSON Schemas. Graph, topic, changelog, search, SVG XML, exact file layout, UTF-8, SHA-256 map, and symlink constraints are validated before promotion.
- `BundleManifest.to_dict()` emits exactly `version`, `projects`, and `files`; local `project_hashes` remain available on the typed result without entering public JSON.
- JSON bytes, newlines, project/graph/path ordering, file hashes, project hashes, and version derivation are deterministic and contain no wall-clock values. Source paths affect only the one-way version hash and are never rendered.
- Promotion loads, privacy-scans, and validates the entire candidate before touching public state. Identical trees preserve the existing public inode and bytes.
- Changed project IDs include added, modified, and removed project subtrees in sorted order. Existing bundles use `.public-bundle.previous` during same-filesystem rename and are restored after an injected candidate rename failure.

## Coverage

Tests cover first publish, added/changed/removed project reporting, deterministic manifests and bytes, rebuild-from-empty, exact managed-comment stripping, arbitrary-comment blocking, duplicate-key full-tree scanning, staging/candidate symlink rejection, schema and unexpected-file failures, file hashes, mtime-independent tree hashes, rename rollback, stale backup refusal, no-op inode preservation, and local path/session/provenance/key exclusion.

## Concerns

- A pre-existing `.public-bundle.previous` blocks changed promotion rather than being overwritten. Task 9 should surface this as an explicit local recovery condition.
- Task 9 must place staging on the same filesystem as `public_dir` and provide SHA-256 source hashes; cross-filesystem promotion fails before public state changes.

## Commit

`feat: build atomic public atlas bundles`

## Fix Round 1

### Status

Resolved all three Critical and both Important review findings. The implementation and tests used only `tmp_path`; the real `public-bundle/` was not read or written.

### TDD Evidence

- Privacy RED: eight newly required POSIX/Windows/UNC forms passed through the narrow detector; builder and promotion coverage now blocks all listed families without leaking values in errors.
- Ancestor-symlink RED: promotion followed a symlinked staging parent and the public no-op path hashed through a symlinked ancestor; both paths now fail before reads or hashes.
- Rollback RED: injected recovery-copy, recovery-rename, and cleanup failures exposed incomplete recovery handling. Recovery now copies only to a same-parent temp, validates and hashes it, atomically renames it, and retains the original backup until success.
- Incremental/version RED: `previous_manifest` had no effect and arbitrary manifest versions promoted. Local changed-project metadata and one recomputable public-content version function now cover both build and promotion.
- Self-review RED: a rename precondition `ValueError` skipped rollback, and an internally rehashed prior manifest with an impossible public file was accepted. Both cases now have regression tests.
- Focused GREEN: `.venv/bin/python -m pytest tests/worker/test_bundle.py tests/worker/test_privacy.py -q` passed `90` with `1` Linux platform-conditional skip.
- Full suite, run once after code freeze: `.venv/bin/python -m pytest -v` passed `218` with `1` Linux platform-conditional skip.

### Delivered Fixes

- Absolute-path privacy detection covers root and arbitrary POSIX paths, delimiter-adjacent paths, all drive-rooted Windows paths, and UNC paths while excluding ordinary HTTP(S) URLs and exact public project routes. Findings expose only category and JSON pointer.
- Existing components of staging, public, backup, and recovery paths are checked with `lstat` before tree reads, hashes, no-op decisions, copies, cleanup, and atomic renames. Tree walks reject every symlink without following it.
- Promotion preserves either a complete live tree or the intact last-good backup at every injected rename/copy/cleanup failure. It never copies directly into the live name while backup is the only valid tree.
- `BundleManifest.changed_projects` is local-only. A validated prior baseline produces deterministic added, modified, removed, or unchanged results; stale hashes, versions, IDs, missing files, and unexpected paths are rejected explicitly.
- `content_version()` uses only validated public file hashes and derived project subtree hashes. Builder and promotion share the calculation; `manifest.json` remains excluded from `files`. This supersedes the earlier report statement that source hashes affect the version.

### Self-Review

Verified exact public serialization and layout, no-follow operation ordering, rollback state invariants, prior-manifest consistency checks, content-version recomputation, stable ordering/newlines, and absence of direct live recovery copies. `git diff --check` and Python bytecode compilation passed before the full suite.

### Concerns

- A stale `.public-bundle.previous` or `.public-bundle.recovery` remains an explicit operator recovery condition and blocks changed promotion deterministically.
- Cross-filesystem promotion remains intentionally rejected before public state changes.
