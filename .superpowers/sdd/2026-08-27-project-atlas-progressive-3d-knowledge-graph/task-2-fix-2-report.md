# Task 2 Fix Round 2 Report

## Status

DONE

## Finding Resolved

### MEDIUM: Node evidence label accepts generic Windows drive paths

- Added a Node store regression using `C:\\atlas\\private.txt` as a KG evidence label.
- Extended the evidence-label absolute-path check with the same generic drive-prefix boundary used by Python `PrivacyGate`: a drive letter followed by `:` and either slash direction, with no preceding alphanumeric character.
- Kept the existing HTTP URL masking and generic POSIX absolute-path check unchanged.
- Unsafe labels continue to reject the graph as `invalid_atlas_graph_edge`.

## TDD Evidence

- RED, before the production change: Atlas store `19 passed, 1 failed`.
- Failure: `Missing expected rejection: evidence label Windows drive path`.
- GREEN, after the minimal validator change: Atlas store `20 passed`.

## Verification

- `node test/server/atlas-store.test.js`: `20 passed`.
- `node test/server/public-evidence-url.test.js`: `2 passed`.
- `.venv/bin/python -m pytest tests/worker/test_privacy.py -q`: `136 passed, 1 skipped`.
- `node --check lib/atlas-store.js`: passed.
- `git diff --check`: passed.
- Every test command above used the required CPU, memory, BLAS, and niceness limits except the syntax and diff checks.
- No loopback API test was run, per instruction.

## Self-review

- The production diff is limited to the Node KG evidence-label validator and its Windows drive-path regression.
- The JavaScript boundary `(^|[^A-Za-z0-9])[A-Za-z]:[\\/]` matches Python's `(?<![A-Za-z0-9])[A-Za-z]:[\\/]` acceptance boundary.
- Existing POSIX detection and HTTP URL masking remain in the same helper.
- UNC labels remain covered by the shared Node public-content policy.
- V1 compatibility, V2 strict KG validation, hidden-project filtering, relation loading, and evidence URL allowlists are unchanged.
- Existing `.superpowers/brainstorm/` remains untracked and excluded from staging.

## Concerns

- The controller should rerun the elevated combined store/API gate because this change is exercised through the API store path; that loopback verification was intentionally not run here.
