# Task 6 Report: Old LLM Wiki Migration Audit and Visual Gate

## Status

DONE_WITH_CONCERNS

## Implemented

- Added `scripts/import_llm_wiki_graph.py` as an audit-only CSV reader. It normalizes the approved six node types and seven base edge types, returns a structured report API, and prints deterministic JSON without writing migration artifacts.
- Rejects `SHARES_FOCUS` and `SHARES_TAG` as name-derived relations. It separately counts unknown project IDs, missing endpoints, raw locator fields, unsupported types, and taxonomy-unmapped nodes.
- Emits reviewed-taxonomy alias suggestions without modifying `data/knowledge-taxonomy.yaml`.
- Added fixture-driven Python coverage for normalization, every required rejection class, stable JSON, forbidden family/similarity output, byte-for-byte source preservation, and no created JSON files.
- Expanded `e2e/atlas-graph.spec.js` with canvas nonblank pixels, desktop/mobile horizontal overflow, `initial < total`, control overlap, zoom, pan, rotate, project-node drag, Fit, Reset, Focus expansion, minimal-path search, Project expansion, relation filtering, reduced motion, project navigation, and WebGL fallback gates.
- Added the stable `data-graph-canvas` hook to the existing graph container and documented the audit-only command and targeted graph E2E command in `README.md`.

## Legacy Audit Result

Command:

```bash
.venv/bin/python scripts/import_llm_wiki_graph.py --source /home/dowon/securedir/git/codex/projects/llm_wiki --taxonomy data/knowledge-taxonomy.yaml --format json
```

- Nodes: `98 accepted`, `0 rejected`, `0 unmapped`; all six canonical node types observed.
- Edges: `681 accepted`, `2772 rejected`, `0 unmapped`; all seven canonical base edge types observed in accepted output.
- Rejected name-derived relations: `SHARES_FOCUS=134`, `SHARES_TAG=2631`.
- Other rejection: `missing_endpoint=7`.
- Suggested taxonomy aliases: `0` for the reviewed current taxonomy.
- The old `nodes.csv`, old `edges.csv`, reviewed taxonomy, and both current bundle graph files retained their pre-audit SHA-256 values.

## TDD Evidence

- RED: focused pytest collection failed with `ModuleNotFoundError: No module named 'scripts.import_llm_wiki_graph'` before the importer existed.
- GREEN: importer tests passed `2/2` after the minimal audit implementation.
- The E2E contract was written before adding `data-graph-canvas`. Browser RED could not reach selectors because Playwright startup exhausted the required 2 GiB address-space limit.

## Tests

- `.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_llm_wiki_graph_import.py -q`: PASS, `44 passed`.
- `.venv/bin/python -m pytest tests/worker -q`: PASS, `785 passed, 1 skipped`.
- `npm test`: PASS, `92 passed`.
- `node --check e2e/atlas-graph.spec.js`: PASS.
- `git diff --check`: PASS.
- `npm ls 3d-force-graph --depth=0`: PASS, exact installed version `1.80.0`.
- Runtime graph/CDN scan across `index.html`, `client/`, vendor script, and `package.json`: zero remote graph/CDN references.
- `npm run test:ui -- e2e/atlas-graph.spec.js`: UNRUN. Node failed in Undici startup before Playwright test execution with `WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory for new instance` under `prlimit --as=2147483648`.

## Completion Gate Audit

- Fixture graph: `project-similarity=0`, `SHARES_FOCUS=0`; progressive graph Node contracts pass.
- Actual `public-bundle/graph/edges.json`: `project-similarity=71`, `SHARES_FOCUS=0`.
- Actual `public-bundle` validation: FAIL, exit `2`, sanitized result `{"error":{"category":"validation","pointer":"$"}}`.
- Initial Focus/Project projection, expansion, minimal path, relation filters, and renderer lifecycle: PASS through Node tests and fixture data.
- Desktop/mobile canvas pixels, control overlap, and real pointer gestures: UNRUN because browser startup failed at the 2 GiB gate.
- Locked local renderer package and no runtime CDN: PASS.

## Self-review

- The importer opens only the two source CSV files and taxonomy for reading. It has no output-path argument and no file write operation.
- Stable JSON uses sorted keys, type lists, count maps, rejection maps, and alias suggestions; it omits source and taxonomy paths.
- Rejection priority gives every row one primary outcome: name-derived relation, raw locator, unknown project, missing endpoint, or unmapped type.
- The E2E interaction test uses rendered pixel deltas for camera controls and a rendered Project-color pixel for node drag instead of asserting only that handlers exist.
- Existing untracked `.superpowers/brainstorm/` content was not modified or staged.

## Concerns

- The actual promoted `public-bundle` does not satisfy the Task 6 zero-similarity completion gate and does not pass current bundle validation. The audit-only importer must not rewrite it; regeneration/promotion from current reviewed sources is separate work.
- Browser assertions remain unexecuted under the required 2 GiB process limit. Do not treat the E2E source contract or non-browser tests as desktop/mobile visual approval.
