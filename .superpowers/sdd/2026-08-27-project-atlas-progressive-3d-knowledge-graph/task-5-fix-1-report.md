# Task 5 Fix Round 1 Report

## Status

DONE

## Fixed

### HIGH: HTML-capable graph tooltip label

- Replaced the `nodeLabel` string result with a real `span` created through the browser document.
- Assigns API-controlled label content only through `textContent`, so HTML-shaped labels remain literal text and never enter the dependency's `innerHTML` branch.
- Returns an empty label when DOM element creation is unavailable.

### MEDIUM: Error route lifecycle cleanup

- Added one `cleanupActiveRoute()` path shared by normal route rendering and `renderError()`.
- Clears `root.__atlasCleanup` before invoking it, then allows graph listener removal, `view.destroy()`, `ResizeObserver.disconnect()`, renderer disposal, and DOM replacement to occur in order.
- Repeated error rendering cannot invoke the prior route cleanup twice.

### MEDIUM: Live reduced-motion propagation

- Added `view.setReducedMotion()` without recreating the graph, preserving the active graph state and renderer data.
- A live no-preference to reduce change updates cooldown/warmup policy and alpha decay, and makes every subsequent node focus and Fit operation use a zero-millisecond duration.
- `main.js` continues to update `data-reduced-motion` and now dispatches the live value to the bound graph view. The route cleanup removes this listener.

## Regression Tests

- HTML-shaped label regression verifies `nodeLabel` returns an object whose `textContent` is the exact literal payload and has no child markup.
- Error rendering regression verifies active cleanup runs before DOM replacement and the callback is cleared.
- Live motion regression starts with animation enabled, applies `setReducedMotion(true)`, and verifies focus and Fit duration are both `0` with reduced simulation settings.
- Graph E2E contract now changes media preference after `/graph` is already loaded and checks the live data hook transition from `false` to `true`.

## TDD Evidence

- Tooltip RED: expected an object but received the unsafe HTML-capable string.
- Reduced-motion RED: `view.setReducedMotion` did not exist.
- Error cleanup RED: observed only DOM replacement; destroy/disconnect events were absent.
- Focused GREEN: `node test/client/graph-view.test.js` passed 6/6.
- Focused GREEN: `node test/client/project-reader.test.js` passed 12/12.
- Full Node gate: `npm test` passed 92/92 with 0 failed and 0 skipped.

## Verification

- `node --check client/graph-view.js`: PASS.
- `node --check client/render.js`: PASS.
- `node --check client/main.js`: PASS.
- `node --check e2e/atlas-graph.spec.js`: PASS.
- `git diff --check`: PASS.
- Static review confirms the renderer label accessor routes through `textContent`, the media event listener is paired with cleanup, and both normal and error rendering share the same route teardown.

## Self-review

- The tooltip fix does not rely on escaping correctness or server validation; the DOM text boundary is local to the renderer adapter.
- Hidden non-Focus labels still return an empty string, while active and Focus labels return browser-created elements accepted by the pinned tooltip implementation.
- Motion updates do not reset selection, visible graph state, relation filters, search state, camera position, or renderer data.
- Cleanup is idempotent at the route boundary because the stored callback is cleared before invocation.
- Existing untracked `.superpowers/brainstorm/` content was not modified or staged.

## Concerns

- Playwright remains controller `UNRUN` as requested. Browser proof for the live media transition, WebGL tooltip rendering, desktop/mobile layout, and fallback interaction remains outside this worker's Node-only gate.
