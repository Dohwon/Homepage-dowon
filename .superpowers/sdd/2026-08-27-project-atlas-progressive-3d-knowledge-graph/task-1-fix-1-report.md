# Task 1 Fix Round 1 Report

## Status

`DONE`

독립 리뷰 `task-1-review.md`의 HIGH 1개와 MEDIUM 2개를 모두 negative
regression test로 재현한 뒤 수정했다.

## HIGH: Public Evidence Invariant

### RED

- article 없이 evidence를 제공해도 graph와 artifact가 생성됨
- evidence mapping key `left`에 `EvidenceRecord.project_id == right`를 넣어도 허용됨
- article mapping key `left`에 `ProjectArticle.project_id == right`를 넣어도 허용됨

세 테스트 모두 수정 전 `Failed: DID NOT RAISE`로 실패했다.

### Fix

- 모든 article object/mapping의 `project_id`가 mapping key와 일치해야 한다.
- non-empty evidence set은 동일 project의 matching article을 요구한다.
- 모든 evidence object/mapping의 `project_id`가 mapping key와 일치해야 한다.
- 위 검증을 artifact 생성과 curated relation evidence index 생성 전에 수행한다.
- curated relation은 이 검증을 통과한 public evidence index만 참조한다.

## MEDIUM: Fail-closed Taxonomy YAML

### RED

- 한 row에 `id` key를 두 번 작성한 YAML이 마지막 값으로 overwrite되어 통과함
- YAML merge key `<<`로 focus row를 합성해도 통과함

두 file-loader 테스트 모두 수정 전 `Failed: DID NOT RAISE`로 실패했다.

### Fix

- `yaml.SafeLoader` 기반 `_UniqueKeyLoader`를 taxonomy 전용으로 추가했다.
- mapping construction 중 duplicate key를 `graph-taxonomy-yaml-key`로 거부한다.
- merge key를 `graph-taxonomy-yaml-merge`로 거부한다.
- 일반 YAML parse 오류도 stable `graph-taxonomy-yaml` 오류로 fail-closed 처리한다.

## MEDIUM: Public Graph URL Boundary

### RED

- node URL의 local absolute path, `session:` locator, `file:` URL, traversal route가 통과함
- evidence-link URL의 session/local/file/traversal locator가 통과함
- 같은 private locator payload가 `public-graph` JSON Schema도 통과함

수정 전 URL negative case 8개와 schema case 1개가 모두
`Failed: DID NOT RAISE`로 실패했다.

### Fix

- node와 evidence-link projection이 하나의 `validate_public_graph_url()`을 사용한다.
- 내부 URL은 canonical `/projects/<encoded-project-id>` route만 허용한다.
- query는 public project tab `decisions`, `system-map`, `build-timeline`, `evidence`만
  허용한다.
- 외부 URL은 기존 public DNS 기반 absolute HTTPS validator를 통과해야 한다.
- raw absolute path, control/whitespace, backslash, malformed encoding, traversal,
  private scheme/session locator를 거부한다.
- node는 link가 없는 taxonomy node를 위해 empty URL만 예외적으로 허용한다.
- JSON Schema의 node/evidence-link URL에도 같은 custom format을 적용했다.

## Verification

Focused KG gate:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 \
prlimit --as=2147483648 --cpu=1800 -- \
.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py -q
45 passed in 0.17s
```

Full worker regression:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 \
prlimit --as=2147483648 --cpu=1800 -- \
.venv/bin/python -m pytest tests/worker -q
767 passed, 1 skipped in 6.67s
```

`git diff --check`도 통과했다.

## Self-review

- article/evidence identity 검증은 public evidence index와 artifact보다 먼저 실행된다.
- evidence가 없는 project는 article을 강제하지 않으며, projected evidence가 있는
  project만 matching article을 요구한다.
- duplicate evidence ID 검증은 matching article/project_id 조건 뒤에도 유지된다.
- duplicate/merge YAML key는 parse 후 overwrite되기 전에 loader에서 차단된다.
- dataclass projection과 JSON Schema가 동일 URL validator를 사용한다.
- generated `/projects/<id>`와 `/projects/<id>?tab=evidence` route는 유지된다.
- safe `https://example.com/...` URL은 허용되고 HTTP, file, session, local path는
  허용되지 않는다.
- legacy `atlas_worker.graph.build_graph()`와 bundle validator는 변경하지 않았다.
- 기존 `.superpowers/brainstorm/` untracked 디렉터리는 수정하지 않았다.

## 변경 파일

- `atlas_worker/kg.py`
- `atlas_worker/models.py`
- `schemas/public-graph.schema.json`
- `tests/worker/test_kg.py`
- 이 보고서

## 우려사항

없음.
