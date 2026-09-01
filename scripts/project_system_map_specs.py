"""Reviewed system-map subjects for the curated Project Atlas articles."""

from __future__ import annotations

from typing import Any


def _node(node_id: str, label: str, kind: str, description: str, section: str) -> dict[str, str]:
    return {
        "id": node_id,
        "label": label,
        "kind": kind,
        "description": description,
        "section": section,
    }


def _spec(map_type: str, title: str, summary: str, nodes: list[dict[str, str]], flows: list[tuple[str, str, str]], decisions: list[str]) -> dict[str, Any]:
    return {
        "map_type": map_type,
        "title": title,
        "summary": summary,
        "nodes": nodes,
        "flows": [
            {"id": f"flow-{index:02}", "from": source, "to": target, "label": label}
            for index, (source, target, label) in enumerate(flows, 1)
        ],
        "decision_sections": decisions,
    }


SPECS: dict[str, dict[str, Any]] = {
    "251104-prompt-auto-evaluation": _spec(
        "evaluation-pipeline", "입력 행에서 비교 결과까지", "한 입력 행이 후보 생성, 형식 확인, judge 비교와 결과 보존을 거치는 평가 파이프라인이다.",
        [_node("test-row", "평가 입력 행", "input", "동일한 질문과 기대 조건을 가진 한 건의 비교 단위다.", "fixed-input"), _node("candidate-runs", "후보 생성 실행", "service", "같은 입력에 대해 둘 이상의 모델 후보를 생성한다.", "judge-boundary"), _node("format-gate", "형식 검증", "guardrail", "JSON과 필수 필드가 맞는지 먼저 확인하고 의미 평가와 분리한다.", "structural-validation"), _node("judge-comparison", "후보 비교", "process", "N-way 후보의 의미적 승패와 동률 규칙을 계산한다.", "n-way"), _node("review-output", "원시 결과와 요약", "output", "실패 행을 잃지 않고 원시 실행과 검토용 요약을 함께 남긴다.", "output-lifecycle")],
        [("test-row", "candidate-runs", "후보 생성"), ("candidate-runs", "format-gate", "형식 확인"), ("format-gate", "judge-comparison", "통과 행 평가"), ("judge-comparison", "review-output", "결과 보존")], ["judge-boundary", "structural-validation", "output-lifecycle"],
    ),
    "260212-feeling-traker": _spec(
        "cross-surface-ledger", "감정 입력에서 공통 기록과 대화까지", "브라우저와 데스크톱 위젯의 감정 입력을 하나의 원장으로 모으고 필요한 경우에만 대화를 시작한다.",
        [_node("feeling-input", "감정 입력", "input", "한 번의 클릭이나 짧은 기록으로 현재 감정을 남긴다.", "click-intent"), _node("shared-ledger", "공통 감정 원장", "state", "웹과 위젯이 함께 읽는 기록 저장소다.", "shared-ledger"), _node("reminder-window", "최근 기록 알림", "guardrail", "오래된 누락을 전부 경고하지 않고 최근 일주일 범위만 보여 준다.", "reminder-window"), _node("conversation-entry", "선택적 대화", "interface", "기록만 남길지 대화를 시작할지 사용자의 의도를 분리한다.", "conversation-fallback"), _node("insight-view", "인사이트 화면", "output", "축적된 기록을 요약해 다시 보는 화면이다.", "product-expansion")],
        [("feeling-input", "shared-ledger", "기록 저장"), ("shared-ledger", "reminder-window", "최근 기록 확인"), ("shared-ledger", "conversation-entry", "필요할 때 대화"), ("conversation-entry", "insight-view", "다시 보기")], ["shared-ledger", "conversation-fallback"],
    ),
    "260218-ope-log-anlayze": _spec(
        "log-analysis-pipeline", "원천 로그에서 인계 산출물까지", "서로 다른 운영 데이터와 이벤트를 정렬·복원해 월별 분석 산출물과 인계 계약으로 만든다.",
        [_node("raw-events", "원천 이벤트", "input", "운영 시스템에서 나온 이벤트와 고객 control 데이터를 받는다.", "split-data-layers"), _node("schema-normalizer", "스키마 정규화", "process", "실제 이벤트 스키마를 확인해 잘못된 usage 테이블 가정을 제거한다.", "replace-usage-table-assumption"), _node("session-rebuilder", "세션 복원", "process", "시간순 이벤트를 세션 단위로 묶고 blank와 순서 이상을 보존한다.", "ascending-session-contract"), _node("search-metrics", "검색 신호 분리", "state", "검색 후보·실행·일치 결과를 서로 다른 지표로 저장한다.", "separate-search-contract"), _node("monthly-handoff", "월별 인계 산출물", "output", "대용량 처리를 재실행 가능한 월별 파일과 계약으로 넘긴다.", "monthly-handoff-boundary")],
        [("raw-events", "schema-normalizer", "스키마 확인"), ("schema-normalizer", "session-rebuilder", "정렬·복원"), ("session-rebuilder", "search-metrics", "신호 계산"), ("search-metrics", "monthly-handoff", "월별 산출")], ["split-data-layers", "ascending-session-contract", "separate-search-contract"],
    ),
    "260315-moe-prompt-routing": _spec(
        "routing-pipeline", "사용자 요청에서 expert 결과까지", "명확한 명령은 사전이 처리하고, 남은 요청만 family 선택과 expert 실행으로 넘기는 라우팅 흐름이다.",
        [_node("user-request", "사용자 요청", "input", "음성 또는 텍스트로 들어온 자연어 요청이다.", "dictionary-first"), _node("dictionary-router", "명확한 명령 라우터", "process", "사전에 확실히 매핑되는 요청을 낮은 비용으로 먼저 처리한다.", "dictionary-first"), _node("family-selector", "기능 family 선택", "service", "모호한 요청만 적절한 기능 family로 분류한다.", "family-then-expert"), _node("expert-executor", "expert 실행", "service", "선택된 family의 expert가 실행 가능한 결과 계약을 만든다.", "family-then-expert"), _node("evaluated-result", "평가 결과", "output", "라우팅과 expert 결과를 별도 조건으로 평가하고 실패 행도 남긴다.", "result-contract")],
        [("user-request", "dictionary-router", "확실한 명령 우선"), ("dictionary-router", "family-selector", "미해결 요청"), ("family-selector", "expert-executor", "family 전달"), ("expert-executor", "evaluated-result", "결과 평가")], ["dictionary-first", "family-then-expert"],
    ),
    "260317-desktop-scheduler": _spec(
        "local-desktop-app", "일정 입력에서 알림 상태까지", "단일 사용자 일정의 날짜·미루기 이력과 알림 상태를 로컬 앱 안에서 보존한다.",
        [_node("calendar-input", "일정 입력", "interface", "콘솔 없이 바탕화면 앱에서 일정을 만들고 날짜를 바꾼다.", "planning-background"), _node("calendar-view", "6주 달력", "interface", "월 경계에서도 같은 6주 그리드로 일정을 탐색한다.", "fixed-calendar"), _node("sqlite-store", "로컬 SQLite", "state", "일정 본문과 미루기 이력을 분리해 저장한다.", "implementation-flow"), _node("notification-state", "알림 상태", "state", "알림 발송 여부를 저장해 재시작과 재시도에 중복 알림이 생기지 않게 한다.", "notification-state")],
        [("calendar-input", "calendar-view", "날짜 탐색"), ("calendar-view", "sqlite-store", "일정 저장"), ("sqlite-store", "notification-state", "알림 상태 갱신")], ["planning-background", "fixed-calendar", "notification-state"],
    ),
    "260319-llm-tool-hub": _spec(
        "tool-registry", "사용자 요청에서 도구 실행과 운영 상태까지", "도구 레지스트리와 메모리 어댑터를 분리해 요청을 선택된 provider 실행으로 연결하고 운영 상태를 확인한다.",
        [_node("user-request", "사용자 요청", "input", "사용자가 원하는 작업과 도구를 자연어로 요청한다.", "provider-adapter"), _node("tool-registry", "도구 레지스트리", "state", "도구의 capability와 운영 메타데이터를 정본으로 관리한다.", "source-separation"), _node("memory-adapter", "메모리 어댑터", "service", "공통 프로필과 도구별 입력 형식 사이를 변환한다.", "adapter-generation"), _node("provider-run", "Provider 실행", "service", "공통 prompt 계약 뒤에 서로 다른 LLM provider를 배치한다.", "provider-adapter"), _node("usage-status", "로그인·사용량·상태", "output", "인증, 사용량과 갱신 실패를 운영자가 확인할 수 있게 남긴다.", "access-state")],
        [("user-request", "tool-registry", "도구 선택"), ("tool-registry", "memory-adapter", "입력 변환"), ("memory-adapter", "provider-run", "공통 prompt"), ("provider-run", "usage-status", "실행 상태")], ["source-separation", "adapter-generation", "provider-adapter"],
    ),
    "260321-memento-mori-archive": _spec(
        "private-content-service", "기록 작성에서 공개·비공개 응답까지", "개인 기록을 저장하고 요청자의 권한에 따라 본문·목록·관리 기능을 다르게 제공한다.",
        [_node("journal-entry", "개인 기록", "input", "사용자가 작성하거나 수정하려는 기록 본문이다.", "split-public-runtime-data"), _node("volume-storage", "영속 저장소", "state", "runtime data와 legacy 데이터를 공개 정적 파일과 분리해 보존한다.", "volume-and-migration"), _node("session-auth", "서명 세션", "guardrail", "HttpOnly cookie와 서버 검증으로 요청자의 접근 권한을 확인한다.", "server-side-auth-cookie"), _node("access-router", "접근별 API", "service", "관리자·채팅 archive·개별 글 접근을 서로 다른 인증 경계로 처리한다.", "split-auth-scopes"), _node("safe-response", "안전한 응답", "output", "잠긴 요청에는 본문과 excerpt 대신 고정된 비공개 응답만 돌려준다.", "sanitize-private-response")],
        [("journal-entry", "volume-storage", "저장"), ("volume-storage", "session-auth", "권한 확인"), ("session-auth", "access-router", "접근 경로 선택"), ("access-router", "safe-response", "공개 범위 적용")], ["volume-and-migration", "server-side-auth-cookie", "split-auth-scopes", "sanitize-private-response"],
    ),
    "260322-polite-message-extension": _spec(
        "browser-extension-service", "선택한 문장에서 다듬은 문장까지", "브라우저에서 선택한 문장과 수신자·톤을 서버 재작성 요청으로 보내고 결과를 다시 삽입하거나 복사한다.",
        [_node("selected-text", "선택한 문장", "input", "사용자가 웹페이지나 메일에서 다듬을 문장을 선택한다.", "rewrite-contract"), _node("rewrite-context", "수신자와 톤", "input", "재작성에 필요한 수신자와 말투를 구조화한다.", "rewrite-contract"), _node("extension-popup", "확장 팝업", "interface", "입력과 결과를 확인하고 사용자가 다음 행동을 선택하는 화면이다.", "implementation-flow"), _node("rewrite-api", "재작성 API", "service", "세션과 사용량을 확인한 뒤 외부 모델 호출을 서버에서 수행한다.", "backend-boundary"), _node("insert-or-copy", "삽입·복사 결과", "output", "완성된 문장을 원래 입력 위치에 넣거나 클립보드로 전달한다.", "release-package")],
        [("selected-text", "rewrite-context", "맥락 추가"), ("rewrite-context", "extension-popup", "입력 확인"), ("extension-popup", "rewrite-api", "서버 요청"), ("rewrite-api", "insert-or-copy", "결과 반환")], ["rewrite-contract", "backend-boundary", "release-package"],
    ),
    "260324-central-memory-prompt-kit": _spec(
        "memory-distribution", "중앙 메모리에서 도구별 참조까지", "하나의 canonical profile과 공유 메모리를 각 도구가 읽을 수 있는 어댑터와 카탈로그로 배포한다.",
        [_node("canonical-profile", "Canonical profile", "state", "사용자의 안정적인 특성과 응답 선호를 하나의 정본으로 관리한다.", "canonical-profile-adapters"), _node("shared-memory", "공유 메모리", "state", "전역 작업 규칙과 프로젝트 인덱스를 자동 대화 저장소와 구분해 둔다.", "ownership-replacement"), _node("tool-adapter", "도구별 어댑터", "service", "각 실행 도구의 입력 형식에 맞는 얇은 참조를 만든다.", "runtime-shareable-skills"), _node("skill-catalog", "스킬 카탈로그", "state", "런타임 스킬과 공개 설명 문서의 소유권을 별도로 기록한다.", "runtime-shareable-skills"), _node("runtime-context", "실행 컨텍스트", "output", "작업을 시작할 때 필요한 프로필·규칙·프로젝트 링크를 제공한다.", "implementation-flow")],
        [("canonical-profile", "shared-memory", "공통 정본"), ("shared-memory", "tool-adapter", "공통 정본 변환"), ("tool-adapter", "skill-catalog", "스킬 연결"), ("skill-catalog", "runtime-context", "실행 시 참조")], ["canonical-profile-adapters", "ownership-replacement", "runtime-shareable-skills"],
    ),
    "260329-tmap-clone": _spec(
        "navigation-flow", "도로 선택에서 주행 기록까지", "웹에서 설명 가능한 장거리 경로를 계산하고 지도에 표시한 뒤 실제 주행과 simulation 기록을 구분한다.",
        [_node("route-request", "장거리 경로 요청", "input", "최단거리보다 오래 달릴 도로와 설명 가능한 주행을 요청한다.", "explainable-long-drive"), _node("route-core", "경로 계산", "service", "경로 provider에서 받은 기본 경로를 주행 가능한 구간 구조로 만든다.", "core-enrichment-split"), _node("road-enrichment", "도로 부가정보", "service", "차선·속도·단속 등 신뢰 기준을 통과한 정보를 경로에 덧붙인다.", "trusted-driving-data"), _node("map-driving-ui", "지도·주행 화면", "interface", "heading-up 지도와 Road Master 상태로 현재 경로와 진입 방향을 보여 준다.", "road-traversal-session"), _node("drive-record", "실제 주행 기록", "output", "실제 차량 좌표와 simulation을 구분해 주행 결과를 저장한다.", "actual-drive-persistence")],
        [("route-request", "route-core", "경로 계산"), ("route-core", "road-enrichment", "부가정보 결합"), ("road-enrichment", "map-driving-ui", "지도 표시"), ("map-driving-ui", "drive-record", "주행 기록")], ["core-enrichment-split", "trusted-driving-data", "actual-drive-persistence"],
    ),
    "260331-iphone-calculator-clone": _spec(
        "state-machine-ui", "버튼 입력에서 계산 화면까지", "DOM 화면과 계산 상태를 분리하고 입력 상태에 따라 버튼 표시와 계산 결과를 전이시킨다.",
        [_node("key-input", "숫자·연산자 입력", "input", "사용자가 숫자, 연산자, 소수점과 equals를 누른다.", "engine-state"), _node("calculator-state", "계산 상태", "state", "현재 피연산자·연산자·결과·반복 equals를 DOM과 독립적으로 보존한다.", "engine-state"), _node("button-mode", "AC·C 상태", "interface", "계산 상태에 맞춰 지우기 버튼과 연산자 교체 동작을 바꾼다.", "clear-state"), _node("display-result", "계산기 화면", "output", "세로 4칙연산 UI에 상태와 결과를 안정적으로 표시한다.", "interface-contract")],
        [("key-input", "calculator-state", "상태 전이"), ("calculator-state", "button-mode", "버튼 상태"), ("calculator-state", "display-result", "결과 렌더링")], ["engine-state", "clear-state"],
    ),
    "260401-wine-cellar-scan": _spec(
        "scan-confirmation", "라벨 이미지에서 와인 장부까지", "OCR 후보를 자동 확정하지 않고 사용자의 확인을 거쳐 개인 장부 카드로 저장한다.",
        [_node("label-image", "라벨 이미지", "input", "사용자가 촬영하거나 올린 와인 라벨 사진이다.", "planning-background"), _node("ocr-candidates", "OCR 후보", "service", "이미지에서 읽힌 이름과 빈티지 후보를 여러 값으로 제공한다.", "confirmation-flow"), _node("user-confirmation", "사용자 확인", "guardrail", "인식 결과를 그대로 확정하지 않고 사용자가 올바른 항목을 고른다.", "confirmation-flow"), _node("cellar-record", "개인 장부", "state", "확정된 와인과 시음·재구매 메모를 개인 JSON으로 보존한다.", "local-ledger-scope"), _node("wine-card", "와인 카드", "output", "저장된 행을 다시 읽기 쉬운 카드와 목록으로 보여 준다.", "grouped-cellar-book")],
        [("label-image", "ocr-candidates", "후보 추출"), ("ocr-candidates", "user-confirmation", "확인 요청"), ("user-confirmation", "cellar-record", "확정 저장"), ("cellar-record", "wine-card", "카드 표시")], ["confirmation-flow", "local-ledger-scope"],
    ),
    "260405-execution-harness-system": _spec(
        "agent-execution-control", "요청에서 승인된 실행과 검증까지", "대표 요청을 실행 계획과 handoff packet으로 바꾸고 승인·구현·검증 상태를 분리해 관리한다.",
        [_node("task-intake", "대표 요청", "actor", "사람이 해결하려는 업무와 완료 조건을 하나의 intake로 넣는다.", "structured-handoff"), _node("execution-plan", "실행 계획", "process", "구현자에게 범위·산출물·검증 조건을 구조화해 전달한다.", "executable-plan"), _node("approval-gate", "사람 승인", "guardrail", "실제 구현과 외부 효과가 발생하기 전에 진행 여부를 확인한다.", "preview-completion-gate"), _node("agent-run", "에이전트 실행", "service", "Python orchestrator와 Codex backend가 승인된 단계를 수행한다.", "switch-to-cli-backend"), _node("verification-report", "검증 보고", "output", "구현 검증과 사용자 수용 검증을 별도 상태로 기록한다.", "split-sqe-sqa")],
        [("task-intake", "execution-plan", "계획 작성"), ("execution-plan", "approval-gate", "승인 요청"), ("approval-gate", "agent-run", "승인 후 dispatch"), ("agent-run", "verification-report", "검증 인계")], ["executable-plan", "preview-completion-gate", "split-sqe-sqa"],
    ),
    "260408-ideal-type-editorial": _spec(
        "curation-workflow", "신청 데이터에서 소개 패키지까지", "후보 분석을 자동 매칭으로 확정하지 않고 운영자 검토를 거쳐 소개용 결과물로 만든다.",
        [_node("application", "신청 데이터", "input", "사용자가 제공한 자기소개와 선호 정보다.", "implementation-flow"), _node("candidate-set", "후보 묶음", "process", "비교할 후보를 제한된 수로 선택하고 분석 대상 집합을 만든다.", "bounded-selection"), _node("trait-analysis", "외모·성격 분석", "service", "외모와 성격을 분리된 분석 단계와 구조화 결과로 처리한다.", "split-analysis"), _node("operator-review", "운영자 큐", "guardrail", "자동 결과를 바로 매칭하지 않고 사람이 검토·수정한다.", "manual-curation"), _node("intro-package", "소개 패키지", "output", "검토된 후보와 설명을 다음 운영 단계에서 사용할 패키지로 만든다.", "editorial-output")],
        [("application", "candidate-set", "후보 선택"), ("candidate-set", "trait-analysis", "분석"), ("trait-analysis", "operator-review", "검토 대기"), ("operator-review", "intro-package", "소개 패키지")], ["bounded-selection", "split-analysis", "manual-curation"],
    ),
    "260410-keyboard-piano": _spec(
        "browser-instrument", "키 입력에서 피아노 소리와 연습 화면까지", "브라우저 키보드 입력을 음계와 피아노 샘플 재생으로 연결하고 연주·연습 상태를 화면에 표시한다.",
        [_node("keyboard-input", "키보드 입력", "input", "설치 없이 브라우저에서 컴퓨터 키를 누른다.", "keyboard-map"), _node("note-mapping", "반음계 매핑", "process", "J 키를 중심으로 각 키를 음계와 연결한다.", "keyboard-map"), _node("piano-samples", "피아노 샘플", "service", "합성음 대신 매핑된 건반의 피아노 음원을 재생한다.", "sample-audio-rollback"), _node("play-mode", "연주·연습 상태", "state", "자유 연주와 낙하 노트 연습 흐름을 구분한다.", "practice-mode"), _node("piano-screen", "건반 화면", "interface", "현재 입력과 다음 노트를 시각적으로 보여 준다.", "implementation-flow")],
        [("keyboard-input", "note-mapping", "음계 변환"), ("note-mapping", "piano-samples", "소리 선택"), ("piano-samples", "play-mode", "연주 상태"), ("play-mode", "piano-screen", "화면 표시")], ["keyboard-map", "sample-audio-rollback", "practice-mode"],
    ),
    "260413-dictionary-transition-bundle": _spec(
        "dataset-release-pipeline", "명령 입력에서 배포 가능한 사전까지", "기능 호출 사전을 역할별 자산으로 나누고 생성·평가·홀드아웃 gate를 거쳐 배포한다.",
        [_node("command-input", "한국어 명령", "input", "사용자가 말하거나 입력한 기능 요청이다.", "precision-recall-contract"), _node("dictionary-bundle", "역할별 사전", "state", "mapping, contains_token 등 서로 다른 목적의 사전을 별도 자산으로 관리한다.", "four-dictionary-roles"), _node("generator", "데이터 생성기", "process", "alias·dependency와 조건 조합을 규칙에 따라 테스트 행으로 만든다.", "implementation-assets"), _node("holdout-eval", "홀드아웃 평가", "guardrail", "raw·corrected·holdout 모집단을 분리해 정확도와 경계를 평가한다.", "holdout-release-gate"), _node("release-bundle", "배포 번들", "output", "통과한 사전과 평가 결과를 runtime이 읽을 수 있는 형태로 묶는다.", "implementation-assets")],
        [("command-input", "dictionary-bundle", "사전 조회"), ("dictionary-bundle", "generator", "생성 규칙"), ("generator", "holdout-eval", "평가 입력"), ("holdout-eval", "release-bundle", "배포 gate")], ["four-dictionary-roles", "precision-recall-contract", "holdout-release-gate"],
    ),
    "260418-japanese-word-study": _spec(
        "learning-loop", "학습 답안에서 다음 복습까지", "답안 판정과 연속 정답 상태를 바탕으로 복습 우선 세션과 계정 동기화를 만든다.",
        [_node("word-bank", "단어 카드", "input", "JLPT 급수별 학습 카드와 현재 상태를 제공한다.", "planning-background"), _node("session-selector", "복습 세션", "process", "오답과 due 카드를 신규 단어보다 먼저 골라 세션을 만든다.", "review-first-selection"), _node("answer-checker", "답안 판정", "service", "정규화·동의어를 먼저 적용하고 필요한 경우 의미 유사도를 보조로 사용한다.", "answer-evaluation"), _node("mastery-state", "연속 정답 상태", "state", "연속 성공 횟수로 다음 복습 간격과 archive 여부를 계산한다.", "mastery-state"), _node("progress-sync", "진행도·계정 동기화", "output", "로컬 학습 기록을 보존하면서 로그인 계정과 병합한다.", "sync-merge")],
        [("word-bank", "session-selector", "카드 선택"), ("session-selector", "answer-checker", "답안 입력"), ("answer-checker", "mastery-state", "상태 갱신"), ("mastery-state", "progress-sync", "진행도 저장")], ["review-first-selection", "answer-evaluation", "mastery-state", "sync-merge"],
    ),
    "260619-chat-friends": _spec(
        "relationship-chat", "대화 입력에서 관계 기억까지", "텍스트·음성 대화와 이미지 흐름을 공통 대화 상태에 연결하고 기억 추출과 안전 처리를 분리한다.",
        [_node("message-input", "텍스트·음성 입력", "input", "사용자가 채팅 또는 실시간 음성으로 관계 맥락을 이어 간다.", "persona-and-entry"), _node("conversation-state", "대화 상태", "state", "현재 대화와 선톡·단체 대화 같은 관계 흐름을 관리한다.", "proactive-and-group-flow"), _node("response-service", "응답 생성", "service", "구조화 응답 복구와 안전 대화를 포함한 답변을 만든다.", "parser-and-safety"), _node("memory-extractor", "기억 추출", "process", "답변 저장과 장기 기억 추출을 별도 작업으로 처리한다.", "async-memory-boundary"), _node("relationship-memory", "관계 기억", "output", "삭제 권한과 생활 상태를 고려해 다음 대화의 맥락으로 제공한다.", "relationship-memory")],
        [("message-input", "conversation-state", "대화 갱신"), ("conversation-state", "response-service", "응답 요청"), ("response-service", "memory-extractor", "기억 후보"), ("memory-extractor", "relationship-memory", "기억 반영")], ["async-memory-boundary", "parser-and-safety", "relationship-memory"],
    ),
    "260621-easy-news": _spec(
        "news-publishing", "뉴스 원천에서 오늘 읽기 화면까지", "검토된 seed와 RSS를 수집해 이슈 타임라인과 원자적 snapshot으로 제공한다.",
        [_node("news-sources", "뉴스 원천", "input", "검토된 seed와 외부 RSS에서 기사 후보를 받는다.", "staged-mvp"), _node("issue-timeline", "이슈 타임라인", "process", "거대한 관계 그래프 대신 한 이슈의 시간 흐름으로 정리한다.", "issue-reading-model"), _node("reviewed-snapshot", "검토된 snapshot", "state", "반쯤 갱신된 결과가 공개되지 않도록 한 번에 교체할 발행 상태다.", "atomic-snapshot"), _node("watch-list", "저장·지켜보기", "state", "나중에 읽기와 계속 추적하기의 사용자 의도를 분리한다.", "save-and-watch"), _node("mobile-reader", "모바일 읽기 화면", "output", "짧은 시간에 이슈 흐름을 읽고 접근성 기준을 확인하는 화면이다.", "mobile-quality")],
        [("news-sources", "issue-timeline", "수집·정리"), ("issue-timeline", "reviewed-snapshot", "검토 후 발행"), ("reviewed-snapshot", "watch-list", "사용자 저장"), ("reviewed-snapshot", "mobile-reader", "오늘 화면")], ["issue-reading-model", "atomic-snapshot", "mobile-quality"],
    ),
    "260626-make-test-set": _spec(
        "testset-generation", "제품 정의에서 검증 가능한 테스트셋까지", "제품 문서의 slot·alias·dependency와 route 경계를 조합해 positive·negative·command 테스트셋을 생성한다.",
        [_node("product-spec", "제품 명세", "input", "기능, slot과 지원 범위를 정의한 원천 문서다.", "slot-model"), _node("coverage-model", "상태·의존성 모델", "process", "slot 상태와 alias·dependency를 별도 규칙으로 정리한다.", "alias-dependency"), _node("case-generator", "테스트 생성기", "service", "조건 조합 하나를 한 행으로 유지하며 schedule matrix를 생성한다.", "generator-ownership"), _node("route-datasets", "세 종류 테스트셋", "state", "positive는 source span, negative는 경계, command는 action family를 보존한다.", "positive-data"), _node("coverage-gate", "커버리지 gate", "guardrail", "생성 통과와 실제 command coverage를 구분해 다음 작업을 판단한다.", "command-gap")],
        [("product-spec", "coverage-model", "규칙 추출"), ("coverage-model", "case-generator", "조합 생성"), ("case-generator", "route-datasets", "셋 분리"), ("route-datasets", "coverage-gate", "커버리지 확인")], ["alias-dependency", "generator-ownership", "positive-data", "command-gap"],
    ),
    "260725-household-account-book": _spec(
        "local-finance-app", "금액 입력에서 연간 비교 화면까지", "월별 기록을 단일 JSON에 원자적으로 저장하고 연간 비교가 가능한 표와 얇은 Windows 실행기로 제공한다.",
        [_node("amount-input", "금액 입력", "input", "금액 입력 자체를 기록 완료로 취급한다.", "annual-table-state"), _node("annual-table", "연간 비교 표", "interface", "월별 화면을 오가는 대신 한 해의 수입·지출을 비교한다.", "annual-table-state"), _node("json-ledger", "단일 JSON 원장", "state", "기존 로컬 기록을 보존하면서 원자 교체로 저장한다.", "atomic-json-store"), _node("summary-calculation", "중간 합계", "process", "위치 기반 합계와 표의 용어를 일관되게 계산한다.", "table-language"), _node("windows-shell", "Windows 실행기", "output", "웹 화면을 여는 얇은 데스크톱 진입점이다.", "windows-shell")],
        [("amount-input", "annual-table", "표에 반영"), ("annual-table", "json-ledger", "원장 저장"), ("json-ledger", "summary-calculation", "합계 계산"), ("summary-calculation", "windows-shell", "실행 화면")], ["annual-table-state", "atomic-json-store", "table-language"],
    ),
    "260727-server-app-web-learn-book": _spec(
        "documentation-publishing", "원고에서 검색 가능한 학습서까지", "Markdown 원고와 glossary를 정본으로 삼아 PM 질문 중심의 정적 HTML과 검색 색인을 만든다.",
        [_node("pm-question", "PM 질문", "input", "구현 단계보다 의사결정 맥락을 알고 싶은 질문에서 학습 단위를 시작한다.", "decision-centered-lessons"), _node("markdown-source", "Markdown 원고", "state", "10권 구조와 실제 관찰을 담는 출판 정본이다.", "markdown-canonical-source"), _node("glossary", "용어집", "state", "본문과 분리된 정의와 검색어를 관리한다.", "two-stage-search"), _node("html-builder", "정적 HTML 생성", "process", "원고를 브라우저에서 읽는 문서와 검색 index로 변환한다.", "implementation-flow"), _node("learning-site", "학습서 웹", "output", "기술 정의와 의사결정 맥락을 연결해 탐색할 수 있는 결과물이다.", "verified-assets")],
        [("pm-question", "markdown-source", "원고 구성"), ("markdown-source", "glossary", "용어 추출"), ("markdown-source", "html-builder", "HTML 변환"), ("glossary", "html-builder", "검색 index"), ("html-builder", "learning-site", "출판")], ["markdown-canonical-source", "two-stage-search"],
    ),
    "260802-map-diary": _spec(
        "road-recording", "도로 검색에서 방문 기록까지", "VWorld 원본 도로를 검색·선택하고 Feature ID와 geometry snapshot을 방문 기록으로 보존한다.",
        [_node("road-search", "도로 검색", "input", "사용자가 도로명과 지역으로 저장할 후보를 찾는다.", "vworld-road-layer"), _node("vworld-feature", "VWorld 도로 Feature", "service", "도로명·코드·Feature ID·geometry를 가진 원본 객체다.", "source-feature-record"), _node("selected-segment", "선택 구간", "interface", "검색 후보와 사용자가 확정한 구간을 다른 상태로 표시한다.", "visual-state-layers"), _node("geometry-snapshot", "geometry snapshot", "state", "확정 시점의 Feature ID와 잘라낸 선형을 함께 보존한다.", "geometry-snapshot"), _node("visit-record", "방문 기록", "output", "방문 날짜와 횟수를 상세 패널에서 다시 보여 준다.", "date-in-details")],
        [("road-search", "vworld-feature", "원본 조회"), ("vworld-feature", "selected-segment", "후보 표시"), ("selected-segment", "geometry-snapshot", "구간 확정"), ("geometry-snapshot", "visit-record", "방문 저장")], ["source-feature-record", "vworld-road-layer", "geometry-snapshot"],
    ),
    "260802-map-diary-v2": _spec(
        "planned-route-recording", "계획 경로에서 방문 기록까지", "TMAP은 계획 경로를 만들고 VWorld는 확정 도로를 보존하며, 사용자가 확인한 결과만 trip record가 된다.",
        [_node("trip-plan", "주행 계획", "input", "출발·도착과 사용자 경유 pin으로 계획을 만든다.", "provider-role-boundary"), _node("tmap-preview", "TMAP 계획 경로", "service", "외부 provider의 경로를 미리보기와 안내 후보로만 사용한다.", "provider-adapter-proxy"), _node("vworld-confirmation", "VWorld 확정 도로", "service", "실제로 기록할 도로의 원본과 geometry를 확인한다.", "route-trip-spot-flow"), _node("trip-record", "trip·route·spot 기록", "state", "계획·도로 그룹·방문 지점을 서로 다른 데이터 단위로 저장한다.", "route-trip-spot-flow"), _node("static-preview", "정적 미리보기", "output", "GPS 주행을 먼저 구현하지 않고 계획 결과를 확인하는 화면을 제공한다.", "scope-rollback-static-preview")],
        [("trip-plan", "tmap-preview", "계획 계산"), ("tmap-preview", "vworld-confirmation", "확정 후보"), ("vworld-confirmation", "trip-record", "방문 저장"), ("tmap-preview", "static-preview", "미리보기")], ["provider-role-boundary", "scope-rollback-static-preview", "route-trip-spot-flow"],
    ),
    "260802-map-diary-v3": _spec(
        "hybrid-drive-recording", "주행 센서에서 영구 도로 기록까지", "네이티브 SQLite가 raw drive를 보존하고 WebView는 동기화된 후보를 검토해 승인된 도로만 영구 기록으로 확정한다.",
        [_node("native-location", "네이티브 위치 기록", "input", "iOS 주행 중 위치와 센서 이벤트를 raw drive로 수집한다.", "native-sqlite-source"), _node("raw-drive-db", "Native SQLite", "state", "짧은 보존 기간의 원시 주행 데이터를 기기 정본으로 저장한다.", "state-based-retention"), _node("webview-sync", "WebView 동기화", "service", "sequence cursor로 새 기록만 웹 화면에 전달한다.", "sequence-paging"), _node("road-candidates", "도로 후보·분석", "process", "TMAP 정보는 gap 후보로만 쓰고 분석 실패와 provider 실패를 분리한다.", "tmap-candidate-only"), _node("approved-road", "승인된 도로 snapshot", "output", "사용자 검토와 revision CAS를 통과한 도로만 장기 보존한다.", "approved-snapshot-only")],
        [("native-location", "raw-drive-db", "raw 저장"), ("raw-drive-db", "webview-sync", "cursor 동기화"), ("webview-sync", "road-candidates", "후보 분석"), ("road-candidates", "approved-road", "사용자 확정")], ["native-sqlite-source", "sequence-paging", "approved-snapshot-only"],
    ),
    "260803-ai-office": _spec(
        "approval-workflow", "대표 지시에서 완료 검증까지", "하나의 intake를 모드·부서 stage로 dispatch하고 승인·경로 확인·검증 gate를 거쳐 완료로 판정한다.",
        [_node("executive-intake", "대표 지시", "actor", "사람이 보고만 받을지 실제 구현을 맡길지 요청한다.", "single-intake"), _node("work-mode", "업무 모드", "process", "report-only와 implementation을 실행 전에 구분한다.", "handoff-mode"), _node("stage-dispatch", "부서 stage", "service", "각 단계의 담당 agent와 산출물을 연결한다.", "stage-ownership"), _node("runtime-preflight", "실행 전 검사", "guardrail", "dispatch 전에 runtime, 경로와 checkout을 확인한다.", "runtime-preflight"), _node("completion-gate", "완료 검증", "output", "요청한 파일·경로가 실제로 존재하고 검증을 통과했을 때 완료로 기록한다.", "path-proof")],
        [("executive-intake", "work-mode", "모드 선택"), ("work-mode", "stage-dispatch", "stage 배정"), ("stage-dispatch", "runtime-preflight", "실행 전 검사"), ("runtime-preflight", "completion-gate", "완료 판정")], ["handoff-mode", "stage-ownership", "runtime-preflight", "path-proof"],
    ),
    "a2a-lambda": _spec(
        "agent-routing", "질문에서 제한된 backend 실행까지", "feature flag와 응답 envelope를 유지하면서 family agent와 실제 backend의 경계를 지키는 A2A 라우팅이다.",
        [_node("incoming-question", "준비된 질문", "input", "지원 범위와 실행 조건을 가진 질문을 받는다.", "dqr-frg-bridge"), _node("route-envelope", "A2A 응답 계약", "state", "depth·family·상태를 포함한 공통 envelope로 전달한다.", "flag-and-envelope"), _node("family-agent", "Family agent", "service", "기능별 질문을 담당하지만 실제 외부 실행의 소유권은 넘겨받지 않는다.", "family-agents"), _node("backend-boundary", "실제 backend", "service", "action·schedule 등 실제 실행 가능 여부를 별도 경계에서 판단한다.", "bounded-delegation"), _node("validated-response", "검증된 응답", "output", "flag와 자유 질의 경계를 포함해 전환 가능한 결과를 반환한다.", "validation")],
        [("incoming-question", "route-envelope", "계약 생성"), ("route-envelope", "family-agent", "family 전달"), ("family-agent", "backend-boundary", "제한된 위임"), ("backend-boundary", "validated-response", "응답 반환")], ["flag-and-envelope", "bounded-delegation", "family-agents"],
    ),
    "a2a-normal": _spec(
        "retrieval-routing", "질문에서 답변 근거까지", "route_turn이 질문을 분류하고 retrieval 후보·재순위화·DQR 평가를 별도 계약으로 처리한다.",
        [_node("user-query", "사용자 질문", "input", "일반 대화, 라우팅 또는 문서 검색이 필요한 질문이다.", "route-entry"), _node("route-classifier", "라우팅 분류", "process", "heuristic·planner·fallback 중 사용한 경로를 표시한다.", "route-source"), _node("retrieval-candidates", "검색 후보", "service", "문서에서 답변 후보를 생성하고 layout-aware 경로는 별도 조건으로 둔다.", "retrieval-stack"), _node("reranked-context", "재순위화 컨텍스트", "process", "후보를 답변에 사용할 근거 순서로 정리한다.", "retrieval-stack"), _node("answer-gate", "로컬 평가 gate", "guardrail", "고정 holdout과 DQR 질의를 나눠 retrieval 품질을 확인한다.", "fixed-holdout")],
        [("user-query", "route-classifier", "질문 분류"), ("route-classifier", "retrieval-candidates", "검색 요청"), ("retrieval-candidates", "reranked-context", "재순위화"), ("reranked-context", "answer-gate", "근거 평가")], ["route-entry", "retrieval-stack", "fixed-holdout"],
    ),
    "a2a-test": _spec(
        "agent-test-lifecycle", "지원 범위에서 재현 가능한 평가까지", "capability registry를 기준으로 라우팅 테스트를 만들고 실행 결과와 점수, runtime 반영을 분리한다.",
        [_node("capability-registry", "Capability registry", "state", "현재 지원하는 기능과 route의 정본이다.", "registry-source"), _node("preclassifier", "사전 분류", "process", "최종 정책을 결정하지 않고 관찰용 증거만 제공한다.", "preclassifier"), _node("route-run", "Stage 1 route", "service", "질문을 담당 route로 보내고 실행 결과를 수집한다.", "stage-ownership"), _node("policy-score", "정책·최종 점수", "guardrail", "정책 score와 final score를 섞지 않고 평가한다.", "scoring-boundary"), _node("runtime-result", "재현 결과", "output", "source 수정, runtime 반영과 재실행 완료 여부를 구분해 남긴다.", "runtime-sync")],
        [("capability-registry", "preclassifier", "지원 범위 확인"), ("preclassifier", "route-run", "route 증거"), ("route-run", "policy-score", "점수 계산"), ("policy-score", "runtime-result", "결과 기록")], ["registry-source", "stage-ownership", "scoring-boundary", "runtime-sync"],
    ),
    "gemini-multiturn-tester-v3": _spec(
        "multiturn-evaluation", "테스트 행에서 재현 로그까지", "공통 실행 계약으로 persona·history를 관리하고 provider 응답과 실패 원문을 행별로 보존한다.",
        [_node("xlsx-row", "테스트 행", "input", "한 행의 질문과 persona를 하나의 세션 실행으로 취급한다.", "row-isolation"), _node("session-state", "history·persona 상태", "state", "멀티턴 history와 persona를 다음 요청에 명시적으로 전달한다.", "session-state"), _node("provider-runner", "Provider 실행기", "service", "세 실행 표면이 공통 요청·응답 계약을 사용한다.", "shared-runner"), _node("raw-response", "원시 응답", "state", "schema 실패나 네트워크 오류에도 요청과 응답 원문을 보존한다.", "json-recovery"), _node("replay-report", "재현 로그·평가", "output", "실행 흔적과 품질 평가를 분리해 다음 분석에서 다시 사용할 수 있게 한다.", "full-call-log")],
        [("xlsx-row", "session-state", "세션 초기화"), ("session-state", "provider-runner", "공통 요청"), ("provider-runner", "raw-response", "응답 보존"), ("raw-response", "replay-report", "재현 기록")], ["shared-runner", "session-state", "json-recovery", "full-call-log"],
    ),
    "operation-log-analayzer": _spec(
        "operational-log-pipeline", "로그 파일에서 월별 세션 산출물까지", "손상 입력을 격리하고 중복 제거·시간순 세션 복원·상태 계산을 거쳐 품질 산출물을 만든다.",
        [_node("log-files", "운영 로그 파일", "input", "여러 파일에 흩어진 이벤트와 인코딩 상태를 입력으로 받는다.", "quarantine-corrupt-input"), _node("clean-event-stream", "정제 이벤트 스트림", "process", "손상 파일을 중단시키지 않고 격리한 뒤 명시적으로 중복 제거한다.", "explicit-dedup"), _node("session-state-machine", "세션 상태 기계", "process", "SQLite 오름차순 스트리밍으로 log_id별 FIFO pairing과 세션 순서를 복원한다.", "session-state-machine"), _node("quality-signals", "검색·실패 품질 신호", "state", "검색 후보와 실제 실행, 실패 원인과 제품 backlog를 분리한다.", "split-search-signals"), _node("monthly-artifacts", "월별 산출물", "output", "재현 가능한 월별 파일과 인계 자료로 결과를 남긴다.", "implementation-flow")],
        [("log-files", "clean-event-stream", "정제·격리"), ("clean-event-stream", "session-state-machine", "세션 복원"), ("session-state-machine", "quality-signals", "품질 계산"), ("quality-signals", "monthly-artifacts", "산출물 생성")], ["quarantine-corrupt-input", "explicit-dedup", "session-state-machine", "split-search-signals"],
    ),
    "semantic-verb-schema": _spec(
        "language-schema-pipeline", "한국어 문장에서 동사 의미 스키마까지", "문장을 entity와 action으로 나누고 형태 정보를 보존한 태깅·후보 생성 파이프라인으로 바꾼다.",
        [_node("korean-command", "한국어 명령", "input", "기능을 수행하려는 자연어 문장이다.", "entity-action-split"), _node("kiwi-parser", "형태 분석", "service", "규칙만으로 자르지 않고 Kiwi 기반으로 어근·어미·표면형을 분석한다.", "replace-rule-retagging"), _node("action-schema", "동사 의미 스키마", "state", "동작을 열 가지 의미 유형과 액션 구성요소로 표현한다.", "action-type-contract"), _node("retagging-pipeline", "재태깅 파이프라인", "process", "말뭉치 확장과 후보 생성을 단계별로 실행한다.", "staged-corpus-pipeline"), _node("schema-assets", "학습·평가 자산", "output", "학습 데이터와 사전 평가의 소유권을 분리해 결과를 관리한다.", "split-asset-ownership")],
        [("korean-command", "kiwi-parser", "형태 분석"), ("kiwi-parser", "action-schema", "의미 분류"), ("action-schema", "retagging-pipeline", "후보 생성"), ("retagging-pipeline", "schema-assets", "자산 저장")], ["entity-action-split", "replace-rule-retagging", "action-type-contract", "split-asset-ownership"],
    ),
    "todack": _spec(
        "personal-agent-service", "감정 입력에서 개인화된 보조 작업까지", "웹·모바일 입력을 사용자 원장과 개인화 프로필에 연결하고 대화·캡슐·미션을 같은 계정 경계에서 처리한다.",
        [_node("feeling-entry", "감정·대화 입력", "input", "웹, 모바일과 음성 채널에서 사용자의 기록과 대화를 받는다.", "common-product-boundary"), _node("identity-session", "사용자 세션", "guardrail", "브라우저와 모바일의 세션 전달 방식을 사용자 단위로 통일한다.", "identity-and-session"), _node("personalization", "프로필·기억", "state", "사용자별 프롬프트와 기억을 다른 사용자의 데이터와 섞지 않는다.", "profile-evolution"), _node("assistant-actions", "대화·캡슐·미션", "service", "대화 응답, 미래 캡슐과 미션 상태를 서버에서 처리한다.", "capsule-scheduling"), _node("user-dashboard", "기록·통계 화면", "output", "감정 기록과 기간별 통계를 다시 보여 주되 관측 강도와 표본을 함께 고려한다.", "statistics-model")],
        [("feeling-entry", "identity-session", "사용자 식별"), ("identity-session", "personalization", "프로필 조회"), ("personalization", "assistant-actions", "개인화 실행"), ("assistant-actions", "user-dashboard", "기록·통계 반영")], ["common-product-boundary", "identity-and-session", "profile-evolution", "statistics-model"],
    ),
}
