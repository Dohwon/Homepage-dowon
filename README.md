# Portfolio Homepage

카카오 스타일 레퍼런스를 반영한 개인 포트폴리오 앱이다. 기존 정적 페이지를 운영형 Node 서버로 확장해 카드 기반 프로젝트 탐색, 관리자 CMS, 댓글, 방문자 집계, Google 로그인 연결 지점을 제공한다.

## 주요 기능

- 카드 라이브러리형 메인 화면과 블러 상세 모달
- 카드 호버 시 영상 재생 또는 모션 목업 프리뷰
- Google 로그인 기반 권한 분리
  - 비로그인: 읽기
  - 로그인 사용자: 읽기 + 댓글
  - 관리자 이메일: 카드 생성/수정/삭제 + 방문 통계
- 파일 기반 저장소
  - `data/site-content.json`: 사이트/카드 메인 데이터
  - `data/comments.json`: 댓글
  - `data/analytics.jsonl`: 방문 이벤트
- `deploy/systemd/portfolio-homepage.service` 포함

## 파일 구조

- `server.js`: 정적 자산 + API 서버
- `index.html`: 메인 레이아웃
- `styles.css`: 카카오 레퍼런스 기반 UI
- `app.js`: 프론트엔드 상태/렌더링/인증/UI 로직
- `data/projects.json`, `data/projects.generated.json`: 초기 시드 원본
- `data/site-content.json`: 서버 첫 실행 시 자동 생성되는 운영 데이터
- `deploy/DEPLOY.md`: 배포 메모

## 실행

1. `.env.example`을 참고해 `.env`를 만든다.
2. 필수값을 채운다.

```env
SESSION_SECRET=...
GOOGLE_CLIENT_ID=...
ADMIN_EMAILS=your-email@example.com
```

3. 서버 실행

```bash
cd /home/dowon/securedir/git/codex/portfolio-homepage
node server.js
```

기본 포트는 `4173`이고 기본 바인딩은 `0.0.0.0`이다.

## 프리뷰 영상 연결

프로젝트 ID 기준으로 아래 파일을 두면 카드 hover 시 자동 사용된다.

- `data/previews/{project-id}.mp4`
- `data/previews/{project-id}.webm`
- `data/posters/{project-id}.jpg|jpeg|png|webp`

파일이 없으면 CSS 모션 목업이 기본 프리뷰로 표시된다.

## 운영 메모

- Google OAuth Origin은 실제 도메인 기준으로 등록해야 한다.
- `SESSION_SECRET`를 고정하지 않으면 서버 재시작 시 로그인 세션이 끊긴다.
- 개인 포트폴리오 트래픽 기준으로는 파일 저장소 구조로 충분하지만, 댓글량이 커지면 SQLite/Postgres로 옮기는 편이 안전하다.
