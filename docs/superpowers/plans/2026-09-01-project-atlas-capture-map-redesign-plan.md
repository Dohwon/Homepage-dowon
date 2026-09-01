# Project Atlas 캡처 및 의미형 System Map 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실제 구현 화면을 프로젝트별로 검토·공개하고, 캡처를 `Decisions` 하단에 배치하며, 프로젝트별 의사결정 관계를 드러내는 비정형 System Map으로 Project Atlas를 갱신한다.

**Architecture:** 프로젝트 원본의 `project_memory/project-atlas/`를 공개 자료의 정본으로 둔다. 캡처는 명시적 목록만 privacy gate를 통과해 public bundle로 복사하고, System Map은 프로젝트별 `map_type`과 가변 노드·관계 데이터를 사용한다. 일일 publisher는 프로젝트 폴더를 탐색해 변경된 bundle을 검증한 뒤 Railway 배포 저장소에 반영한다.

**Tech Stack:** Python 3, PyYAML, JSON Schema, Node.js, vanilla JavaScript, SVG, pytest, npm test, Railway CLI

**Spec:** `docs/superpowers/specs/2026-09-01-project-atlas-capture-map-redesign-design.md`

## Global Constraints

- `captures.yaml`에 등록된 파일만 공개 번들로 복사한다.
- 경로는 프로젝트 루트 밖으로 나갈 수 없고 symlink를 허용하지 않는다.
- 기존 `cover.png`는 당장 깨지지 않게 읽되, 새 등록은 `captures.yaml`을 정본으로 사용한다.
- 캡처는 프로젝트 `Decisions` 탭의 의사결정 글 뒤에만 표시한다.
- 실제 화면이 없거나 공개 검토되지 않은 프로젝트는 캡처 없이 공개할 수 있다.
- System Map은 프로젝트별 관계를 표현하며 노드 수와 단계 수를 고정하지 않는다.
- 기존 `data/blog-posts.json`, `data/site-content.json`의 사용자 변경 내용을 덮어쓰거나 커밋하지 않는다.
- 공개 profile과 article이 없는 새 프로젝트는 발견 로그에만 남기고 자동 공개하지 않는다.

### Task 1: 캡처 데이터 계약과 worker 로더 확장

**Files:**
- Create: `schemas/project-captures.schema.json`
- Create: `schemas/public-captures.schema.json`
- Create: `atlas_worker/captures.py`
- Modify: `atlas_worker/models.py`
- Modify: `atlas_worker/bundle.py`
- Modify: `atlas_worker/cli.py`
- Modify: `schemas/public-project.schema.json`
- Modify: `schemas/project-profile.schema.json`
- Test: `tests/worker/test_captures.py`
- Test: `tests/worker/test_bundle.py`

**Interfaces:**
- `load_project_captures(ref: ProjectRef, gate: PrivacyGate) -> tuple[ProjectCapture, ...]`
- `ProjectCapture.to_public_dict() -> dict[str, str]`
- `BundleContext.project_captures: Mapping[str, tuple[ProjectCapture, ...]]`

- [ ] **Step 1: Write failing tests for explicit capture lists.**

```python
def test_load_project_captures_only_reads_registered_files(tmp_path):
    ref = make_project(tmp_path, "todack")
    atlas = ref.root / "project_memory/project-atlas"
    (atlas / "captures").mkdir(parents=True)
    (atlas / "captures/home.png").write_bytes(PNG_BYTES)
    (atlas / "unregistered.png").write_bytes(PNG_BYTES)
    (atlas / "captures.yaml").write_text(
        "captures:\n  - id: home\n    path: captures/home.png\n    alt: Todack 홈 화면\n    caption: 감정 기록 홈\n    role: overview\n",
        encoding="utf-8",
    )
    captures = load_project_captures(ref, PrivacyGate(alias_key=b"test"))
    assert [item.capture_id for item in captures] == ["home"]
    assert captures[0].content == PNG_BYTES
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `.venv/bin/python -m pytest tests/worker/test_captures.py -q`
Expected: FAIL because the capture schema, loader, and model do not exist.

- [ ] **Step 3: Implement the capture model, schema validation, confined image loading, and bundle serialization.**

The loader will read only `project_memory/project-atlas/captures.yaml`, reject duplicate IDs, missing files, symlinks, unsupported MIME signatures, files larger than the existing 2 MiB image limit, and paths outside the project root. It will retain the existing `cover.png` fallback as a single legacy capture when `captures.yaml` is absent.

- [ ] **Step 4: Run focused worker tests and bundle regression tests.**

Run: `.venv/bin/python -m pytest tests/worker/test_captures.py tests/worker/test_bundle.py -q`
Expected: PASS, including existing single-cover behavior and new multi-capture metadata.

- [ ] **Step 5: Commit the capture contract.**

```bash
git add schemas atlas_worker tests/worker/test_captures.py tests/worker/test_bundle.py
git commit -m "feat: add reviewed project capture manifest"
```

### Task 2: 캡처 UI를 Decisions 하단으로 이동

**Files:**
- Modify: `client/render.js`
- Modify: `styles.css`
- Modify: `server.js`
- Create: `test/client/render.test.js`
- Test: `test/server/atlas-api.test.js`

**Interfaces:**
- `renderProjectCaptures(captures) -> string`
- `renderProject(project, state) -> string`
- `GET /api/atlas/projects/:id/captures/:captureId`

- [ ] **Step 1: Add a failing render test.**

```javascript
test("renders captures after decisions content and not in the project header", () => {
  const html = renderProject(makeProjectWithCaptures(), { route: { tab: "decisions" } });
  assert.equal(html.indexOf("project-captures") > html.indexOf("project-article"), true);
  assert.equal(html.includes('class="project-header"'), true);
  assert.equal(html.slice(0, html.indexOf("project-tabs")).includes("project-cover"), false);
});
```

- [ ] **Step 2: Run the focused Node tests and verify the new assertion fails.**

Run: `node --test tests/client/render.test.js`
Expected: FAIL because captures are currently rendered as a header cover.

- [ ] **Step 3: Move capture rendering into the Decisions tab.**

Render the article body first, then a `구현 화면` section only when the active tab is `decisions` and the project has captures. Keep the existing `cover` API as a compatibility route, add capture-specific routes, escape all metadata, and omit the section entirely when no capture exists.

- [ ] **Step 4: Add responsive gallery styling and route tests.**

Use stable image sizing, captions, keyboard-accessible links, and no layout shift. Verify that Overview, System Map, Evidence, and Build Timeline do not contain the capture section.

- [ ] **Step 5: Run Node tests and commit.**

Run: `npm test`

```bash
git add client server.js tests
git commit -m "feat: place project captures below decisions"
```

### Task 3: 실제 화면 보유 프로젝트 전수 조사와 캡처 등록

**Files:**
- Create or modify in each applicable project repository: `/home/dowon/securedir/git/codex/projects/*/project_memory/project-atlas/captures.yaml`
- Create or modify in each applicable project repository: `/home/dowon/securedir/git/codex/projects/*/project_memory/project-atlas/captures/*`
- Modify: `scripts/audit_project_captures.py`
- Create: `scripts/register_reviewed_project_captures.py`
- Test: `tests/worker/test_capture_audit.py`
- Output: `.knowledge-worker/project-atlas-capture-audit.json`

**Interfaces:**
- `audit_project_captures(workspace: Path) -> CaptureAudit`
- `register_reviewed_capture(project_id: str, source: Path, capture_id: str, ...) -> Path`

- [ ] **Step 1: Extend the audit to classify implementation screens, deployed web apps, references, assets, and no-screen projects.**

The audit will inspect every discovered project, `runtime-sync` deployment references, existing `cover.png`, known screenshot filenames, runnable web entrypoints, and project-specific public assets. It will explicitly report `reviewed`, `needs-review`, `reference-only`, and `no-screen` rather than treating every PNG as a capture.

- [ ] **Step 2: Run the audit and review all candidates, prioritizing Railway-deployed projects.**

Run:

```bash
.venv/bin/python scripts/audit_project_captures.py \
  --workspace /home/dowon/securedir/git/codex \
  --output /home/dowon/securedir/git/codex/.knowledge-worker/project-atlas-capture-audit.json
```

Review every project that has a Railway deployment or a runnable web/app surface. Use the Railway project list and the project's own deployment notes as the deployment source of truth. Do not publish logos, splash screens, design references, test failure captures, private records, API keys, or images with unmasked personal data.

- [ ] **Step 3: Register each reviewed implementation screen in the project memory.**

Copy only the selected image into `project_memory/project-atlas/captures/`, write its `captures.yaml` entry with a meaningful role and caption, and migrate an existing reviewed `cover.png` as the first capture when that file exists. Projects without a real screen receive an explicit `no-screen` audit status and no empty image placeholder.

- [ ] **Step 4: Build and inspect the public bundle.**

Run: `.venv/bin/python scripts/project_atlas.py build --workspace /home/dowon/securedir/git/codex`

Expected: all approved capture files are represented in the candidate bundle, with no source project path, private text, or unregistered image included.

- [ ] **Step 5: Run privacy and capture audit tests, then commit project memory assets separately from unrelated data changes.**

Run: `.venv/bin/python -m pytest tests/worker/test_capture_audit.py tests/worker/test_captures.py -q`

Commit the service audit changes in `portfolio-homepage` and commit each project's capture metadata and image in that project's own Git repository. Do not add project files to the service repository and do not stage unrelated user changes.

### Task 4: 프로젝트별 의미형 System Map 데이터 재작성

**Files:**
- Modify: `scripts/project_system_map_specs.py`
- Modify: `schemas/project-system-map.schema.json`
- Modify: `schemas/public-system-map.schema.json`
- Modify: `atlas_worker/system_map.py`
- Create or modify: `/home/dowon/securedir/git/codex/projects/*/project_memory/project-atlas/system-map.yaml`
- Test: `tests/worker/test_system_map.py`
- Test: `tests/worker/test_project_content_backfill.py`

**Interfaces:**
- `ProjectSystemMap.map_type: str`
- `SystemMapFlow.label: str`
- `render_system_map_svg(system_map: ProjectSystemMap) -> str`

- [ ] **Step 1: Add failing tests that reject generic repeated flows.**

```python
def test_map_specs_use_project_specific_relation_types():
    maps = load_all_fixture_maps()
    assert maps["260802-map-diary-v2"].map_type == "version-roadmap"
    assert maps["a2a-normal"].map_type == "agent-orchestration"
    assert maps["260401-wine-cellar-scan"].map_type == "state-transition"
    assert any(flow.label in {"왜 변경했나", "버림", "복구", "승인"} for flow in maps["260802-map-diary-v2"].flows)
```

- [ ] **Step 2: Run the focused map tests and verify the current fixtures fail.**

Run: `.venv/bin/python -m pytest tests/worker/test_system_map.py tests/worker/test_project_content_backfill.py -q`
Expected: FAIL for map types and relation labels that do not yet exist.

- [ ] **Step 3: Replace the repeated input-process-output specs with semantic map families.**

Use variable node counts and meaningful relations. Map data must reflect actual project decisions: version transitions for Map Diary, state and recovery for Todack, route ownership and fallback for A2A, dataset-run-judge feedback for evaluation tools, and client-server-storage boundaries for deployed services. Keep Decisions as the detailed narrative and use the map to expose relationships between decisions.

- [ ] **Step 4: Update SVG rendering to reflect map family without forcing one geometry.**

Use family-specific layout hints: a horizontal version path for roadmaps, state circles and recovery loops for state transitions, swimlanes for service boundaries, and feedback arcs for evaluation loops. Preserve accessible title/description metadata, stable ordering, and safe text escaping.

- [ ] **Step 5: Regenerate all 33 project maps and validate.**

Run:

```bash
python3 scripts/project_system_map_specs.py
.venv/bin/python scripts/project_atlas.py validate --fixture public-bundle
```

Expected: every public project has a valid map whose type and relations are supported by its article and evidence.

- [ ] **Step 6: Run map tests and commit the semantic map data.**

Run: `.venv/bin/python -m pytest tests/worker/test_system_map.py tests/worker/test_project_content_backfill.py -q`

Commit the service generator and schema changes in `portfolio-homepage`. Commit each regenerated `system-map.yaml` in its owning project repository when that repository tracks the memory directory. Keep generated `public-bundle/` changes in the service repository.

### Task 5: 동기화·발견 로그와 공개 번들 회귀 보강

**Files:**
- Modify: `atlas_worker/source_manifest.py`
- Modify: `atlas_worker/discovery.py`
- Modify: `scripts/project_atlas_scheduled_publish.py`
- Modify: `scripts/project_atlas_scheduled_publish.sh`
- Modify: `README.md`
- Modify: `deploy/DEPLOY.md`
- Test: `tests/worker/test_source_manifest.py`
- Test: `tests/worker/test_cli.py`

**Interfaces:**
- `build_source_manifest(project, runner) -> SourceManifest`
- scheduled JSON fields `discovery`, `build`, and `publication`

- [ ] **Step 1: Add failing tests for capture and new-folder detection.**

```python
def test_changed_only_detects_project_memory_capture_addition(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    invoke_cli_json(["run", "--workspace", str(workspace), "--changed-only"])
    capture = workspace / "projects/alpha/project_memory/project-atlas/captures.yaml"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text("captures: []\n", encoding="utf-8")
    output = invoke_cli_json(["run", "--workspace", str(workspace), "--changed-only"])
    assert output["affected_projects"] == ["alpha"]
```

- [ ] **Step 2: Run the focused sync tests and verify the new assertion fails if the path is not included.**

Run: `.venv/bin/python -m pytest tests/worker/test_source_manifest.py tests/worker/test_cli.py -q`
Expected: FAIL only if the capture path is not part of the manifest.

- [ ] **Step 3: Keep project memory and approved capture changes in the manifest while documenting intentionally skipped dependency/generated directories.**

Ensure both new direct project folders and changes under `project_memory/project-atlas/` appear in the affected list. Preserve fail-closed behavior for ambiguous projects and do not publish an unprofiled folder.

- [ ] **Step 4: Run the complete scheduled publisher once locally.**

Run:

```bash
/home/dowon/securedir/git/codex/portfolio-homepage/scripts/project_atlas_scheduled_publish.sh
```

Expected: discovery includes all direct project folders, the build validates, and only changed public bundle files are staged/pushed.

- [ ] **Step 5: Run worker tests, Node tests, syntax checks, and commit.**

```bash
.venv/bin/python -m pytest tests/worker -q
npm test
node --check server.js
node --check client/render.js
git diff --check
git add atlas_worker scripts README.md deploy tests
git commit -m "test: verify atlas capture and folder synchronization"
```

### Task 6: Railway 재배포와 공개 검증

**Files:**
- Modify: `deploy/DEPLOY.md`
- Do not modify: `data/blog-posts.json`, `data/site-content.json`

**Interfaces:**
- `GET /`
- `GET /api/health`
- `GET /api/atlas/bootstrap`
- `GET /api/atlas/projects/:id/captures/:captureId`

- [ ] **Step 1: Confirm the local bundle and service before deploy.**

```bash
.venv/bin/python scripts/project_atlas.py validate --fixture public-bundle
npm test
```

- [ ] **Step 2: Deploy from the linked Railway `Project Atlas` project.**

```bash
railway status
railway up
railway domain
```

The GitHub repository remains `Homepage-dowon`; Railway project identity is `Project Atlas`.

- [ ] **Step 3: Verify the public deployment.**

```bash
curl -sS -f https://project-atlas-production-7818.up.railway.app/api/health
curl -sS -f https://project-atlas-production-7818.up.railway.app/api/atlas/bootstrap
curl -sS -f https://project-atlas-production-7818.up.railway.app/api/atlas/projects/todack/captures/home
```

Expected: HTML and JSON return `200`, bootstrap contains the regenerated version, and an approved capture returns its image content type.

- [ ] **Step 4: Record the public URL, deployed version, project count, capture count, and any missing-screen projects in the final handoff.**

### Task 7: 최종 UI·콘텐츠 QA

**Files:**
- Test only: `tests/worker`, existing Node/UI tests, and temporary QA scripts under `/tmp`

- [ ] **Step 1: Open the public site at desktop and mobile widths.**

Verify the capture is absent from Overview and present below Decisions, the image does not push the tab rail unexpectedly, and projects with no capture have no empty frame.

- [ ] **Step 2: Inspect representative map families.**

Check Map Diary version roadmap, Todack state/recovery map, an A2A orchestration map, an evaluation loop, and a deployed service-boundary map. Confirm labels explain relationships rather than merely listing stages.

- [ ] **Step 3: Verify interaction and accessibility.**

Test tab navigation, capture keyboard focus, image alt text, SVG title/description, graph navigation, mobile overflow, and dark mode.

- [ ] **Step 4: Run final verification.**

```bash
.venv/bin/python -m pytest tests/worker -q
npm test
node --check server.js
node --check client/render.js
git diff --check
git status --short --branch
```

- [ ] **Step 5: Push only the implementation commits and preserve unrelated user changes.**

```bash
git push origin main
```
