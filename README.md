# Dowon Project Atlas

`portfolio-homepage`와 기존 LLM Wiki의 역할을 합친 프로젝트 탐색 서비스다. 로컬
Project Atlas worker가 만든 검증된 `public-bundle/`만 공개 API로 읽으며, 프로젝트
목록·주제·변경 기록·검색·관계 그래프와 프로젝트별 작업 이야기를 한 화면에서
탐색한다. 기존 포트폴리오 CMS는 `/admin.html`에 그대로 보존한다.

## 공개 화면

- `/`: 최근 프로젝트와 주제 중심 홈
- `/projects`: 상태·도메인 필터가 있는 전체 프로젝트 목록
- `/projects/{id}`: Decisions, System Map, Build Timeline, Evidence 탭과 본문 기준
  읽기 진행률
- `/topics`, `/graph`, `/changelog`: 주제, 태그부터 프로젝트로 펼치는 2D 지식 그래프, 변경 기록
- `Cmd/Ctrl+K`: 전체 공개 번들 검색
- `/admin.html`: 기존 Google 로그인 기반 CMS
  - 비로그인: 읽기
  - 로그인 사용자: 읽기 + 댓글
  - 관리자 이메일: 카드 생성/수정/삭제 + 방문 통계

공개 Atlas API는 raw session, 로컬 경로, provenance를 제공하지 않는다. CMS override도
허용된 표시 필드만 병합하며 개인정보·비밀정보 패턴은 거부한다.

프로젝트 상세 화면은 공개할 실제 내용이 없는 탭과 절을 빈 칸이나 추정 문장으로
채우지 않는다. 각 프로젝트 폴더는 독립 프로젝트로 유지하며 이름이 비슷하거나
버전 이력이 이어져도 하나의 프로젝트 family로 병합하지 않는다. 앞선 이력은 필요한
경우 해당 프로젝트의 Decisions 본문에서만 맥락으로 설명한다.

각 프로젝트의 제목 없는 도입부는 `article.yaml`의 evidence-backed `orientation`을
사용한다. System Map은 `system-map.yaml`에 정의한 프로젝트별 실제 구성 요소와
데이터·사용자 흐름을 보여 준다. Decisions는 왜 그렇게 만들었는지, 어떤 대안을
검토했는지와 롤백·검증 근거를 설명하며, 맵은 그 본문을 반복하지 않고 필요한 결정만
링크한다. 프로젝트마다 필요한 노드 수와 흐름 형태는 근거에 따라 달라진다.

## 파일 구조

- `server.js`: Atlas 공개 API, 기존 CMS API, 정적 자산 서버
- `index.html`, `styles.css`, `client/`: 공개 Project Atlas UI
- `admin.html`, `admin.css`, `admin.js`: 보존된 기존 CMS
- `lib/atlas-store.js`: 검증된 bundle 로딩과 CMS allowlist 병합
- `lib/atlas-routes.js`: `/api/atlas/*` 공개 API
- `public-bundle/`: worker가 승격한 유일한 공개 프로젝트 데이터
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

3. Node 의존성 설치와 서버 실행

```bash
cd /home/dowon/securedir/git/codex/portfolio-homepage
npm install
node server.js
```

기본 포트는 `4173`이고 기본 바인딩은 `0.0.0.0`이다.

기본 Atlas bundle은 service root의 `public-bundle/`이다. 다른 검증된 bundle을 읽을
때만 절대 경로로 `ATLAS_BUNDLE_DIR`을 지정한다.

```bash
ATLAS_BUNDLE_DIR=/absolute/path/to/public-bundle PORT=4173 node server.js
```

검증된 bundle이 없으면 서버와 `/admin.html`은 계속 동작하고 Atlas API는 빈 상태를
명시적으로 반환한다. 로컬 경로나 원본 프로젝트 파일을 fallback으로 읽지 않는다.

## 검증

```bash
.venv/bin/python -m pytest tests/worker -q
npm test
npm run test:ui
npm run test:ui -- e2e/atlas-graph.spec.js
node --check server.js
node --check admin.js
```

## 기존 CMS 프리뷰 영상

프로젝트 ID 기준으로 아래 파일을 두면 카드 hover 시 자동 사용된다.

- `data/previews/{project-id}.mp4`
- `data/previews/{project-id}.webm`
- `data/posters/{project-id}.jpg|jpeg|png|webp`

파일이 없으면 CSS 모션 목업이 기본 프리뷰로 표시된다.

## 기존 CMS 운영 메모

- Google OAuth Origin은 실제 도메인 기준으로 등록해야 한다.
- `SESSION_SECRET`를 고정하지 않으면 서버 재시작 시 로그인 세션이 끊긴다.
- 개인 포트폴리오 트래픽 기준으로는 파일 저장소 구조로 충분하지만, 댓글량이 커지면 SQLite/Postgres로 옮기는 편이 안전하다.

## Project Atlas Worker

Worker는 로컬 workspace를 읽어 검토된 public profile과 직접 작성된 project memory만 `public-bundle/`로 만든다. 기본 출력은 key ordering이 고정된 JSON이며 absolute project root, raw session text, alias key, provenance를 출력하지 않는다.

### 설치

Python 3.10+ 환경이 필요하다. service root에서 전용 virtual environment와 Atlas 의존성을 설치한다.

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-atlas.txt
```

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

구현 화면을 공개할 프로젝트는 `project_memory/project-atlas/cover.png|jpg|jpeg|webp` 중
하나만 둘 수 있다. Worker가 이미지 형식, 크기, 공개 번들을 검증하고 프로젝트 상세에
대표 화면으로 연결한다. 비공개 정보가 보이는 캡처는 저장하지 않는다.

변경 감지와 공개 번들 갱신은 Windows 작업 스케줄러에 등록할 수 있다. WSL에서 아래를
실행하면 하루 1회의 `Dowon Project Atlas Sync` 작업을 설치하며, 실제 배포는 GitHub
`main` push를 통해 이어진다.

```bash
scripts/install_project_atlas_schedule.sh
scripts/install_project_atlas_schedule.sh --check
```

수동 실행이나 로그 확인은 아래를 사용한다.

```bash
scripts/project_atlas_scheduled_publish.sh
tail -35 .knowledge-worker/project-atlas-schedule.log
```

기존 33개 curated article의 문제 정의를 Orientation으로 승격하고 대응하는 System Map
source를 재생성할 때는 아래 migration을 사용한다. System Map은 기사 섹션을 순서대로
복사하지 않고 `scripts/project_system_map_specs.py`의 프로젝트별 구성 요소·흐름
사양을 사용한다. 이 명령은 정확히 33개를 요구하는 기존 카탈로그 migration이며 새
프로젝트 초기화 명령이 아니다.

```bash
.venv/bin/python scripts/backfill_project_atlas_content.py --workspace /home/dowon/securedir/git/codex --expected-count 33 --check
```

`discover`는 read-only다. `validate`도 bundle의 privacy, schema, hash, exact-tree contract만 읽어 검사하며 promotion을 호출하지 않는다. `backfill --dry-run`은 `--sessions-root`가 없고 `.knowledge-worker/config.yaml`에도 session root가 없으면 정상적인 zero-session 결과를 반환한다.

### Legacy LLM Wiki Graph Audit

기존 LLM Wiki CSV는 아래 audit-only importer로 검토한다. 이 명령은 six node/seven base
edge type을 정규화하고 name-derived relation, unknown project, missing endpoint, raw
locator를 거부한 deterministic JSON count와 taxonomy alias 제안만 stdout에 출력한다.
`nodes.csv`, `edges.csv`, reviewed taxonomy, `public-bundle/`을 수정하거나 migration
artifact를 생성하지 않으며 alias 제안을 자동 적용하지 않는다.

```bash
.venv/bin/python scripts/import_llm_wiki_graph.py \
  --source /home/dowon/securedir/git/codex/projects/llm_wiki \
  --taxonomy data/knowledge-taxonomy.yaml \
  --format json
```

### Reviewed Apply

Profile 생성은 자동 적용하지 않는다. 먼저 `bootstrap-profiles --dry-run`의 ambiguous ID를 검토하고, 아래 형식의 JSON을 별도로 작성한 뒤 적용한다. 각 profile은 현재 발견된 ambiguous ID와 정확히 일치하고 `project-profile` schema를 통과해야 한다.

Runtime config의 `registered_assets`에 등록된 단일 파일만 standalone project 후보가 된다. 등록되지 않은 파일과 sidecar는 자동 발견하지 않는다. 등록 파일의 reviewed profile은 같은 디렉터리의 `<asset-name>.project-profile.yaml` sidecar에 원자적으로 생성·갱신되며, 일반 디렉터리 project의 `project_memory/`로 취급하지 않는다.

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

`build`와 `run`의 non-dry 실행은 최소 32 bytes인 local alias-key material이 필요하다. 짧은 key는 config exit `2`로 거부된다. Key 값은 출력하거나 repository에 저장하지 않는다. Repository 밖의 사용자 전용 파일을 mode `600`으로 두는 방식을 권장한다.

```bash
install -d -m 700 "$HOME/.config/project-atlas"
umask 077
.venv/bin/python -c 'import secrets,sys; sys.stdout.buffer.write(secrets.token_bytes(32))' > "$HOME/.config/project-atlas/alias-hmac.key"
chmod 600 "$HOME/.config/project-atlas/alias-hmac.key"
export PROJECT_ATLAS_HMAC_KEY_PATH="$HOME/.config/project-atlas/alias-hmac.key"
.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex
```

`PROJECT_ATLAS_HMAC_KEY` 환경변수도 지원하지만 process environment에 남으므로 file 방식이 우선이다. `.knowledge-worker/config.yaml`의 `hmac_key_path`/`alias_key_file`은 절대 경로 또는 workspace 상대 경로를 받으며, key file 끝의 CR/LF만 제거한다. Runtime config의 `sessions_root`는 `backfill`과 `run`의 기본 session source다.

### 33개 공개 카탈로그 감사

공개 후보를 만들기 전에 정확한 33개 ID, 프로젝트별 readiness, 원본 근거 locator/hash, SVG 참조, 직접 관계와 Map Diary 소유 경계를 한 번에 검사한다. 프로젝트 수만 맞춘 대체 ID, Atlas가 스스로 만든 재서술 근거, generic decision 문서, 유사도 기반 project relation은 실패한다.

```bash
.venv/bin/python scripts/audit_public_atlas_catalog.py \
  --workspace /home/dowon/securedir/git/codex \
  --output /home/dowon/securedir/git/codex/.knowledge-worker/catalog-audit.json
```

성공 조건은 `project_count=33`, `ready=true`, 나머지 finding 배열이 모두 비어 있는 것이다. 출력은 프로젝트 ID와 비가역 finding code만 포함하며 source locator나 로컬 절대 경로를 노출하지 않는다.

### Dry Run과 Exit Code

`bootstrap-profiles`, `backfill`, `build`, `run`은 `--dry-run`을 지원한다. Dry-run은 profile, project memory, session cursor, manifest state, `public-bundle/`을 쓰지 않는다. Bundle 후보는 service directory와 same filesystem에 있는 자동 정리 temporary staging에서만 생성되고 promotion되지 않는다. 원자적 rename을 위해 staging과 `public-bundle/` parent의 device ID가 같아야 하며 아래처럼 확인할 수 있다.

```bash
stat -c '%d %n' . public-bundle 2>/dev/null || stat -c '%d %n' .
```

| Code | 의미 |
|---:|---|
| `0` | 성공 |
| `2` | argument, config, profile, schema, bundle validation 실패 |
| `3` | privacy gate 실패 |
| `4` | file 또는 directory I/O 실패 |

오류 stderr는 traceback이나 입력 원문 없이 category와 JSON pointer만 담은 JSON 한 줄이다.

### Promotion 복구

Promotion 복구 실패와 stale `.public-bundle.previous` 또는 `.public-bundle.recovery`는 경로를 노출하지 않는 `{"error":{"category":"io","pointer":"$"}}`와 exit `4`로 정규화된다. 이때 자동 재실행이나 즉시 삭제를 하지 말고 timer를 중지한 뒤 아래 순서로 검사한다.

```bash
cd /home/dowon/securedir/git/codex/portfolio-homepage
SERVICE="$PWD"
PUBLIC="$SERVICE/public-bundle"
PREVIOUS="$SERVICE/.public-bundle.previous"
RECOVERY="$SERVICE/.public-bundle.recovery"
find "$SERVICE" -maxdepth 1 \( -name 'public-bundle' -o -name '.public-bundle.previous' -o -name '.public-bundle.recovery' \) -printf '%y %f\n'
test ! -L "$PUBLIC" && test ! -L "$PREVIOUS" && test ! -L "$RECOVERY"
test ! -e "$PUBLIC" || .venv/bin/python scripts/project_atlas.py validate --fixture "$PUBLIC"
test ! -e "$PREVIOUS" || .venv/bin/python scripts/project_atlas.py validate --fixture "$PREVIOUS"
test ! -e "$RECOVERY" || .venv/bin/python scripts/project_atlas.py validate --fixture "$RECOVERY"
```

`public-bundle/`이 없고 `.public-bundle.previous` validation이 성공한 경우에만 adjacent atomic rename으로 last-good을 복원한다.

```bash
test ! -e "$PUBLIC"
.venv/bin/python scripts/project_atlas.py validate --fixture "$PREVIOUS"
mv -- "$PREVIOUS" "$PUBLIC"
.venv/bin/python scripts/project_atlas.py validate --fixture "$PUBLIC"
```

유효한 `public-bundle/`이 이미 있으면 previous/recovery를 덮어쓰거나 삭제하지 않는다. 둘을 각각 validation한 후 예약 이름 밖의 로컬 격리 디렉터리로 이동하고, 다음 dry-run과 build validation이 성공한 뒤 보존 정책에 따라 정리한다.

```bash
STAMP="$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$SERVICE/.atlas-inspected"
test ! -e "$PREVIOUS" || mv -- "$PREVIOUS" "$SERVICE/.atlas-inspected/previous-$STAMP"
test ! -e "$RECOVERY" || mv -- "$RECOVERY" "$SERVICE/.atlas-inspected/recovery-$STAMP"
.venv/bin/python scripts/project_atlas.py build --workspace /home/dowon/securedir/git/codex --dry-run
.venv/bin/python scripts/project_atlas.py validate --fixture "$PUBLIC"
```
