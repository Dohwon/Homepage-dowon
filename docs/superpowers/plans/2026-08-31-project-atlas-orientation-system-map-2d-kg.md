# Project Atlas Orientation, System Map, 2D KG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 33개 프로젝트를 처음 보는 독자가 문제와 기획 판단부터 이해하게 만들고, 비어 있지 않은 프로젝트별 System Map과 태그가 읽히는 2D Knowledge Graph를 제공한다.

**Architecture:** Article에는 고정 목차 대신 장문 Orientation을 추가하고 근거 연결만 구조적으로 검증한다. System Map은 프로젝트별 YAML 정본을 loader가 검증한 뒤 결정론적 SVG와 공개 설명 자료로 투영한다. 전역 Graph는 기존 KG 데이터와 탐색 state를 재사용하되 WebGL adapter를 DOM/SVG 2D renderer로 교체한다.

**Tech Stack:** Python 3, PyYAML, JSON Schema, Node.js ESM, DOM/SVG, CSS, Node test runner, pytest

**Spec:** `docs/superpowers/specs/2026-08-31-project-atlas-orientation-system-map-2d-kg.md`

## Global Constraints

- 고정된 프로젝트 글 목차나 절 개수를 강제하지 않는다.
- 공개 근거에서 확인되지 않은 문제, 고민, 결과를 만들지 않는다.
- 공개 대상 33개 프로젝트를 정확한 전체 범위로 처리한다.
- System Map은 프로젝트 고유 경계와 결정을 설명하며 generic 3단계 도식을 허용하지 않는다.
- Graph에서 Focus, Domain, Tag label은 pointer 없이 읽을 수 있어야 한다.
- 비공개 locator, 세션 ID, credential과 절대 경로를 public bundle에 쓰지 않는다.

---

### Task 1: Orientation 데이터 계약

**Files:**
- Modify: `schemas/project-article.schema.json`
- Modify: `schemas/public-article.schema.json`
- Modify: `atlas_worker/models.py`
- Modify: `atlas_worker/article.py`
- Modify: `atlas_worker/content_audit.py`
- Test: `tests/worker/test_article.py`
- Test: `tests/worker/test_content_audit.py`

**Interfaces:**
- Consumes: 기존 `article.yaml`, evidence ID 검증과 `ProjectArticle.to_public_dict()`
- Produces: `ProjectArticle.orientation: str`, `orientation_evidence_ids: tuple[str, ...]`

- [ ] `ready` article의 Orientation과 evidence 참조를 요구하는 실패 테스트를 작성한다.
- [ ] 대상 pytest가 `orientation` 필드 부재와 evidence 누락으로 실패하는지 확인한다.
- [ ] schema, loader, model과 public projection을 최소 변경한다.
- [ ] content audit가 Orientation의 존재와 근거 연결을 검사하게 한다.
- [ ] worker article/audit 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 2: 유연한 상세 글 도입부

**Files:**
- Modify: `client/render.js`
- Modify: `styles.css`
- Modify: `test/client/project-reader.test.js`
- Modify: `test/fixtures/public-bundle/projects/alpha/article.json`

**Interfaces:**
- Consumes: public article의 `summary`, `orientation`, `sections`
- Produces: 카드나 고정 heading 없이 본문 앞에 렌더링되는 Orientation

- [ ] summary와 Orientation이 중복 카드 없이 자연스러운 도입부로 렌더링되는 실패 테스트를 작성한다.
- [ ] client test가 Orientation 미렌더링으로 실패하는지 확인한다.
- [ ] render와 typography를 구현하고 Orientation을 목차에서 제외한다.
- [ ] 기존 section 순서와 sticky 목차, scroll progress가 유지되는지 테스트한다.
- [ ] client 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 3: 구조화 System Map loader와 SVG projector

**Files:**
- Create: `schemas/project-system-map.schema.json`
- Create: `schemas/public-system-map.schema.json`
- Create: `atlas_worker/system_map.py`
- Modify: `atlas_worker/models.py`
- Modify: `atlas_worker/article.py`
- Modify: `atlas_worker/cli.py`
- Modify: `atlas_worker/bundle.py`
- Test: `tests/worker/test_system_map.py`
- Test: `tests/worker/test_bundle.py`
- Test: `tests/worker/test_cli.py`

**Interfaces:**
- Consumes: `system-map.yaml`, loaded article section IDs, evidence IDs
- Produces: `ProjectSystemMap`, `render_system_map_svg(map) -> str`, public `system-map.json`, `system-map.svg`

- [ ] 유효한 map, 잘못된 node/flow/section/evidence 참조, unsafe text를 다루는 실패 테스트를 작성한다.
- [ ] 테스트가 loader와 schema 부재 때문에 실패하는지 확인한다.
- [ ] strict YAML loader와 immutable System Map model을 구현한다.
- [ ] node kind별 token을 사용한 결정론적 layered SVG projector를 구현한다.
- [ ] bundle이 JSON과 SVG를 함께 원자적으로 쓰고 검증하도록 연결한다.
- [ ] worker map, bundle, CLI 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 4: 설명이 있는 System Map 탭

**Files:**
- Modify: `client/api.js`
- Modify: `client/project-reader.js`
- Modify: `client/render.js`
- Modify: `styles.css`
- Modify: `test/client/project-reader.test.js`
- Modify: `test/server/atlas-api.test.js`

**Interfaces:**
- Consumes: public `system-map.json`, `system-map.svg`, article section IDs
- Produces: summary, SVG, node descriptions와 Decision anchor link를 포함한 System Map tab

- [ ] project loader와 renderer의 실패 테스트를 작성한다.
- [ ] JSON이 로드되지 않고 SVG-only UI가 생성돼 테스트가 실패하는지 확인한다.
- [ ] API/store와 client reader에 map metadata를 추가한다.
- [ ] System Map 설명, node legend와 Decision link를 렌더링한다.
- [ ] server/client 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 5: 2D KG state projection

**Files:**
- Modify: `client/graph-state.js`
- Test: `test/client/graph-state.test.js`

**Interfaces:**
- Consumes: 기존 KG nodes/edges
- Produces: Focus, Domain, Tag를 기본으로 노출하고 선택된 Tag의 Project를 펼치는 immutable state

- [ ] 기본 projection에 Focus, Domain, Tag가 포함되고 Artifact가 제외되는 실패 테스트를 작성한다.
- [ ] 기존 프로젝트 중심 초기 상태 때문에 실패하는지 확인한다.
- [ ] 초기 state와 tag/project expansion 규칙을 구현한다.
- [ ] shortest path, relation filter와 immutable snapshot 회귀 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 6: 접근 가능한 2D SVG Graph renderer

**Files:**
- Replace: `client/graph-view.js`
- Modify: `client/render.js`
- Modify: `styles.css`
- Modify: `test/client/graph-view.test.js`
- Modify: `test/client/project-reader.test.js`
- Modify: `index.html`
- Modify: `package.json`
- Modify: `package-lock.json`

**Interfaces:**
- Consumes: `visibleGraph()`의 nodes와 links
- Produces: `createGraphView(container, graph, options)` 호환 adapter와 persistent text labels

- [ ] SVG node, edge, persistent label, theme background, keyboard selection의 실패 테스트를 작성한다.
- [ ] 기존 3D factory adapter 때문에 테스트가 실패하는지 확인한다.
- [ ] 결정론적 계층 layout과 keyed DOM/SVG update를 구현한다.
- [ ] fit/reset, resize, 선택, reduced motion API 호환을 구현한다.
- [ ] WebGL 감지와 3D 전용 fallback 문구를 제거하고 목록 fallback은 유지한다.
- [ ] 사용되지 않는 3D vendor 의존성을 제거한다.
- [ ] client 전체 테스트를 통과시킨다.
- [ ] 변경을 커밋한다.

### Task 7: 33개 프로젝트 Orientation backfill

**Files:**
- Modify: `/home/dowon/securedir/git/codex/projects/*/project_memory/project-atlas/article.yaml`
- Modify: `/home/dowon/securedir/git/codex/projects/finish/*/project_memory/project-atlas/article.yaml`
- Modify: `tests/worker/test_content_acceptance.py`
- Modify: `scripts/audit_public_atlas_catalog.py`

**Interfaces:**
- Consumes: 기존 article, evidence, 프로젝트 문서·코드·세션 분석 결과
- Produces: 33개 근거 연결 Orientation과 보완된 문제·기획 서사

- [ ] 공개 33개 모두 Orientation과 근거를 요구하는 acceptance 실패 테스트를 작성한다.
- [ ] 정확히 33개가 실패 대상으로 검출되는지 확인한다.
- [ ] 각 프로젝트의 기존 근거를 다시 읽고 고유한 Orientation을 작성한다.
- [ ] 첫 Planning 절의 중복을 줄이고 기획 판단, 범위 변경과 rollback 근거를 보완한다.
- [ ] 전체 카탈로그 audit가 33개를 빠짐없이 통과하는지 확인한다.
- [ ] 프로젝트 source 변경은 각 소유 저장소 상태를 확인한 뒤 관련 파일만 커밋하거나 변경 목록으로 남긴다.

### Task 8: 33개 프로젝트 System Map backfill

**Files:**
- Create: `/home/dowon/securedir/git/codex/projects/*/project_memory/project-atlas/system-map.yaml`
- Create: `/home/dowon/securedir/git/codex/projects/finish/*/project_memory/project-atlas/system-map.yaml`
- Modify: `tests/worker/test_content_acceptance.py`
- Modify: `scripts/audit_public_atlas_catalog.py`

**Interfaces:**
- Consumes: 각 article section/evidence ID와 실제 프로젝트 구조
- Produces: 33개 프로젝트 고유 System Map source

- [ ] 모든 공개 프로젝트에 유효한 Map을 요구하는 acceptance 실패 테스트를 작성한다.
- [ ] 33개 missing Map이 검출되는지 확인한다.
- [ ] 프로젝트별 actor/input/process/state/service/output/guardrail 경계와 flow를 작성한다.
- [ ] 각 Map을 실제 Decision section과 evidence에 연결한다.
- [ ] 중복 topology와 generic label을 검출하는 카탈로그 검사를 추가한다.
- [ ] 33개 Map 전체를 load/render/audit한다.

### Task 9: 전체 재생성 및 회귀 검증

**Files:**
- Regenerate: `public-bundle/**`
- Regenerate: `data/projects.generated.json`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-31-project-atlas-orientation-system-map-2d-kg.md`

**Interfaces:**
- Consumes: 33개 curated source와 변경된 worker/client
- Produces: privacy-safe atomic public bundle과 운영 문서

- [ ] worker 전체 pytest를 실행한다.
- [ ] Node 전체 테스트를 실행한다.
- [ ] public catalog audit에서 projects=33, orientations=33, system_maps=33을 확인한다.
- [ ] 번들을 race-safe 방식으로 재생성하고 strict validation을 통과시킨다.
- [ ] 서버를 재시작하고 API에서 33개 ready 프로젝트와 Map JSON/SVG를 확인한다.
- [ ] 1440px와 390px에서 글, System Map, Graph, sticky 목차와 progress bar를 시각 검증한다.
- [ ] 시각 검증 도구를 사용할 수 없으면 정확한 미실행 경계와 원인을 기록한다.
- [ ] 사용자 요구, 테스트 결과와 남은 release 경계를 README/spec에 반영한다.
- [ ] 관련 변경만 최종 커밋한다.

