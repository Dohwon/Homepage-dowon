# Project Atlas Knowledge Content Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic list-based project memories with evidence-linked project articles, decision episodes, source manifests, and auditable project/session ownership without merging independent projects.

**Architecture:** Each project owns a curated `project_memory/project-atlas/` source directory. The worker builds a private source/session audit from local evidence, validates the curated article against that audit, and projects only public-safe article data into the Atlas bundle. Session ownership is resolved from changed paths, Git common directories, current working directories, and parent-child session links; unresolved evidence stays unmapped.

**Tech Stack:** Python 3.10+, dataclasses, PyYAML, JSON Schema Draft 2020-12, pytest 8.x, Git CLI, existing Atlas privacy and atomic bundle modules

**Spec:** `docs/superpowers/specs/2026-08-27-project-atlas-content-graph-redesign.md`

## Global Constraints

- Every discovered folder under `projects/`, including each child of `projects/finish/`, remains an independent project ID and URL.
- Similar names, version suffixes, and shared Git remotes never merge projects or create predecessor links.
- A worktree contributes evidence to its owning repository unless a reviewed profile declares an independent project.
- Public prose is curated by Codex from local evidence; the unattended worker never calls an external LLM, embedding, or vision API.
- Raw sessions, absolute paths, private provenance, and reversible encrypted source values never enter `public-bundle/`.
- Article section, decision, option, rollback, and diagram counts have no fixed minimum or maximum.
- Missing evidence produces `insufficient-evidence`; it never produces generic filler.
- Titles are plain Korean descriptions such as `TMAP 데이터 장기 저장 제한 해결`, not dramatic narrative headlines.
- Existing `public-bundle/` remains last-good when schema, evidence, privacy, or filesystem validation fails.

---

## Planned File Structure

```text
atlas_worker/
├── models.py                 # immutable content, evidence, audit, and graph records
├── source_manifest.py        # project files, Git roots, and worktree ownership
├── session_index.py          # session/thread/tool-call index and project mapping
├── decision_episodes.py      # bounded private decision windows and evidence IDs
├── article.py                # curated article loading, title lint, SVG reference checks
├── content_audit.py          # readiness and coverage reports
├── memory.py                 # load project-atlas curated sources
├── bundle.py                 # public article/timeline/evidence projection
└── cli.py                    # `audit-content` and migrated build flow
schemas/
├── project-article.schema.json
├── public-article.schema.json
├── public-timeline.schema.json
└── public-evidence.schema.json
tests/worker/
├── test_source_manifest.py
├── test_session_index.py
├── test_decision_episodes.py
├── test_article.py
├── test_content_audit.py
└── test_bundle.py
tests/fixtures/project-content/
├── map-diary-v2/
└── insufficient/
```

The canonical project-owned source layout is:

```text
project_memory/project-atlas/
├── article.yaml
├── evidence.yaml
├── relations.yaml            # optional, curated only
├── system-map.svg            # optional whole-system boundary and data flow
└── visuals/
    └── <stable-figure-id>.svg
```

Generated private state is stored only under workspace-local `.knowledge-worker/`:

```text
.knowledge-worker/
├── source-manifests/<project-id>.json
├── session-index.json
├── content-audits/<project-id>.json
└── review-queue/<project-id>.json
```

### Task 1: Structured Article, Evidence, and Audit Models

**Files:**
- Modify: `atlas_worker/models.py`
- Create: `schemas/project-article.schema.json`
- Create: `schemas/public-article.schema.json`
- Create: `schemas/public-timeline.schema.json`
- Create: `schemas/public-evidence.schema.json`
- Modify: `tests/worker/test_models.py`

**Interfaces:**
- Consumes: existing `ProjectRef`, `ProjectEvent`, and `validate_schema(instance, schema_name)`.
- Produces: `EvidenceRecord`, `DiagramRef`, `ArticleSection`, `DecisionIndexEntry`, `ProjectArticle`, `ContentAudit`, and their `to_public_dict()` methods.

- [ ] **Step 1: Write failing model and schema tests**

```python
def test_project_article_omits_absent_optional_sections_from_public_projection():
    article = ProjectArticle(
        project_id="alpha",
        title="라우팅 실패 분류 개선",
        summary="운영 로그에서 실패 유형을 재현 가능하게 분류했다.",
        sections=(ArticleSection(
            section_id="failure-taxonomy",
            title="실패 유형 분리",
            section_type="planning",
            body="같은 실패처럼 보이던 사례를 입력, 라우팅, 실행 단계로 나눴다.",
            evidence_ids=("ev-spec",),
        ),),
        readiness="ready",
    )

    payload = article.to_public_dict()

    assert payload["sections"][0]["id"] == "failure-taxonomy"
    assert "prior_context" not in payload
    assert "diagrams" not in payload["sections"][0]
    validate_schema(payload, "public-article")


def test_public_article_schema_rejects_private_evidence_locator():
    payload = {
        "project_id": "alpha",
        "title": "라우팅 개선",
        "summary": "검증된 요약",
        "readiness": "ready",
        "sections": [{
            "id": "routing",
            "title": "라우팅 개선",
            "section_type": "decision",
            "body": "본문",
            "evidence_ids": ["ev-1"],
            "source_locator": "/home/dowon/private",
        }],
    }
    with pytest.raises(ValueError, match="source_locator"):
        validate_schema(payload, "public-article")
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_models.py -q`

Expected: FAIL because `ProjectArticle` and `public-article` do not exist.

- [ ] **Step 3: Add immutable records and exact literal types**

```python
ArticleSectionType = Literal["planning", "decision", "implementation", "validation", "result"]
DecisionStatus = Literal["adopted", "revised", "rolled-back", "unresolved"]
EvidenceSourceType = Literal["session", "spec", "code", "test", "git", "project_memory"]
EvidencePrivacy = Literal["public-safe", "private", "secret"]
Readiness = Literal["ready", "insufficient-evidence", "review-required"]

@dataclass(frozen=True)
class DiagramRef:
    diagram_id: str
    source_path: str
    caption: str
    alt: str
    svg: str = field(repr=False, compare=False)

@dataclass(frozen=True)
class ArticleSection:
    section_id: str
    title: str
    section_type: ArticleSectionType
    body: str
    evidence_ids: tuple[str, ...]
    diagrams: tuple[DiagramRef, ...] = ()

@dataclass(frozen=True)
class DecisionIndexEntry:
    decision_id: str
    section_id: str
    status: DecisionStatus
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True)
class ProjectArticle:
    project_id: str
    title: str
    summary: str
    sections: tuple[ArticleSection, ...]
    readiness: Readiness
    prior_context: str = ""
    decision_index: tuple[DecisionIndexEntry, ...] = ()

    def to_public_dict(self) -> dict[str, object]:
        payload = {
            "project_id": self.project_id,
            "title": self.title,
            "summary": self.summary,
            "readiness": self.readiness,
            "sections": [_public_section(section) for section in self.sections],
        }
        if self.prior_context:
            payload["prior_context"] = self.prior_context
        if self.decision_index:
            payload["decision_index"] = [asdict(item) for item in self.decision_index]
        return payload

def _public_section(section: ArticleSection) -> dict[str, object]:
    payload = {
        "id": section.section_id,
        "title": section.title,
        "section_type": section.section_type,
        "body": section.body,
        "evidence_ids": list(section.evidence_ids),
    }
    if section.diagrams:
        payload["diagrams"] = [
            {"id": item.diagram_id, "caption": item.caption, "alt": item.alt}
            for item in section.diagrams
        ]
    return payload
```

Define `EvidenceRecord` with private `source_locator`, `content_hash`, and `privacy_class`; its public projection includes only `id`, `label`, `source_type`, `observed_at`, and an optional allowlisted `url`. Define `ContentAudit` with `project_id`, `readiness`, `evidence_counts`, `session_stats`, `missing_evidence_ids`, `unmapped_session_ids`, and `findings`.

- [ ] **Step 4: Add strict schemas and run the model tests**

The public schemas use `additionalProperties: false` at every object level. `public-article` permits no locator, session ID, filesystem path, provenance, or raw text field. `project-article` validates the curated YAML shape and requires stable IDs matching `^[a-z0-9][a-z0-9-]*$`.

Run: `.venv/bin/python -m pytest tests/worker/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the content contract**

```bash
git add atlas_worker/models.py schemas/project-article.schema.json schemas/public-article.schema.json schemas/public-timeline.schema.json schemas/public-evidence.schema.json tests/worker/test_models.py
git commit -m "feat: define Atlas article evidence contracts"
```

### Task 2: Project Source Manifests and Worktree Ownership

**Files:**
- Create: `atlas_worker/source_manifest.py`
- Create: `tests/worker/test_source_manifest.py`
- Modify: `atlas_worker/cli.py`

**Interfaces:**
- Consumes: `ProjectRef` records and a `GitRunner.run(cwd, *args) -> str` protocol.
- Produces: `build_source_manifest(project, runner) -> SourceManifest`, `resolve_git_owner(path, projects, runner) -> str | None`, and CLI `audit-content --workspace ... --project <id>`.

- [ ] **Step 1: Write failing independent-project and worktree tests**

```python
def test_finish_is_a_container_and_children_remain_independent(tmp_path):
    refs = (
        project_ref(tmp_path / "projects/finish/alpha", "alpha"),
        project_ref(tmp_path / "projects/finish/beta", "beta"),
    )
    manifests = tuple(build_source_manifest(ref, FakeGitRunner()) for ref in refs)
    assert [item.project_id for item in manifests] == ["alpha", "beta"]
    assert all(item.project_id != "finish" for item in manifests)


def test_worktree_is_evidence_for_git_common_dir_owner(tmp_path):
    owner = project_ref(tmp_path / "projects/map-v3", "map-v3")
    worktree = tmp_path / "projects/map-v3/.worktrees/v4"
    runner = FakeGitRunner(common_dirs={owner.root: "/git/map", worktree: "/git/map"})
    assert resolve_git_owner(worktree, (owner,), runner) == "map-v3"


def test_similar_version_names_do_not_create_predecessor():
    manifest = build_source_manifest(project_ref(Path("/workspace/map-v2"), "map-v2"), FakeGitRunner())
    assert manifest.predecessor_ids == ()
```

- [ ] **Step 2: Run the source-manifest tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_source_manifest.py -q`

Expected: FAIL importing `atlas_worker.source_manifest`.

- [ ] **Step 3: Implement deterministic source classification**

```python
SOURCE_PATTERNS = (
    ("spec", ("docs/superpowers/specs/**/*.md", "docs/specs/**/*.md")),
    ("plan", ("docs/superpowers/plans/**/*.md", "docs/plans/**/*.md")),
    ("test", ("tests/**/*", "test/**/*", "e2e/**/*")),
    ("project_memory", ("project_memory/**/*.md", "project_memory/**/*.yaml")),
    ("manager_memory", ("manager_memory/**/*.md",)),
    ("source", ("src/**/*", "app/**/*", "lib/**/*", "*.py", "*.js", "*.ts")),
)

def resolve_git_owner(path: Path, projects: Sequence[ProjectRef], runner: GitRunner) -> str | None:
    candidate = runner.git_common_dir(path)
    if not candidate:
        return None
    owners = {
        project.project_id
        for project in projects
        if runner.git_common_dir(project.root) == candidate
    }
    return next(iter(owners)) if len(owners) == 1 else None
```

`build_source_manifest` stores relative paths, content hashes, source class, and owning project ID. It records Git `HEAD` and common-dir fingerprints as private audit values, not public article fields. Predecessors are loaded only from reviewed `article.yaml.prior_context.project_id` or `relations.yaml`; filename similarity is never consulted.

- [ ] **Step 4: Add CLI JSON output and run tests**

Run: `.venv/bin/python -m pytest tests/worker/test_source_manifest.py tests/worker/test_discovery.py tests/worker/test_cli.py -q`

Expected: PASS. `audit-content --project alpha --format json` emits counts and hashes but no absolute path.

- [ ] **Step 5: Commit source ownership**

```bash
git add atlas_worker/source_manifest.py atlas_worker/cli.py tests/worker/test_source_manifest.py tests/worker/test_cli.py
git commit -m "feat: audit Atlas project evidence ownership"
```

### Task 3: Session Index and Parent-Child Mapping

**Files:**
- Create: `atlas_worker/session_index.py`
- Modify: `atlas_worker/sessions.py`
- Modify: `atlas_worker/models.py`
- Create: `tests/worker/test_session_index.py`
- Modify: `tests/worker/test_sessions.py`

**Interfaces:**
- Consumes: JSONL paths, `ProjectRef` records, explicit aliases, and Git ownership from Task 2.
- Produces: `index_session(path) -> SessionTrace`, `map_session_trace(trace, projects, aliases, git_owner) -> SessionMapping`, and `merge_child_evidence(traces, mappings) -> tuple[SessionMapping, ...]`.

- [ ] **Step 1: Write failing mapping-priority and child-session tests**

```python
def test_changed_file_path_outranks_parent_cwd(tmp_path):
    trace = SessionTrace(
        session_id="child",
        parent_session_id="parent",
        cwd="/workspace/projects/alpha",
        changed_paths=("/workspace/projects/beta/src/app.js",),
        git_common_dirs=(),
        events=(),
    )
    mapping = map_session_trace(trace, project_refs(tmp_path), {}, FakeGitOwner())
    assert mapping.project_id == "beta"
    assert mapping.reason == "changed-path"


def test_child_without_direct_evidence_inherits_parent_project():
    mappings = merge_child_evidence(
        traces=(trace("parent"), trace("child", parent="parent")),
        mappings=(mapped("parent", "alpha", "cwd"), unmapped("child")),
    )
    assert mappings[1].project_id == "alpha"
    assert mappings[1].reason == "parent-session"


def test_conflicting_direct_child_evidence_is_not_overridden_by_parent():
    mappings = merge_child_evidence(
        traces=(trace("parent"), trace("child", parent="parent")),
        mappings=(mapped("parent", "alpha", "cwd"), mapped("child", "beta", "changed-path")),
    )
    assert mappings[1].project_id == "beta"
```

- [ ] **Step 2: Run the session-index tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_session_index.py tests/worker/test_sessions.py -q`

Expected: FAIL because trace-level mapping is absent.

- [ ] **Step 3: Parse session metadata, tool calls, and changed paths without publishing text**

```python
@dataclass(frozen=True)
class SessionTrace:
    session_id: str
    parent_session_id: str
    cwd: str
    changed_paths: tuple[str, ...]
    git_common_dirs: tuple[str, ...]
    events: tuple[SessionEvent, ...]

@dataclass(frozen=True)
class SessionMapping:
    session_id: str
    project_id: str | None
    reason: Literal["changed-path", "git-common-dir", "cwd", "alias", "parent-session", "ambiguous", "unmapped"]
    child_session_ids: tuple[str, ...] = ()
```

`index_session` recognizes `session_meta`, `turn_context`, message `response_item`, and function/tool-call records. It extracts paths only from structured `cwd`, `workdir`, `path`, and patch target fields; it does not scan prose for arbitrary path-like strings. Mapping priority is `changed-path > git-common-dir > cwd > alias > parent-session`. Equal-strength conflicts return `ambiguous`.

- [ ] **Step 4: Replace event-by-event CLI mapping with trace mapping**

Update `_scan_sessions` to index each JSONL once, map the trace once, then feed its events to the owning project's private extractor. Add counters for `parent_sessions`, `child_sessions`, `mapped_by_reason`, and `ambiguous_sessions`; keep session IDs out of sanitized CLI output unless `--private-audit-dir` points inside `.knowledge-worker/`.

Run: `.venv/bin/python -m pytest tests/worker/test_session_index.py tests/worker/test_sessions.py tests/worker/test_cli.py -q`

Expected: PASS, including old cwd and Windows alias cases.

- [ ] **Step 5: Commit trace-level session mapping**

```bash
git add atlas_worker/session_index.py atlas_worker/sessions.py atlas_worker/models.py atlas_worker/cli.py tests/worker/test_session_index.py tests/worker/test_sessions.py tests/worker/test_cli.py
git commit -m "feat: map Atlas sessions by repository evidence"
```

### Task 4: Private Decision Episodes and Evidence Audit

**Files:**
- Create: `atlas_worker/decision_episodes.py`
- Create: `atlas_worker/content_audit.py`
- Modify: `atlas_worker/backfill.py`
- Create: `tests/worker/test_decision_episodes.py`
- Create: `tests/worker/test_content_audit.py`
- Modify: `tests/worker/test_backfill.py`

**Interfaces:**
- Consumes: mapped `SessionTrace`, source manifests, curated evidence YAML, and article evidence IDs.
- Produces: `extract_decision_episodes(trace, project_id) -> tuple[DecisionEpisode, ...]`, `audit_project_content(...) -> ContentAudit`, and private review queue records.

- [ ] **Step 1: Write failing episode-boundary and no-filler tests**

```python
def test_revision_loop_is_one_episode_with_multiple_turns():
    trace = trace_with_messages(
        user("왼쪽 목차가 따라오지 않아"),
        assistant("sticky offset을 수정하겠습니다"),
        user("헤더와 겹쳐. 다시 수정해"),
        assistant("회귀 테스트까지 통과했습니다"),
    )
    episodes = extract_decision_episodes(trace, "atlas")
    assert len(episodes) == 1
    assert episodes[0].status == "supported"
    assert len(episodes[0].evidence_ids) == 4


def test_no_decision_language_creates_no_episode():
    trace = trace_with_messages(user("파일 목록 보여줘"), assistant("목록입니다"))
    assert extract_decision_episodes(trace, "alpha") == ()


def test_missing_evidence_yields_insufficient_status_without_generic_sections():
    audit = audit_project_content(project("alpha"), manifest(), article=None, evidence=(), mappings=())
    assert audit.readiness == "insufficient-evidence"
    assert "generic-section" not in audit.findings
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_decision_episodes.py tests/worker/test_content_audit.py -q`

Expected: FAIL importing both new modules.

- [ ] **Step 3: Implement bounded, private episode extraction**

```python
OPEN_CUES = re.compile(r"문제|제약|왜|대안|바꿔|수정|롤백|결정|선택|채택|실패|겹쳐|안 돼", re.I)
CLOSE_CUES = re.compile(r"검증|통과|완료|반영|확인|보류|미해결", re.I)
MAX_EPISODE_EVENTS = 24

def extract_decision_episodes(trace: SessionTrace, project_id: str) -> tuple[DecisionEpisode, ...]:
    episodes = []
    window = []
    for event in trace.events:
        if event.role == "user" and OPEN_CUES.search(event.text) and not window:
            window = [event]
            continue
        if window:
            window.append(event)
            if CLOSE_CUES.search(event.text) or len(window) == MAX_EPISODE_EVENTS:
                episodes.append(_episode(project_id, trace.session_id, window))
                window = []
    if window:
        episodes.append(_episode(project_id, trace.session_id, window, status="candidate"))
    return tuple(episodes)
```

The private episode stores bounded excerpts and locators under `.knowledge-worker/review-queue/`. Its public representation is forbidden. Existing generic claim values such as `rollback requested` may remain compatibility input for old memory migration but must not become article prose.

- [ ] **Step 4: Implement readiness and evidence-reference audit**

`audit_project_content` returns:

- `ready` only when every article `evidence_id` resolves, all referenced SVGs validate, title lint passes, and no contradictory evidence is unresolved.
- `review-required` when article claims conflict, parent-child mapping is ambiguous, or references are missing.
- `insufficient-evidence` when no curated article exists or only factual metadata is supportable.

Run: `.venv/bin/python -m pytest tests/worker/test_decision_episodes.py tests/worker/test_content_audit.py tests/worker/test_backfill.py -q`

Expected: PASS. No test asserts a fixed number of sections or decisions.

- [ ] **Step 5: Commit private decision audits**

```bash
git add atlas_worker/decision_episodes.py atlas_worker/content_audit.py atlas_worker/backfill.py tests/worker/test_decision_episodes.py tests/worker/test_content_audit.py tests/worker/test_backfill.py
git commit -m "feat: audit evidence-backed Atlas decisions"
```

### Task 5: Curated Project Article Loader and Title Lint

**Files:**
- Create: `atlas_worker/article.py`
- Modify: `atlas_worker/memory.py`
- Modify: `atlas_worker/visuals.py`
- Create: `tests/worker/test_article.py`
- Modify: `tests/worker/test_memory.py`
- Modify: `tests/worker/test_visuals.py`

**Interfaces:**
- Consumes: `project_memory/project-atlas/article.yaml`, `evidence.yaml`, optional `system-map.svg`, and `visuals/*.svg` inside a project boundary.
- Produces: `load_project_article(ref, gate) -> ProjectArticle | None`, `load_project_evidence(ref, gate) -> tuple[EvidenceRecord, ...]`, `load_system_map(ref, gate) -> str | None`, `lint_article_title(title) -> tuple[str, ...]`, and `validate_article_diagrams(...)`.

- [ ] **Step 1: Write failing article loader, title, and SVG tests**

```python
def test_article_loader_preserves_long_markdown_and_section_order(project_tree):
    write_article(project_tree, {
        "project_id": "map-v2",
        "title": "경로 주행 기록 개선",
        "summary": "주행 경로를 영구 도로 기록으로 변환했다.",
        "readiness": "ready",
        "sections": [
            {"id": "retention", "title": "TMAP 데이터 장기 저장 제한 해결", "section_type": "decision",
             "body": "TMAP 경로는 세션 입력으로만 사용한다.\n\nVWorld Feature ID와 geometry snapshot을 영구 저장한다.",
             "evidence_ids": ["ev-tmap-spec"],
             "diagrams": [{
                 "id": "tmap-vworld-lifecycle",
                 "caption": "TMAP 입력과 VWorld 영구 기록의 데이터 수명",
                 "alt": "TMAP 경로는 세션에서만 사용되고 VWorld Feature와 geometry snapshot은 영구 저장되는 흐름",
             }]},
        ],
    })
    article = load_project_article(project_tree.ref, gate())
    assert article.sections[0].body.count("\n\n") == 1
    assert article.sections[0].diagrams[0].diagram_id == "tmap-vworld-lifecycle"


@pytest.mark.parametrize("title", (
    "웹 앱이 멈추는 순간, 기록도 함께 멈췄다",
    "드디어 완벽한 경로 기록을 만들었다",
))
def test_title_lint_rejects_dramatic_or_unverified_copy(title):
    assert lint_article_title(title)


def test_svg_must_have_viewbox_title_desc_and_no_external_resource(project_tree):
    write_svg(project_tree, "bad", '<svg><image href="https://example.com/x.png"/></svg>')
    with pytest.raises(ValueError, match="article-svg"):
        load_project_article(project_tree.ref, gate())


def test_system_map_is_optional_and_uses_the_same_svg_gate(project_tree):
    assert load_system_map(project_tree.ref, gate()) is None
    write_system_map(project_tree, SAFE_SYSTEM_MAP_SVG)
    assert load_system_map(project_tree.ref, gate()) == SAFE_SYSTEM_MAP_SVG
```

- [ ] **Step 2: Run loader tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_article.py tests/worker/test_memory.py tests/worker/test_visuals.py -q`

Expected: FAIL because structured article loading is absent.

- [ ] **Step 3: Implement confined loading and neutral-title rules**

```python
DRAMATIC_TITLE_RULES = (
    re.compile(r"순간.*함께", re.I),
    re.compile(r"드디어|마침내|완벽한|혁신적|압도적", re.I),
    re.compile(r"[!?]{2,}"),
)

def lint_article_title(title: str) -> tuple[str, ...]:
    value = title.strip()
    findings = [rule.pattern for rule in DRAMATIC_TITLE_RULES if rule.search(value)]
    if len(value) > 60:
        findings.append("title-too-long")
    return tuple(findings)
```

Load files through `read_confined_text`; populate internal `DiagramRef.source_path` and `DiagramRef.svg`, then omit both fields from `to_public_dict()`. Apply the same SVG validator to optional `system-map.svg`. Reject symlinks, traversal, duplicate section/decision/diagram IDs, missing evidence IDs, SVG scripts, event handlers, `foreignObject`, external hrefs, and absent `viewBox`, `<title>`, or `<desc>`. Do not generate generic SVGs from `ProjectEvent`; retain `render_problem_solving_svg` only for legacy bundle validation until Task 6 removes it.

- [ ] **Step 4: Run all article and memory tests**

Run: `.venv/bin/python -m pytest tests/worker/test_article.py tests/worker/test_memory.py tests/worker/test_visuals.py tests/worker/test_privacy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit curated article loading**

```bash
git add atlas_worker/article.py atlas_worker/memory.py atlas_worker/visuals.py tests/worker/test_article.py tests/worker/test_memory.py tests/worker/test_visuals.py
git commit -m "feat: load curated Atlas project articles"
```

### Task 6: Public Bundle Article Migration

**Files:**
- Modify: `atlas_worker/bundle.py`
- Modify: `atlas_worker/cli.py`
- Modify: `lib/atlas-store.js`
- Modify: `schemas/public-manifest.schema.json`
- Modify: `tests/worker/test_bundle.py`
- Modify: `tests/worker/test_cli.py`
- Modify: `test/server/atlas-store.test.js`
- Modify: `test/fixtures/public-bundle/`

**Interfaces:**
- Consumes: validated `ProjectArticle`, public evidence projections, `ProjectEvent` timeline, and optional system-map/inline SVG files.
- Produces: bundle files `article.json`, `timeline.json`, `evidence.json`, `system-map.svg`, and `visuals/<id>.svg`; server project payload fields `article`, `timeline`, `evidence`, `systemMap`, and `visuals`.

- [ ] **Step 1: Write failing exact-tree and server-load tests**

```python
def test_bundle_writes_structured_article_and_only_referenced_figures(bundle_context, tmp_path):
    manifest = build_candidate_bundle(bundle_context, tmp_path / "candidate")
    project_dir = tmp_path / "candidate/projects/alpha"
    article = json.loads((project_dir / "article.json").read_text())
    assert article["sections"][0]["id"] == "routing"
    assert (project_dir / "visuals/routing-flow.svg").is_file()
    assert not (project_dir / "decisions.md").exists()
    assert not (project_dir / "visuals/problem-solving.svg").exists()
    assert "projects/alpha/article.json" in manifest.files
```

```javascript
test("loads structured public project content", async () => {
  const project = await createStore().project("alpha");
  assert.equal(project.article.sections[0].id, "routing");
  assert.equal(project.timeline[0].event_id, "alpha-1");
  assert.match(project.visuals["routing-flow"], /<svg/);
  assert.equal(project.buildStory, undefined);
  assert.equal(project.decisions, undefined);
  assert.equal(project.visualMap, undefined);
});
```

- [ ] **Step 2: Run bundle and store tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py tests/worker/test_cli.py -q`

Run: `node --test test/server/atlas-store.test.js`

Expected: FAIL because the old optional Markdown file contract is still active.

- [ ] **Step 3: Replace the old optional-file allowlist**

```python
_OPTIONAL_PROJECT_FILES = (
    "article.json",
    "timeline.json",
    "evidence.json",
    "system-map.svg",
)

def _write_project_content(project_dir, article, evidence, timeline, gate):
    if article is None:
        return
    _write_json(project_dir / "article.json", article.to_public_dict(), gate)
    for diagram in referenced_diagrams(article):
        _write_text(project_dir / "visuals" / f"{diagram.diagram_id}.svg", diagram.svg, gate)
    if evidence:
        _write_json(project_dir / "evidence.json", [item.to_public_dict() for item in evidence], gate)
    if timeline:
        _write_json(project_dir / "timeline.json", [event_to_public(item) for item in timeline], gate)
```

Update exact-tree validation so unreferenced SVGs, legacy `decisions.md`, `build-story.md`, `rollbacks.md`, and generic `problem-solving.svg` are rejected in newly built candidates. The validator may still read a last-good old bundle during a one-release migration only if manifest `format_version` is `1`; all new bundles use `format_version: 2`.

- [ ] **Step 4: Expand search indexing and verify privacy**

Create one search record per article section with URL `/projects/<id>?tab=decisions#<section-id>`. Index public section body and neutral title only. Validate every JSON and SVG through `PrivacyGate` before hashing.

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py tests/worker/test_cli.py tests/worker/test_privacy.py -q`

Run: `node --test test/server/atlas-store.test.js test/server/atlas-api.test.js`

Expected: PASS; malformed or private article fields preserve the prior manifest.

- [ ] **Step 5: Commit the bundle migration**

```bash
git add atlas_worker/bundle.py atlas_worker/cli.py lib/atlas-store.js schemas/public-manifest.schema.json tests/worker/test_bundle.py tests/worker/test_cli.py test/server/atlas-store.test.js test/fixtures/public-bundle
git commit -m "feat: publish structured Atlas project articles"
```

### Task 7: Map Diary and Project-Boundary Acceptance Fixtures

**Files:**
- Create: `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/article.yaml`
- Create: `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/evidence.yaml`
- Create: `tests/fixtures/project-content/map-diary-v2/project_memory/project-atlas/visuals/tmap-vworld-lifecycle.svg`
- Create: `tests/fixtures/project-content/insufficient/project_memory/project-profile.yaml`
- Create: `tests/worker/test_content_acceptance.py`
- Modify: `tests/worker/helpers.py`

**Interfaces:**
- Consumes: every public content interface from Tasks 1-6.
- Produces: regression fixtures for the verified Map Diary V2 decision and evidence-poor projects.

- [ ] **Step 1: Add the failing Map Diary acceptance test**

```python
def test_map_diary_v2_article_preserves_verified_data_lifecycle_decision(map_diary_v2_ref):
    article = load_project_article(map_diary_v2_ref, gate())
    body = "\n".join(section.body for section in article.sections)
    assert "24시간" in body
    assert "세션 입력" in body
    assert "VWorld Feature ID" in body
    assert "geometry snapshot" in body
    assert "TMAP 원본 경로" in body
    assert article.project_id == "260802-map-diary-v2"


def test_worktree_v4_evidence_does_not_create_an_independent_project(projects):
    ids = {project.project_id for project in projects}
    assert "260802-map-diary-v4" not in ids
    assert "260802-map-diary-v3" in ids


def test_insufficient_project_has_no_manufactured_decisions(insufficient_ref):
    audit = audit_ref(insufficient_ref)
    assert audit.readiness == "insufficient-evidence"
    assert load_project_article(insufficient_ref, gate()) is None
```

- [ ] **Step 2: Run the acceptance test and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_content_acceptance.py -q`

Expected: FAIL until the fixture article, evidence, and SVG are present.

- [ ] **Step 3: Add exact fixture content**

The V2 article contains a decision section titled `TMAP 데이터 장기 저장 제한 해결`. It states that TMAP route data is session input only, VWorld Feature ID and geometry snapshot are the durable record, and the TMAP source route is discarded after permanent conversion. The SVG shows two explicitly labeled lifetimes and contains no generic `문제 -> 결정 -> 결과` nodes.

Use evidence IDs `v2-tmap-retention-spec`, `v2-vworld-feature-spec`, and `v2-source-discard-spec`, each pointing privately to the verified V2 design spec fixture. The public projection exposes labels only.

- [ ] **Step 4: Run the full worker foundation suite**

Run: `.venv/bin/python -m pytest tests/worker -q`

Expected: PASS. The generated candidate contains no legacy generic Decisions or problem-solving SVG files.

- [ ] **Step 5: Commit acceptance fixtures**

```bash
git add tests/fixtures/project-content tests/worker/test_content_acceptance.py tests/worker/helpers.py
git commit -m "test: lock Atlas decision content boundaries"
```

## Completion Gate

- [ ] Run `.venv/bin/python -m pytest tests/worker -q` and confirm zero failures.
- [ ] Run `node --test test/server/atlas-store.test.js test/server/atlas-api.test.js` and confirm zero failures.
- [ ] Run `.venv/bin/python scripts/project_atlas.py audit-content --workspace /home/dowon/securedir/git/codex --format json` and confirm every public project has exactly one private audit status.
- [ ] Confirm `project-similarity` remains only an old graph implementation concern; this plan does not create new inferred project relationships.
- [ ] Confirm `git status --short` contains only intended commits plus the pre-existing untracked `.superpowers/brainstorm/` directory.
