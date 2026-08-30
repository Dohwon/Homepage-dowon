# Task 6 Fix Round 1 Report

## Status

DONE

## Review Findings Resolved

### Operation-specific camera and drag oracle

- Added a read-only renderer `inspect()` snapshot with camera position, Orbit target, control revision, engine-settled state, projected public node positions, drag telemetry, and camera-command telemetry.
- Replaced arbitrary canvas-delta gesture assertions with explicit contracts after `onEngineStop` and two stable camera/node samples.
- Zoom now requires a control revision, stable target, and changed camera-target distance.
- Rotate now requires a control revision, stable target and radius, and changed camera-target direction.
- Pan now requires a control revision, moved Orbit target, and stable camera-target vector.
- Fit now requires a new `fit` command with the normal `500 ms` duration.
- Node drag uses the renderer-projected coordinate of a real Project node and requires a new drag revision, matching node ID, nonzero from/to displacement, and pinned node state.
- Reset requires a new `reset` command in addition to the existing visible-node and selection reset assertions.

### Live reduced-motion suppression oracle

- Kept the preference dataset assertion as propagation evidence.
- After a live `no-preference` to `reduce` transition, E2E now verifies the renderer snapshot reports reduced motion.
- A subsequent Fit action must create a newer `fit` command whose transition duration is exactly `0`.

## Production Hook Safety

- `createGraphView().inspect()` returns cloned and frozen public graph telemetry only. It does not expose labels, summaries, evidence, source locators, private paths, renderer objects, or mutation methods.
- `bindGraph` installs one non-writable `__atlasGraphInspector` function on the existing graph container only when the 3D view exists.
- Route cleanup deletes the inspector and the adapter removes the Orbit control listener before destroying the renderer.

## TDD Evidence

- RED: the new adapter inspection test failed before implementation because `onEngineStop` and `inspect()` were absent.
- The first GREEN attempt exposed an `undefined` synthetic-node ID edge case in direct drag-end tests; the drag-start selection now requires a real active drag record.
- Focused adapter tests: PASS, `7 passed`.
- Full Node suite after implementation: PASS, `93 passed`, `0 failed`.

## Verification

- `node --check client/graph-view.js`: PASS.
- `node --check e2e/atlas-graph.spec.js`: PASS.
- `npm test`: PASS, `93 passed`, `0 failed`.
- `git diff --check`: PASS.
- `npm run test:ui -- e2e/atlas-graph.spec.js`: UNRUN. Under `prlimit --as=2147483648`, Node failed in Undici startup before Playwright test execution with `WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory for new instance`.

## Self-review

- Canvas pixels remain only the nonblank rendering oracle; camera, Fit, Reset, and drag behavior no longer pass from unrelated force-layout pixels.
- Each gesture captures its own control/command/drag revision before action, preventing an earlier operation from satisfying a later assertion.
- Engine settle plus consecutive stable snapshots replaces the previous fixed `500 ms` assumption.
- Node drag asserts renderer callback state, actual position displacement, and pinning rather than color detection or generic canvas change.
- Reduced-motion requires a post-transition renderer action and exact zero-duration command, not only a DOM preference marker.
- Existing untracked `.superpowers/brainstorm/` content was not modified or staged.

## Outstanding Concerns

- Browser assertions remain unexecuted because Playwright cannot start within the required 2 GiB address-space limit. This fix strengthens the static oracle and Node-tested adapter contract but is not desktop/mobile browser approval.
- The promoted bundle rebuild HIGH remains assigned to the controller and is outside this fix round. No bundle, legacy CSV, or taxonomy source was modified.
