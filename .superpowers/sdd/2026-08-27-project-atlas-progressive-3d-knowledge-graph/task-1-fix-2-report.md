# Task 1 Fix Round 2 Report

## Status

`DONE`

scoped re-review `task-1-fix-1-review.md`의 남은 HIGH 1개와 MEDIUM 1개를
negative regression test로 재현한 뒤 수정했다.

## HIGH: Schema-backed Public Article Gate

### RED

- `articles={"left": {"project_id": "left"}}` ID-only mapping이 evidence를 공개함
- `readiness="review-required"`인 실제 `ProjectArticle`이 evidence를 공개함

두 테스트 모두 수정 전 `Failed: DID NOT RAISE`로 실패했다.

### Fix

- article 값은 실제 `ProjectArticle` 또는 `Mapping`만 허용한다.
- `ProjectArticle`은 `to_public_dict()`로 public projection을 만든다.
- mapping은 전체 payload를 복사한 뒤 `public-article` JSON Schema로 검증한다.
- missing field, extra field, invalid field type/value는 `graph-article-schema`로 거부한다.
- schema 통과 후 mapping key와 `project_id` 일치를 검증한다.
- 마지막으로 `readiness == "ready"`만 public article index에 포함한다.
- article gate는 public evidence index, artifact, curated relation 생성 전에 실행된다.

Positive regression으로 완전한 ready public-article mapping과 실제 ready
`ProjectArticle`이 evidence를 공개하는 계약도 유지했다.

## MEDIUM: Encoded Traversal Boundary

### RED

다음 두 URL이 node projection, evidence-link projection, direct `public-graph`
schema validation을 모두 통과했다.

```text
/projects/..%2Fprivate?tab=evidence
/projects/%252E%252E%252Fprivate?tab=evidence
```

수정 전 model 4개와 schema 2개, 총 6개 negative case가
`Failed: DID NOT RAISE`로 실패했다.

### Fix

- encoded project ID를 한 번 decode한 뒤 control/whitespace/backslash를 다시 검사한다.
- decoded ID를 추가 decode했을 때 값이 달라지면 double-encoded 입력으로 거부한다.
- decoded ID를 `/` segment로 분리해 `.` 또는 `..` segment를 모두 거부한다.
- 기존 canonical percent encoding과 approved project-tab query 검증은 유지한다.
- JSON Schema는 기존 custom format을 통해 강화된 동일 validator를 사용한다.

정상 encoded project ID `/projects/alpha%2Fbeta?tab=evidence`는 두 번째 decode가
동일하고 traversal segment가 없으므로 계속 허용된다.

## Verification

Focused KG gate:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 \
prlimit --as=2147483648 --cpu=1800 -- \
.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py -q
54 passed in 0.18s
```

Full worker regression:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 \
prlimit --as=2147483648 --cpu=1800 -- \
.venv/bin/python -m pytest tests/worker -q
776 passed, 1 skipped in 6.60s
```

## Self-review

- ID-only mapping은 required public-article fields가 없어 schema에서 거부된다.
- complete mapping의 extra/private field도 `additionalProperties: false`로 거부된다.
- 실제 `ProjectArticle`도 public dict 투영 후 같은 schema를 통과해야 한다.
- `review-required`와 `insufficient-evidence`는 public evidence index 전에 종료된다.
- article `project_id` mismatch 및 evidence `project_id` mismatch 검증은 유지된다.
- single-encoded slash는 project ID 구성 요소로 허용하되 decoded dot segment는 거부된다.
- recursive percent-decoding이 발생하는 ID는 schema/model 양쪽에서 거부된다.
- taxonomy duplicate/merge-key fail-closed loader와 legacy graph 경계는 변경하지 않았다.
- 기존 `.superpowers/brainstorm/` untracked 디렉터리는 수정하지 않았다.
- `git diff --check` 통과.

## 변경 파일

- `atlas_worker/kg.py`
- `atlas_worker/models.py`
- `tests/worker/test_kg.py`
- 이 보고서

## 우려사항

없음.
