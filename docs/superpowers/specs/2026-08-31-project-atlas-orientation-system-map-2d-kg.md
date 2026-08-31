# Project Atlas 프로젝트 설명, System Map, 2D KG 명세

- 작성일: 2026-08-31
- 상태: 사용자 승인
- 대상 브랜치: `feature/project-atlas-public-experience`
- 선행 명세: `docs/superpowers/specs/2026-08-27-project-atlas-content-graph-redesign.md`

이 문서는 선행 명세의 프로젝트 분리, 근거 경계, Decision 중심 글, 공개 안전
정책을 유지하면서 처음 보는 독자를 위한 설명, 프로젝트별 System Map, 읽을 수
있는 Knowledge Graph를 보완한다. 충돌 시 이 문서가 우선한다.

## 1. 해결할 문제

현재 33개 공개 프로젝트에는 장문 article이 있지만 다음 문제가 남아 있다.

1. 한 문장 summary와 곧바로 이어지는 Planning 절만으로는 프로젝트를 처음 보는
   독자가 대상 사용자, 제품 범위와 출발 문제를 충분히 파악하기 어렵다.
2. 글이 선택과 결과를 잘 설명하더라도 선택 이전의 관측, 제약, 기획적 갈등이
   약하면 해결책의 이유를 이해하기 어렵다.
3. 33개 프로젝트 모두 `system-map.svg`가 없어 System Map 탭이 빈 상태다.
4. 3D Graph는 노드 이름을 hover tooltip으로만 보여 주고 초기 상태에서 태그를
   숨긴다. 배경도 렌더러 기본값에 의존해 테마와 다른 검은 화면이 나타날 수 있다.

## 2. 글 구성 원칙

### 2.1 고정 목차를 만들지 않는다

모든 글에 `프로젝트 설명 -> 문제 정의 -> 기획 고민 -> 해결 -> 결과`라는 동일한
제목과 개수를 강제하지 않는다. 대신 공개 가능한 근거가 있을 때 글 전체가 다음
질문에 답해야 한다.

- 이 프로젝트는 누구를 위해 무엇을 만드는가?
- 어떤 관측이나 요구 때문에 시작했는가?
- 기존 상태에서 무엇이 문제였고 왜 단순한 해법으로 충분하지 않았는가?
- 범위, 우선순위, 사용자 흐름, 운영 정책을 정할 때 무엇을 고민했는가?
- 어떤 선택을 했고 무엇을 포기하거나 되돌렸는가?
- 구현과 검증 뒤 무엇이 달라졌으며 아직 확인하지 못한 것은 무엇인가?

프로젝트 성격에 따라 서사를 다르게 구성한다.

- 버전 프로젝트: 선행 단계의 한계와 이번 버전의 범위를 먼저 설명한다.
- 문제 해결 프로젝트: 문제별로 관측, 제약, 선택, 검증을 이어 쓴다.
- 조사·분석 프로젝트: 잘못된 가정, 확인 과정, 분석 계약과 남은 검증을 설명한다.
- 도구 프로젝트: 반복 작업, 실패 비용, 입력·출력 계약과 운영 경계를 설명한다.
- 콘텐츠 프로젝트: 독자 문제, 편집 기준, 정보 구조와 공개·운영 판단을 설명한다.

근거가 없는 질문은 억지로 채우지 않는다. 문제 수, 절 수, 글 길이와 Diagram 수에
목표 개수를 두지 않는다.

### 2.2 Orientation은 한 개의 자연스러운 도입부다

기존 `summary`는 목록과 검색 결과에서 사용하는 짧은 설명으로 유지한다. 상세 글에는
선택적인 장문 `orientation`을 추가한다. `orientation`은 별도 카드나 고정된 다섯 칸이
아니라 본문 앞에 놓이는 2~5문단 Markdown이다.

`orientation`에는 가능한 범위에서 프로젝트 설명, 출발 문제, 중요한 제약과 글에서
다룰 핵심 흐름이 자연스럽게 들어간다. 기존 첫 Planning 절과 내용이 겹치면 해당 절을
기획 판단 중심으로 다시 쓴다. 목차에는 Orientation을 별도 항목으로 추가하지 않는다.

### 2.3 콘텐츠 품질 검사는 단어 매칭이 아니다

`문제`, `결과` 같은 특정 단어 또는 고정 heading의 존재만 검사하지 않는다. 공개 준비
검사는 다음 구조적 신호를 사용한다.

- `ready` article은 비어 있지 않은 `orientation`을 가진다.
- `orientation`은 하나 이상의 evidence ID를 참조한다.
- article 전체에는 적어도 하나의 Planning 또는 Decision 절이 있다.
- 해당 절과 Orientation의 evidence가 공개 evidence 목록에 존재한다.
- 문장 길이와 절 개수로 품질을 대신하지 않는다.

사람이 읽는 전체 카탈로그 점검에서는 각 프로젝트의 설명, 문제, 기획 판단이 실제
근거와 맞는지 별도로 확인한다.

## 3. System Map

### 3.1 데이터 모델

프로젝트별 정본은 `project_memory/project-atlas/system-map.yaml`이다.

```yaml
project_id: stable-id
title: 담백한 지도 제목
summary: 이 지도가 설명하는 프로젝트 고유 경계
nodes:
  - id: stable-id
    label: 짧은 표시 이름
    kind: actor | input | interface | process | state | service | output | guardrail
    description: 처음 보는 독자를 위한 역할 설명
flows:
  - id: stable-id
    from: node-id
    to: node-id
    label: 이동하거나 바뀌는 내용
decision_links:
  - node_ids: [node-id]
    section_id: article-section-id
    label: 이 구조가 필요해진 결정
evidence_ids: [stable-id]
```

노드와 흐름 개수는 강제하지 않는다. 모든 ID 참조, section 참조와 evidence 참조는
loader가 검증한다. SVG는 worker가 이 정본에서 결정론적으로 생성한다.

### 3.2 의미 기준

- 앱은 사용자 입력, 클라이언트, 처리, 저장 정본, 외부 서비스와 결과 경계를 보여 준다.
- 분석은 원천 자료, 정제·조인, 판단 규칙, 검토 산출물과 미검증 경계를 보여 준다.
- 자동화 도구는 trigger, 입력, 처리 단계, failure isolation, 산출물과 승인 경계를 보여 준다.
- 문서·콘텐츠 프로젝트는 source, 편집 판단, 공개 필터, 독자 산출물의 작업 시스템을 보여 준다.
- 프로젝트의 실제 이름과 선택을 제거했을 때 다른 프로젝트에도 그대로 쓸 수 있는 Map은
  허용하지 않는다.

System Map 탭은 summary, SVG, 노드별 설명과 연결된 Decision 링크를 함께 렌더링한다.
SVG만으로 전체 내용을 설명하지 않는다.

## 4. 2D Knowledge Graph

### 4.1 기본 투영

Graph 기본 화면은 WebGL 3D가 아니라 DOM/SVG 기반 2D 계층형 지도다.

```text
Knowledge Focus -> Knowledge Domain -> Knowledge Tag -> Project
                                                   -> Technology / Artifact (선택 후 펼침)
```

- Focus, Domain, Tag의 이름은 항상 화면에 표시한다.
- Project는 연결된 태그를 선택했을 때 표시하며 프로젝트 수를 tag label에 함께 보여 준다.
- Technology와 Artifact는 기본 화면에서 숨기고 Project 선택 뒤 펼친다.
- Artifact 248개가 초기 탐색을 압도하지 않게 한다.
- 노드 선택 시 직접 연결된 경로만 강조하고 나머지는 흐리게 표시한다.
- 태그 선택 시 오른쪽 detail에 연결 프로젝트를 표시한다.
- 프로젝트 선택 시 상세 페이지로 이동할 수 있다.

### 4.2 시각·접근성 계약

- SVG와 label은 CSS theme token을 사용하고 배경을 명시한다.
- light/dark 모두 텍스트와 선의 대비를 유지한다.
- pointer hover 없이도 Focus, Domain, Tag를 읽을 수 있다.
- 키보드 focus와 Enter/Space 선택을 지원한다.
- 작은 화면에서는 가로 스크롤 또는 축소된 계층 배치를 사용하되 label을 숨기지 않는다.
- 검색, 관계 필터, 상세 sidebar와 목록 fallback은 유지한다.
- 3D 보기는 기본 경로에서 제거한다. 기존 vendor asset은 다른 사용처가 없는지 확인한 뒤
  별도 정리한다.

## 5. 공개와 자동 갱신

- source YAML은 프로젝트 폴더에 남고 공개 bundle에는 경로, 세션 ID와 내부 locator를
  포함하지 않는다.
- worker는 article 또는 system-map source hash가 바뀐 프로젝트만 재생성한다.
- Map 검증 실패는 해당 프로젝트 candidate를 `review-required`로 두고 마지막 정상
  bundle을 유지한다.
- 현재 공개 대상 33개 프로젝트 모두 Orientation과 유효한 System Map을 가져야 초기
  backfill을 완료한 것으로 본다.
- 이후 새 프로젝트도 같은 품질 gate를 통과해야 공개 ready가 된다.

## 6. 완료 조건

1. 공개 대상 33개 article 모두 근거가 연결된 Orientation을 가진다.
2. 글은 프로젝트별 서사를 유지하며 고정 heading 세트를 반복하지 않는다.
3. 33개 프로젝트 모두 구조화 System Map과 렌더링 가능한 SVG를 가진다.
4. System Map의 node, flow, article section과 evidence 참조가 모두 유효하다.
5. Graph 첫 화면에서 Focus, Domain, Tag 이름을 pointer 없이 읽을 수 있다.
6. Graph의 배경이 light/dark theme과 일치하며 검은 WebGL 기본 화면이 없다.
7. 태그 선택으로 연결 프로젝트를 확인하고 프로젝트 상세로 이동할 수 있다.
8. privacy, schema, bundle, client, server와 전체 카탈로그 검사가 통과한다.
9. desktop과 mobile에서 overflow, label 겹침, tab 이동과 scroll progress를 확인한다.

