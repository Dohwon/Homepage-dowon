# Task 7 Report: Evidence-Backed Taxonomy and Bounded Graph

## Status

Implemented deterministic local tag selection and public graph generation. Tag evidence and decisions remain local metadata; graph nodes, edges, and similarity reasons contain only public project/tag values.

## TDD Evidence

- RED: `.venv/bin/python -m pytest tests/worker/test_taxonomy_graph.py -v` failed during collection because `atlas_worker.graph` did not exist.
- Additional RED: canonical-ID neighbor lookup failed `1` test when raw project IDs were compared with encoded graph IDs.
- Focused GREEN: `.venv/bin/python -m pytest tests/worker/test_taxonomy_graph.py -v` passed `13/13`.
- Full suite: `.venv/bin/python -m pytest -v` passed `142` with `1` existing Linux platform-conditional skip.

## Delivered

- `TagCandidate.decision` is backward-compatible (`infer` by default) and represents explicit local profile `approve` and `reject` decisions.
- `select_tags()` retains existing `project.tags` as manual baseline, normalizes identity with Unicode NFKC/case/whitespace handling, removes profile rejections, and requires two distinct source classes plus evidence IDs for inferred tags.
- Candidate limits use deterministic evidence ranking; missing required semantic support raises a local `not public-ready` `ValueError` rather than creating filler tags.
- `build_graph()` emits canonical typed project/tag nodes, deduplicated membership edges, positive weighted similarities, and stable aggregated `kind:label` reasons.
- Similarity edge selection is globally score-ordered and degree-bounded, so every project has at most five graph edges rather than merely a five-item read-time slice.

## Coverage

Focused tests cover source threshold, manual approve/reject, single-source and duplicate-ID rejection, deterministic limits/order, required-tag failure, unknown metadata, normalized scoring, node canonicalization, reason aggregation, zero-score omission, canonical neighbor lookup, and graph-wide degree bounds.

## Concerns

The taxonomy accepts only the existing `SOURCE_PRIORITY` classes and requires profile as the source class for explicit decisions. Project metadata/profile loading must emit those exact strings before Task 8 consumes selected tags.
