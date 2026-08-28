# Task 7 Report: Atlas Decision Content Boundary Fixtures

## Result

Added a new acceptance layer that locks the curated Map Diary V2 decision text,
worktree ownership boundary, and insufficient-evidence behavior after the v2
public bundle migration.

## Files

- Added `tests/worker/test_content_acceptance.py`
- Modified `tests/worker/helpers.py`
- Added `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/article.yaml`
- Added `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/evidence.yaml`
- Added `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/visuals/tmap-vworld-lifecycle.svg`
- Added `tests/fixtures/project-content/insufficient/project_memory/project-profile.yaml`

## Decisions

- Locked the V2 decision section title to `TMAP 데이터 장기 저장 제한 해결`.
- Locked the V2 article body to the verified boundary only: TMAP 24-hour limit,
  session-only input, durable VWorld Feature ID plus geometry snapshot, and
  TMAP source route discard after permanent conversion.
- Used the three exact evidence IDs:
  `v2-tmap-retention-spec`, `v2-vworld-feature-spec`,
  `v2-source-discard-spec`.
- Used a specific lifecycle SVG with separate `TMAP 세션 입력 수명` and
  `VWorld 영구 기록 수명` labels; no generic `문제 -> 결정 -> 결과` flow.
- Kept V4 as V3-owned worktree evidence in acceptance coverage and did not add
  any new inferred project relation, merge, or predecessor link.
- Kept the evidence-poor fixture article-free so the audit stays
  `insufficient-evidence` without manufactured content.
- Removed `decision_index` from the V2 fixture because duplicating the same
  evidence IDs across section and decision references triggers the current audit
  contract's `duplicate-evidence-reference` finding.

## TDD Evidence

1. Added `tests/worker/test_content_acceptance.py` before fixture content.
2. Ran the bounded focused test and observed RED:
   - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- .venv/bin/python -m pytest tests/worker/test_content_acceptance.py -q`
   - Result: `2 failed, 1 passed`
   - Failure: missing fixture directories for `map-diary-v2` and `insufficient`
3. Added the exact fixture files.
4. Re-ran the same bounded focused test to GREEN:
   - Result: `3 passed in 0.16s`

## Verification

- Focused acceptance:
  - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- .venv/bin/python -m pytest tests/worker/test_content_acceptance.py -q`
  - Result: `3 passed in 0.16s`
- Full worker:
  - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- .venv/bin/python -m pytest tests/worker -q`
  - Result: `731 passed, 1 skipped in 8.60s`
- Node store and API current-suite check:
  - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- node --test test/server/atlas-store.test.js test/server/atlas-api.test.js`
  - Result: `1 pass, 1 fail`
  - Failure surface: file-level `test/server/atlas-api.test.js` runner failure under `node --test`
- Direct API file execution for detail:
  - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- node test/server/atlas-api.test.js`
  - Result: `10 passed, 0 failed`
- Current `audit-content` command check:
  - `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- .venv/bin/python scripts/project_atlas.py audit-content --workspace /home/dowon/securedir/git/codex --format json`
  - Result: `{"error":{"category":"config","pointer":"/arguments"}}`
  - Note: current CLI contract at `a06f2f3` requires `--project` for `audit-content`.

## Scope Notes

- No production Atlas worker or server code changed.
- No legacy `decisions.md` or generic `problem-solving.svg` files were created
  by Task 7.
- `.superpowers/brainstorm/` remained untouched and must stay unstaged.
