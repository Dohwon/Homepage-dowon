# Task 2 Fix Round 1 Report

## Status

DONE

## Review Findings Resolved

### HIGH: Hidden Artifact survives through a shared tag

- Replaced undirected reachability filtering with semantic ownership filtering.
- An `Artifact` survives only when a visible project owns it through `PRODUCES_ARTIFACT`.
- A `Technology` survives only when a visible project references it through `USES_TECH`.
- `KnowledgeTag` retention starts from visible-project `HAS_TAG` and retained-Artifact `ARTIFACT_HAS_TAG` edges, then retains required parent tags through a fixed-point `HAS_SUBTAG` walk.
- `KnowledgeFocus` and `KnowledgeDomain` remain unconditional fallback navigation nodes.
- Regression covers a hidden Artifact connected to a tag shared by a visible project, plus an Artifact-only child/parent tag chain. The Artifact and dependent chain are removed while the visible shared tag remains.

### HIGH: Production CLI discards curated relations

- Added a confined, no-follow loader for each project's `project_memory/project-atlas/relations.yaml`.
- The loader accepts the `relations` list alongside the existing predecessor metadata keys, enforces exact relation fields, permits only `EVOLVED_FROM`, `VALIDATES`, `DEPLOYS`, and `REUSES_COMPONENT`, and requires non-empty unique evidence IDs.
- Production CLI now gathers relations by source project and passes them to `build_knowledge_graph()`.
- Curated relation records are included in the project source hash.
- CLI integration regression builds an `EVOLVED_FROM` edge and verifies the exact public evidence link.
- Loader regressions reject `project-similarity`, empty evidence IDs, and unknown relation fields.

### HIGH: Actual legacy V1 graph is rejected

- Python bundle validation now chooses the legacy validator only for `format_version: 1` and keeps the strict KG validator for V2.
- Restored the legacy exact node/edge shapes, kind allowlists, canonical membership graph, similarity scoring, deterministic selection, and degree checks for one release.
- Node store now selects separate V1 and V2 record validators and uses a legacy hidden-project filter for V1.
- Regression fixtures use actual old node fields `id,label,kind` and edge fields `source,target,kind,weight,reasons`, including a legacy `project-similarity` edge.
- Separate regressions confirm V2 still rejects the legacy record shape.

### MEDIUM: Node evidence label accepts generic POSIX paths

- Node KG edge validation now rejects generic POSIX absolute paths in evidence labels while masking public HTTPS URL text before path classification.
- Regression confirms `/etc/atlas/private.txt` rejects the entire graph as `invalid_atlas_graph_edge`.

## TDD Evidence

- Initial Python regression run: `2 failed, 1 passed`.
  - V1 failed on missing KG-only node fields.
  - CLI relation test failed because no `EVOLVED_FROM` edge was produced.
- Initial Node store run: `17 passed, 3 failed`.
  - Actual V1 records failed with `invalid_atlas_graph_node`.
  - Generic POSIX evidence label was accepted.
  - Hidden Artifact survived through the shared tag.
- Focused GREEN:
  - Python V1/V2/CLI relation: `3 passed`.
  - Relation loader strict cases: `3 passed`.
  - Node store: `20 passed`.

## Verification

- Python worker suite with resource limits: `783 passed, 1 skipped`.
- Node non-loopback suite: 8 test files passed, including all 20 Atlas store subtests.
- `node --check lib/atlas-store.js`: passed.
- `git diff --check`: passed.
- Per instruction, `test/server/atlas-api.test.js` was not run because it opens a loopback server. The controller must run the elevated combined store/API gate.

## Self-review

- V1 and V2 validators are selected only from explicit manifest `format_version`; V2's exact KG allowlists and rehashed similarity rejection remain unchanged.
- V1 compatibility includes actual legacy similarity records, not only a V1 manifest wrapped around V2 data.
- Relation files are read within each project root with symlink rejection and a 256 KiB bound; missing files produce no relations.
- Relation kind and evidence checks exist both at load time and in the Task 1 projector boundary.
- Hidden filtering removes hidden-project incident edges before ownership evaluation. Removed Artifact edges cannot keep tags alive, and parent-tag retention reaches a fixed point only from visible seeds.
- Internal `formatVersion` is used for store filtering but is not returned by public bootstrap, project, graph, or search responses.
- Existing `.superpowers/brainstorm/` remains untracked and is excluded from staging.

## Concerns

None. The controller-owned loopback store/API gate remains intentionally unrun in this session.
