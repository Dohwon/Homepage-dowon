# Task 1 Report: Public KG Contract and Curated Projector

## Status

`DONE`

정본 `task-1-brief.md`의 public KG 계약을 구현했다. 기존
`atlas_worker.graph.build_graph()`의 tag-similarity API와 bundle validator는
호환 상태로 유지했고, 새 projector만 evidence-backed kind allowlist를 사용한다.

## 구현 결과

- `GraphNodeKind`를 `KnowledgeFocus`, `KnowledgeDomain`, `KnowledgeTag`,
  `Project`, `Technology`, `Artifact`로 제한했다.
- `GraphEdgeKind`를 7개 taxonomy/base relation과 4개 curated project relation으로
  제한하고, deterministic `edge_id` 및 public `evidence_links` projection을 추가했다.
- `KnowledgeTaxonomy`가 stable ID, duplicate ID/alias, focus/domain/tag parent reference,
  parent cycle, unknown profile label을 검증한다.
- `build_knowledge_graph()`가 taxonomy, project, technology, public artifact, curated
  relation을 deterministic 순서로 투영한다. shared tag로 project-project edge를
  생성하지 않으며 node 수를 제한하지 않는다.
- relation은 public evidence ID가 없으면 `graph-relation-evidence`로 실패한다.
  evidence link에는 label과 public project evidence URL만 포함하며 private locator는
  포함하지 않는다.
- `public-graph.schema.json`은 node/edge 필드와 kind를 exact allowlist로 검증한다.
- old LLM Wiki의 8 focus, 13 domain, 28 tag label을 reviewed taxonomy로 옮기고,
  현재 public profile label을 explicit alias로 연결했다.

## TDD 증거

RED:

- 기존 graph kind allowlist 테스트가 old lowercase tag kind 때문에 assertion failure.
- `tests/worker/test_kg.py`가 `atlas_worker.kg` 부재로 collection failure.
- default reviewed taxonomy 테스트가 `data/knowledge-taxonomy.yaml` 부재로 failure.

GREEN:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- \
  .venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py -q
28 passed in 0.14s
```

## Taxonomy 감사

현재 workspace의 `publication: public` profile 33개를 read-only로 다시 스캔했다.

```text
public_profiles=33 unknown_labels=0
```

감사 범위는 모든 `domain`, `problem`, `pattern`, `outcome` label이다. Technology는
projector가 stable normalized node로 직접 투영한다.

## Regression 및 Self-review

첫 전체 worker run에서 56개 failure가 발생했다. root cause는 legacy bundle
validator가 새 public `GRAPH_*_KINDS`를 import해 old `build_graph()` 산출물을
거부한 것이었다. `LEGACY_GRAPH_*_KINDS`를 명시하고 bundle validator import만
그 allowlist로 고정해 public/legacy 경계를 분리했다.

최종 전체 gate:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 prlimit --as=2147483648 --cpu=1800 -- \
  .venv/bin/python -m pytest tests/worker -q
750 passed, 1 skipped in 6.30s
```

Self-review에서 확인한 항목:

- public graph에 `project-similarity` 또는 unknown kind 없음
- shared taxonomy/technology가 direct project edge를 만들지 않음
- project, evidence, taxonomy, relation duplicate ID 검증
- taxonomy parent와 relation endpoint, self relation, relation evidence 검증
- input order와 무관한 node/edge 순서 및 no-cap 동작
- public projection exact field schema 통과
- legacy graph API 및 기존 bundle/CLI worker regression 유지
- `git diff --check` 통과

## 변경 파일

- `atlas_worker/models.py`
- `atlas_worker/kg.py`
- `atlas_worker/bundle.py` (legacy allowlist 호환 경계)
- `schemas/public-graph.schema.json`
- `data/knowledge-taxonomy.yaml`
- `tests/worker/test_kg.py`
- `tests/worker/test_taxonomy_graph.py`
- 이 보고서

## 우려사항

없음. 새 KG의 runtime bundle/CLI wiring은 후속 Task 2 범위이며 이번 Task 1에서는
의도적으로 legacy graph build 경로를 유지했다.
