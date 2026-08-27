# Build Story

- 문제: 모델, 도구 추천, 프로젝트 상태와 작업 규칙이 여러 파일에 흩어졌습니다.
- 접근: registry와 추천 규칙을 분리하고 canonical memory에서 도구별 adapter를 생성했습니다.
- 결과: 탐색, 재사용과 도구 간 메모리 동기화를 하나의 운영 화면으로 묶었습니다.
- 인증 경계를 강화하고 tool-specific 파일을 파생 adapter로 재정의했습니다.
