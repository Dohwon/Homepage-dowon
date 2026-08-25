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
