# Task 2 Report: Public KG Bundle and Store/API Validation

## Status

DONE

## Implemented

- Public bundle generation now serializes the Task 1 KG contract exactly:
  - node: `id`, `label`, `kind`, `url`, `summary`
  - edge: `id`, `source`, `target`, `kind`, `weight`, `evidence_links`
- CLI public builds now use `build_knowledge_graph()` with the reviewed taxonomy instead of the legacy similarity graph builder.
- Python bundle validation and Node store validation use the Task 1 node/edge kind allowlists, validate canonical edge IDs and endpoints, and cross-check every `Project` node against its public project record.
- `project-similarity` is outside both allowlists. A rehashed candidate containing that edge kind fails with `graph-edge-kind` before promotion.
- Graph node URLs and relation `evidence_links` are validated as public URLs. Allowed relation evidence is preserved unchanged through bundle and store/API output.
- CMS-hidden projects remove their project node and every incident edge. A reachability pass then removes disconnected `Artifact`, `Technology`, and `KnowledgeTag` nodes while retaining curated `KnowledgeFocus` and `KnowledgeDomain` nodes.
- Fixture graph records and manifest metadata were migrated to the KG contract.

## Test Evidence

- RED evidence before implementation:
  - Python focused: `3 failed, 241 passed`
  - Node store fixture: rejected with `invalid_atlas_graph_node`
- Final required gates, rerun by the controller against the working changes:
  - Python focused: `380 passed, 1 skipped`
  - Elevated Node store + API: `29/29 passed`
- Per controller instruction, no additional network or loopback test was rerun after those gates.
- Offline fixture integrity after the final manifest refresh:
  - `hashes_match=True`
  - `version_match=True`
  - version: `a3470656b7815d31fd5a1f75de9bb0e67137c9d0b75e68bbf01e00912b7efeb2`
- Diff hygiene: `git diff --check` passed.

## Self-review

- Exact public record fields are enforced independently in Python and Node; unknown fields are rejected.
- Similarity rejection is based on the edge-kind contract, so recomputing fixture hashes cannot bypass it.
- Duplicate node IDs, duplicate edge IDs/directed identities, self edges, dangling endpoints, noncanonical edge IDs, unsafe node URLs, and unsafe evidence URLs are rejected.
- Project node ID, label, URL, and summary are checked against the public project payload in both validation layers.
- Evidence links survive serialization and Node store cloning; tests assert their exact label and URL.
- Hidden-project filtering removes incident edges first, computes reachability from visible projects, and prunes only the three specified orphanable kinds. Focus and Domain fallback navigation remains stable.
- Privacy scanning still rejects actual absolute paths in KG labels while permitting taxonomy display labels containing a spaced slash.
- The fixture manifest hashes and content-derived version were recomputed after graph fixture changes; store/API version assertions were synchronized.
- Reviewed the full changed-file list and diff. `.superpowers/brainstorm/` remains untracked and is excluded from staging.

## Concerns

None. The final Node gate evidence is controller-provided because this session was explicitly instructed not to rerun network/loopback tests.
