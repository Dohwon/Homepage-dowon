# Task 5 Report: Progressive Graph Interaction UI

## Status

DONE_WITH_CONCERNS

## Implemented

- Replaced the legacy SVG binding with one `bindGraph` controller that owns `initialGraphState`, composes `revealPath` and `expandNode` for search selection, applies `setRelationFilters`, and sends every state projection through `view.update(visibleGraph(...))`.
- Added node search, relation checkboxes, a node-type swatch legend, and 42px lucide `maximize-2` Fit and `rotate-ccw` Reset controls.
- Added a selected-node rail with visible relation type, neighbor label, sanitized public evidence links, and `/projects/<id>` article navigation.
- Added fail-closed WebGL handling. Unsupported capability or renderer construction failure switches to a keyboard-accessible, searchable Focus-rooted hierarchy with project article links.
- Added a fixed 320px desktop detail rail and a single-column mobile layout where the detail panel follows the full-width canvas as a bottom sheet.
- Exposed `prefers-reduced-motion` as `data-reduced-motion` on `#atlas-main` and passes the initial value to the Task 4 renderer adapter.
- Kept the existing global navigation and project tab structure unchanged.
- Updated the render-module test fixture for the new `graph-state.js` import and replaced the remaining SVG-only navigation E2E selector with the search-to-article flow.

## Tests

- `node --test test/client/graph-state.test.js test/client/graph-view.test.js`: PASS, exit 0.
- `npm test`: PASS, 89/89 tests, 0 failed, 0 skipped.
- `node --check client/render.js`: PASS.
- `node --check client/main.js`: PASS.
- `node --check e2e/atlas-graph.spec.js`: PASS.
- `node --check e2e/atlas-navigation.spec.js`: PASS.
- `git diff --check`: PASS.
- `npm run test:ui -- e2e/atlas-graph.spec.js`: BLOCKED before test execution. Under the required 2 GiB process limit, Node failed in Undici startup with `WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory for new instance`.

## TDD Evidence

- The Task 5 E2E contract replaced the old SVG/type-filter expectations before production integration.
- The requested browser RED could not reach assertions because the environment failed during Playwright startup; it was not retried or reported as a product failure.
- Added a Node regression proving the brief's state composition: the unit fixture starts with 3 nodes and search-reveal plus project expansion produces the exact 6-node one-hop neighborhood.
- The first full Node run exposed six render-module fixture failures because the temporary module graph did not include the new `graph-state.js` import. Adding that dependency and rewrite to the fixture produced the final 89/89 gate.

## Self-review

- Search results cover the complete graph index without an arbitrary result cap. Project selection reveals the Focus path, expands the exact allowed one-hop neighborhood, updates the detail rail, and exposes the article link.
- Relation filters retain visible nodes while filtering links and selected relations through Task 3 state semantics. Reset restores initial visibility, all relation checkboxes, empty selection, renderer data, and camera fit.
- The fallback builds one deterministic spanning forest from all Focus roots, renders every reachable node once, preserves disconnected nodes under `기타`, and filters without removing matched ancestors.
- Evidence links pass through `toSafePublicHref`; relative public routes use Atlas navigation and external links are HTTPS-only.
- Fit and Reset retain stable 42px dimensions. The base rail is exactly 320px; the mobile breakpoint switches to one column with no nested cards.
- Static scan found no legacy `setKinds`, SVG graph viewport, type-filter selector, or SVG-node E2E contract.
- Existing untracked `.superpowers/brainstorm/` content was not modified or staged.

## Controller Gate

- Run `npm run test:ui -- e2e/atlas-graph.spec.js` in an environment where Playwright can start within the process policy.
- Desktop 1440x900: verify nonblank WebGL canvas, 320px detail rail, 42px controls, search 4->5 against the current public fixture, relation filtering, evidence link, Fit, Reset, and no overlap.
- Mobile 390x844: verify full-width canvas, detail sheet below the canvas, toolbar wrapping, and no clipping or overlap.
- WebGL-disabled run: verify searchable hierarchy, keyboard traversal, and `/projects/alpha` fallback link.
- Reduced-motion run: verify `data-reduced-motion="true"` and zero-duration focus/Fit behavior from the Task 4 adapter.

## Concerns

- Browser interaction and responsive layout gates remain unexecuted in this worker environment because Playwright startup exceeded the enforced 2 GiB address-space limit.
