# Build Story

- 문제: 라우팅 정확도 숫자만으로는 실제 planner 사용 여부와 fallback 의존성을 설명할 수 없었습니다.
- 접근: heuristic, live planner, stub executor와 검색 단계별 지표를 분리해 재현 가능한 벤치마크로 관리했습니다.
- 결과: 성능 수치와 실행 조건 및 남은 fallback을 함께 보고하는 품질 게이트를 구축했습니다.
- 실행 모드와 fallback 여부를 별도 검증 항목으로 재구성했습니다.
