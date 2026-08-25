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

## Project Atlas Worker

Worker는 로컬 workspace를 읽어 검토된 public profile과 직접 작성된 project memory만 `public-bundle/`로 만든다. 기본 출력은 key ordering이 고정된 JSON이며 absolute project root, raw session text, alias key, provenance를 출력하지 않는다.

### 명령

```bash
.venv/bin/python scripts/project_atlas.py discover --workspace /home/dowon/securedir/git/codex --format json
.venv/bin/python scripts/project_atlas.py bootstrap-profiles --workspace /home/dowon/securedir/git/codex --dry-run
.venv/bin/python scripts/project_atlas.py backfill --workspace /home/dowon/securedir/git/codex --sessions-root /path/to/codex/sessions --dry-run
.venv/bin/python scripts/project_atlas.py build --workspace /home/dowon/securedir/git/codex --dry-run
.venv/bin/python scripts/project_atlas.py validate --workspace /home/dowon/securedir/git/codex
.venv/bin/python scripts/project_atlas.py validate --fixture /path/to/public-bundle
.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex --dry-run
```

`discover`는 read-only다. `validate`도 bundle의 privacy, schema, hash, exact-tree contract만 읽어 검사하며 promotion을 호출하지 않는다. `backfill --dry-run`은 `--sessions-root`가 없고 `.knowledge-worker/config.yaml`에도 session root가 없으면 정상적인 zero-session 결과를 반환한다.

### Reviewed Apply

Profile 생성은 자동 적용하지 않는다. 먼저 `bootstrap-profiles --dry-run`의 ambiguous ID를 검토하고, 아래 형식의 JSON을 별도로 작성한 뒤 적용한다. 각 profile은 현재 발견된 ambiguous ID와 정확히 일치하고 `project-profile` schema를 통과해야 한다.

```json
{"profiles":[{"id":"project-id","name":"Reviewed Name","lifecycle":"active","publication":"private","summary":"Reviewed summary","tags":{"domain":["AI"],"problem":["Routing"],"pattern":["Evaluation"],"technology":["Python"],"outcome":["Tool"]}}]}
```

```bash
.venv/bin/python scripts/project_atlas.py bootstrap-profiles --workspace /home/dowon/securedir/git/codex --apply-reviewed-report /path/to/reviewed-profiles.json
```

Backfill도 자동으로 memory나 cursor를 쓰지 않는다. Dry-run JSON의 sanitized `claims`에서 적용할 항목만 남기고 `selected`를 `true`로 바꾼 reviewed report를 전달한다. Report에는 `project_id`, `claim_type`, `confidence`, `evidence_id`, `event_date`, normalized `value`, `selected`만 허용된다.

```bash
.venv/bin/python scripts/project_atlas.py backfill --workspace /home/dowon/securedir/git/codex --sessions-root /path/to/codex/sessions --dry-run > /path/to/reviewed-backfill.json
.venv/bin/python scripts/project_atlas.py backfill --workspace /home/dowon/securedir/git/codex --sessions-root /path/to/codex/sessions --apply-reviewed-report /path/to/reviewed-backfill.json
```

`build`와 `run`의 non-dry 실행은 명시적인 local alias-key material이 필요하다. Key 값은 출력하거나 repository에 저장하지 않는다.

```bash
export PROJECT_ATLAS_HMAC_KEY_PATH=/path/to/local/hmac.key
.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex
```

`PROJECT_ATLAS_HMAC_KEY` 환경변수 또는 `.knowledge-worker/config.yaml`의 `hmac_key_path`/`alias_key_file`도 지원한다. Runtime config의 `sessions_root`는 `backfill`과 `run`의 기본 session source다.

### Dry Run과 Exit Code

`bootstrap-profiles`, `backfill`, `build`, `run`은 `--dry-run`을 지원한다. Dry-run은 profile, project memory, session cursor, manifest state, `public-bundle/`을 쓰지 않는다. Bundle 후보는 service directory와 같은 filesystem의 자동 정리 temporary staging에서만 생성되고 promotion되지 않는다.

| Code | 의미 |
|---:|---|
| `0` | 성공 |
| `2` | argument, config, profile, schema, bundle validation 실패 |
| `3` | privacy gate 실패 |
| `4` | file 또는 directory I/O 실패 |

오류 stderr는 traceback이나 입력 원문 없이 category와 JSON pointer만 담은 JSON 한 줄이다.
