# Task 4 Fix Round 1 Report: WebGL2 Capability Boundary

## Status

DONE

## Root Cause

- `supportsWebGL()` accepted successful `webgl` or `experimental-webgl` context creation after `webgl2` failed.
- The exact locked renderer uses `three@0.185.1`, whose `WebGLRenderer` and the vendored graph bundle request a `webgl2` context. The adapter predicate was therefore looser than renderer construction.

## Fixed

- Restricted `supportsWebGL()` to a usable `webgl2` context only.
- Split the capability fake by context name and added regressions for WebGL2 success plus WebGL1-only, null context, missing `createElement`, missing `getContext`, thrown context creation, and null document failures.

## TDD Evidence

- RED: 3/4 focused subtests passed; the WebGL1-only regression returned `true` instead of expected `false`.
- Focused GREEN: `node --test test/client/graph-view.test.js` exited 0.
- Full regression gate: `npm test` passed 88/88.

## Self-review

- Production capability detection now makes exactly one `getContext("webgl2")` request and retains the existing catch-all fail-closed behavior.
- The diff is limited to `client/graph-view.js`, `test/client/graph-view.test.js`, and this report.
- `git diff --check` and syntax checks for both changed JavaScript files exited 0.
- Existing untracked `.superpowers/brainstorm/` content was not modified or staged.

## Concerns

None.
