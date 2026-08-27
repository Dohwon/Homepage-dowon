# Build Story

- 문제: 하나의 프롬프트가 대화, 검색, 기기 질의와 일정 경계를 모두 판단하며 회귀가 커졌습니다.
- 접근: dictionary gate, family classifier, specialist와 selector로 책임을 나누고 judge를 분리했습니다.
- 결과: 라우팅 변경을 같은 테스트셋과 trace로 비교하는 평가 흐름을 만들었습니다.
- 판단 단계를 계층형 라우팅과 specialist 경로로 분해했습니다.
