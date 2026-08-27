# Project Atlas Backfill Automation and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill all 33 public projects from local evidence, make meaningful future work update curated project memory, and publish only changed validated bundles through a locked local worker and Railway.

**Architecture:** Codex authors initial public-safe prose inside each independent project's `project_memory/project-atlas/` after reviewing private source/session audits. A user-level one-shot worker hashes those curated sources, assembles a complete candidate from changed inputs, validates it, promotes atomically, and stages only `public-bundle/`. Global AGENTS supplies the selective update checkpoint; the worker never generates prose with an unattended model.

**Tech Stack:** Python 3.10+, pytest, YAML/JSON, Git, user-level systemd, Node 20+, Playwright, GitHub, Railway CLI

**Spec:** `docs/superpowers/specs/2026-08-27-project-atlas-content-graph-redesign.md`

**Prerequisite:** Complete and verify the other three 2026-08-27 Project Atlas plans before enabling publication or editing the 33 project memories.

## Global Constraints

- Start after the content foundation, decision reader, and progressive 3D graph plans pass.
- All 33 public IDs require a source manifest and content audit; examples alone do not satisfy completion.
- Project directories and URLs remain independent; `projects/finish/` is never an aggregate project.
- Store selective durable decisions, difficult revisions, rollbacks, and verified outcomes, not routine turns or raw transcripts.
- No unattended external LLM, embedding, or vision API is allowed.
- Every project ends `ready` or `insufficient-evidence`; any `review-required` blocks release.
- Public output is fail-closed; private sessions, locators, paths, and reversible source values stay local.
- Automated Git staging is restricted to `public-bundle/`; a no-op run creates no commit or push.
- Archive `llm_wiki` only after production parity.

---

## Exact Backfill Batches

```text
Batch A: 260802-map-diary, 260802-map-diary-v2, 260802-map-diary-v3, 260329-tmap-clone
Batch B: 260212-feeling-traker, todack, 260619-chat-friends, 260621-easy-news,
         260725-household-account-book, 260401-wine-cellar-scan, 260408-ideal-type-editorial,
         260331-iphone-calculator-clone, 260410-keyboard-piano, 260418-japanese-word-study,
         260322-polite-message-extension, 260317-desktop-scheduler
Batch C: 251104-prompt-auto-evaluation, 260315-moe-prompt-routing, a2a-normal, a2a-test,
         a2a-lambda, gemini-multiturn-tester-v3, 260626-make-test-set, 260803-ai-office,
         260319-llm-tool-hub
Batch D: semantic-verb-schema, 260413-dictionary-transition-bundle, operation-log-analayzer,
         260218-ope-log-anlayze, 260324-central-memory-prompt-kit,
         260405-execution-harness-system, 260727-server-app-web-learn-book,
         260321-memento-mori-archive
```

Each project receives `project_memory/project-atlas/article.yaml`, `evidence.yaml`, optional `relations.yaml`, and only evidence-justified `visuals/*.svg`.

### Task 1: Global Meaningful-Work Checkpoint

**Files:**
- Modify after showing the exact diff and obtaining approval: `/home/dowon/.codex/AGENTS.md`
- Modify: `/home/dowon/securedir/git/codex/AGENTS.md`
- Modify: `/home/dowon/securedir/git/codex/central_memory/adapters/AGENTS.md`
- Create: `scripts/audit_atlas_memory_checkpoint.py`
- Create: `tests/worker/test_atlas_memory_checkpoint.py`

**Interfaces:**
- Consumes: the three instruction files and nearest `project_memory/project-profile.yaml`.
- Produces: `audit_checkpoint(global_path, workspace_path, adapter_path) -> tuple[Finding, ...]`.

- [ ] **Step 1: Write failing instruction tests**

```python
def test_missing_atlas_checkpoint_is_reported(tmp_path):
    files = agent_fixture(tmp_path, global_text="", workspace_text="", adapter_text="")
    assert "missing-project-atlas-checkpoint" in {item.code for item in audit_checkpoint(*files)}

def test_workspace_copy_is_reported(tmp_path):
    files = agent_fixture(tmp_path, VALID_GLOBAL_CHECKPOINT, VALID_GLOBAL_CHECKPOINT, VALID_ADAPTER)
    assert "duplicated-global-checkpoint" in {item.code for item in audit_checkpoint(*files)}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_atlas_memory_checkpoint.py -q`

Expected: FAIL because the auditor does not exist.

- [ ] **Step 3: Present and apply the exact global rule after approval**

```markdown
## Project Atlas Meaningful-Work Checkpoint

- After substantive work in a project with `project_memory/project-profile.yaml`, decide whether it established a durable product decision, difficult revision, rollback, architecture boundary, or verified outcome.
- When it did, merge the fact into `project_memory/project-atlas/article.yaml` and `evidence.yaml`; initialize that directory only when material evidence exists or the user explicitly asks.
- Keep projects independent. A predecessor or direct project relation requires explicit documentary, Git, session, or curated-memory evidence.
- Add an SVG only for a specific structure, state transition, or data lifetime that prose alone does not explain. Never create generic problem-decision-result diagrams.
- Exclude routine commands, raw transcripts, secrets, absolute paths, one-off discussion, and unsupported conclusions.
- Audit the changed project. Keep conflicting claims in local review state and do not overwrite validated public prose.
```

The workspace and adapter files point to this section without copying it. Do not create project `AGENTS.md` files for this behavior.

- [ ] **Step 4: Implement and verify the auditor**

Run the focused test, then run the auditor against the three live files. Expected: `0 findings`.

- [ ] **Step 5: Commit repository-owned tooling**

```bash
git add scripts/audit_atlas_memory_checkpoint.py tests/worker/test_atlas_memory_checkpoint.py
git commit -m "test: audit Atlas memory update routing"
```

### Task 2: Incremental Runtime State and Complete Candidates

**Files:**
- Create: `atlas_worker/runtime_state.py`
- Create: `tests/worker/test_runtime_state.py`
- Modify: `atlas_worker/cli.py`
- Modify: `atlas_worker/bundle.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: current and prior project source hashes, audit hashes, manifest, and HMAC key.
- Produces: `RuntimeState.open()`, `RuntimeState.lock()`, `changed_project_ids()`, atomic state writes, and `run --changed-only`.

- [ ] **Step 1: Write failing lock and last-good tests**

```python
def test_second_worker_cannot_take_lock(tmp_path):
    state = RuntimeState.open(tmp_path / "workspace", config_home=tmp_path / ".config")
    with state.lock():
        with pytest.raises(WorkerAlreadyRunning):
            with state.lock(blocking=False):
                pass

def test_failed_changed_project_preserves_manifest(tmp_path, complete_workspace):
    first = promote_worker(complete_workspace, tmp_path / "service")
    make_article_private(complete_workspace, "alpha")
    with pytest.raises(PrivacyViolation):
        promote_worker(complete_workspace, tmp_path / "service", changed_only=True)
    assert read_manifest(tmp_path / "service") == first.manifest
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_runtime_state.py tests/worker/test_cli.py -q`

Expected: FAIL importing `atlas_worker.runtime_state`.

- [ ] **Step 3: Implement exclusive locking and atomic state**

```python
@contextmanager
def lock(self, blocking=False):
    self.state_root.mkdir(parents=True, exist_ok=True)
    with (self.state_root / "worker.lock").open("a+b") as handle:
        mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle, mode)
        except BlockingIOError as error:
            raise WorkerAlreadyRunning("worker already running") from error
        yield
```

Write source hashes, cursor, audits, and last-good manifest through sibling temporary files, `fsync`, and `os.replace`. Require the key to be mode `0600` and at least 32 bytes.

- [ ] **Step 4: Implement changed-only assembly**

Recompute affected article/KG/search inputs, but always assemble and validate a complete candidate. Taxonomy, schema, or visibility changes invalidate every dependent projection. Run worker/CLI/bundle tests; expected PASS and an unchanged second run has no diff.

- [ ] **Step 5: Commit runtime state**

```bash
git add atlas_worker/runtime_state.py atlas_worker/cli.py atlas_worker/bundle.py tests/worker/test_runtime_state.py tests/worker/test_cli.py .gitignore
git commit -m "feat: assemble changed Atlas projects safely"
```

### Task 3: Backfill Batch A - Mobility

**Files:**
- Create or modify: `projects/260802_map_diary/project_memory/project-atlas/`
- Create or modify: `projects/260802_map_diary_v2/project_memory/project-atlas/`
- Create or modify: `projects/260802_map_diary_v3/project_memory/project-atlas/`
- Create or modify: `projects/260329_tmap_clone/project_memory/project-atlas/`

**Interfaces:**
- Consumes: docs/specs/plans/code/tests/Git, mapped sessions, and old wiki as secondary evidence.
- Produces: four independent article/evidence sets.

- [ ] **Step 1: Run `audit-content` for the four Batch A IDs**

Use `--private-audit-dir /home/dowon/securedir/git/codex/.knowledge-worker`. Expected: four private reports and no public write.

- [ ] **Step 2: Author every material product and technical decision**

V2 must explain the TMAP 24-hour limit, session-only TMAP input, permanent VWorld Feature ID/geometry snapshot, and TMAP source discard. V3 must explain Web/native lifetime separation and native SQLite. V4 worktree evidence belongs to V3 and explains reused line joining, VWorld/ITS validation, and user confirmation for unresolved gaps. Do not merge projects.

- [ ] **Step 3: Add only evidence-specific figures**

Create V2 `tmap-vworld-data-lifetime.svg`, V3 `web-native-recorder-boundary.svg`, and V3 `unresolved-gap-manual-confirmation.svg` only when evidence IDs resolve. Do not match counts across projects.

- [ ] **Step 4: Re-audit and dry-build**

Run the four audits and `build --dry-run`. Expected: only `ready` or `insufficient-evidence`, with zero title, evidence, privacy, merge, and family findings.

- [ ] **Step 5: Commit each repository independently**

Stage only `project_memory/project-atlas/` and commit `docs: curate Atlas project decisions`. Do not initialize Git for non-Git paths or include unrelated changes.

### Task 4: Backfill Batch B - Consumer Products

**Files:**
- Create or modify: the 12 Batch B `project_memory/project-atlas/` directories from the exact batch list.

**Interfaces:**
- Consumes: project-local evidence and mapped correction/rollback sessions.
- Produces: 12 independent decision-first articles.

- [ ] **Step 1: Run private audits for all 12 Batch B IDs**

Expected: 12 reports and no aggregate `finish` project.

- [ ] **Step 2: Author planning and UX decisions first**

Explain why scope or interaction changed, rejected alternatives, accepted behavior, validation, and remaining limits. Use plain headings such as `입력 흐름 단순화`, `편집 상태 복구`, and `배포 환경 분리`; reject dramatic wording.

- [ ] **Step 3: Add diagrams only for real state/persistence/rollback boundaries**

Place each figure after its paragraph and cite evidence. Projects without such evidence receive no SVG.

- [ ] **Step 4: Audit all 12 and dry-build**

Expected: zero generic three-bullet article, missing evidence, unreferenced SVG, private path, and `review-required` status.

- [ ] **Step 5: Commit independently**

Stage only each project's Atlas memory and use `docs: curate Atlas project decisions`.

### Task 5: Backfill Batch C - Agents and Evaluation

**Files:**
- Create or modify: the nine Batch C `project_memory/project-atlas/` directories from the exact batch list.

**Interfaces:**
- Consumes: specs, prompt versions, fixed evaluations, benchmark reports, code, Git, and mapped sessions.
- Produces: nine independent articles with numerically honest validation.

- [ ] **Step 1: Run private audits for all nine Batch C IDs**

Expected: child sessions are evidence under their parent project, never projects.

- [ ] **Step 2: Explain targets, routing boundaries, data rules, prompt tradeoffs, ownership, and failure modes before code**

State benchmark sizes and scores only with local artifacts; plans and commit messages alone are not completion evidence.

- [ ] **Step 3: Preserve failed strategies without inflating decision counts**

Explain each meaningful failed condition and next boundary; group repeated discussion of one decision.

- [ ] **Step 4: Audit all nine and dry-build**

Expected: every numeric claim resolves to evidence and below-target results remain explicit limitations.

- [ ] **Step 5: Commit independently**

Stage only Atlas memory and preserve unrelated prompt/benchmark work.

### Task 6: Backfill Batch D - Data, Memory, and Operations

**Files:**
- Create or modify: the eight Batch D `project_memory/project-atlas/` directories from the exact batch list.

**Interfaces:**
- Consumes: schemas, memory boundaries, operations evidence, legacy harness docs, code, Git, and sessions.
- Produces: eight independent articles and optional curated relations.

- [ ] **Step 1: Run private audits for all eight Batch D IDs**

Expected: harness Markdown remains evidence only and activates no execution loop.

- [ ] **Step 2: Explain intended versus actual wiring**

For memory/harness projects, distinguish intent, actual behavior, failed automation, legacy status, and replacement. For data/operations projects, distinguish schema, extraction/quality choices, outputs, and handoff limits.

- [ ] **Step 3: Add direct relations only with direct evidence**

Allow only `EVOLVED_FROM`, `VALIDATES`, `DEPLOYS`, and `REUSES_COMPONENT`. Similar names and shared themes are insufficient.

- [ ] **Step 4: Audit all eight and dry-build**

Expected: only `ready` or `insufficient-evidence`; no legacy file, raw session, or local path enters the candidate.

- [ ] **Step 5: Commit independently**

Stage only Atlas memory. Do not revive, delete, or execute legacy harness code.

### Task 7: Exact 33-Project Catalog Gate

**Files:**
- Create: `scripts/audit_public_atlas_catalog.py`
- Create: `tests/worker/test_public_catalog_audit.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: discovery, 33 audits, curated sources, and dry-run candidate.
- Produces: `audit_public_catalog(...) -> CatalogAudit`.

- [ ] **Step 1: Write a failing exact-set test**

```python
def test_catalog_requires_all_33_projects(catalog):
    assert len(catalog.project_ids) == 33
    assert "finish" not in catalog.project_ids
    assert catalog.review_required == ()
    assert catalog.generic_decision_documents == ()
    assert catalog.similarity_edges == ()
```

The fixture set must list every ID in the four batch lists, not merely assert a count.

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_public_catalog_audit.py -q`

Expected: FAIL importing the auditor.

- [ ] **Step 3: Implement exact checks**

Require one manifest/audit per ID, valid readiness, no generic article, no missing/duplicate evidence/section/diagram IDs, no unreferenced SVG, no title lint, no inferred project relation, correct Map Diary ownership, and honest session stats.

- [ ] **Step 4: Run the live catalog audit and dry-build**

Run: `.venv/bin/python scripts/audit_public_atlas_catalog.py --workspace /home/dowon/securedir/git/codex --output /home/dowon/securedir/git/codex/.knowledge-worker/catalog-audit.json`

Expected: `33 projects`, `0 review-required`, `0 generic`, `0 inferred relations`.

- [ ] **Step 5: Commit the gate**

```bash
git add scripts/audit_public_atlas_catalog.py tests/worker/test_public_catalog_audit.py README.md
git commit -m "test: require complete Atlas public catalog"
```

### Task 8: Allowlisted Publisher and Timer

**Files:**
- Create: `atlas_worker/publish.py`
- Create: `tests/worker/test_publish.py`
- Modify: `atlas_worker/cli.py`
- Create: `deploy/systemd-user/project-atlas.service`
- Create: `deploy/systemd-user/project-atlas.timer`
- Create: `scripts/install_project_atlas_timer.sh`
- Modify: `deploy/DEPLOY.md`

**Interfaces:**
- Consumes: successful promotion, Git state, and user systemd.
- Produces: `publish_bundle(...) -> PublishResult`, `publish` CLI, and a 15-minute timer.

- [ ] **Step 1: Write failing staging tests**

```python
def test_publisher_stages_only_public_bundle(tmp_path):
    repo = init_repo(tmp_path)
    write(repo / "public-bundle/manifest.json", '{"version":"v2"}')
    write(repo / "server.js", "unrelated")
    result = publish_bundle(repo, PromotionResult(True, ("alpha",)), push=False)
    assert result.staged_paths == ("public-bundle/manifest.json",)
    assert "server.js" in git(repo, "status", "--short")
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_publish.py -q`

Expected: FAIL importing publisher.

- [ ] **Step 3: Implement exact-path publication**

```python
runner.run(repo, "add", "--", "public-bundle")
staged = tuple(runner.lines(repo, "diff", "--cached", "--name-only"))
if any(path != "public-bundle" and not path.startswith("public-bundle/") for path in staged):
    raise PublishError("non-bundle staged path")
```

Defer when pre-existing staged work exists. A no-op returns without commit. `publish` runs lock, catalog audit, tests, candidate validation, promotion, then publication; it never uses broad `git add`.

- [ ] **Step 4: Add exact user units**

The service runs `.venv/bin/python scripts/project_atlas.py publish --workspace /home/dowon/securedir/git/codex --changed-only --push` from `/home/dowon/securedir/git/codex/portfolio-homepage`. The timer uses `OnBootSec=5m`, `OnUnitActiveSec=15m`, `RandomizedDelaySec=60`, and `Persistent=true`. The installer supports `--check`, install, and `--remove` for only these two units.

Run publisher tests and `bash scripts/install_project_atlas_timer.sh --check`; expected PASS.

- [ ] **Step 5: Commit publisher and timer**

```bash
git add atlas_worker/publish.py atlas_worker/cli.py tests/worker/test_publish.py deploy/systemd-user/project-atlas.service deploy/systemd-user/project-atlas.timer scripts/install_project_atlas_timer.sh deploy/DEPLOY.md
git commit -m "feat: publish Atlas updates on a locked timer"
```

### Task 9: Integration, Railway, and Legacy Archival

**Files:**
- Modify: `/home/dowon/securedir/git/codex/.knowledge-worker/config.yaml`
- Modify: `/home/dowon/securedir/git/codex/central_memory/project_agent_inventory.md`
- Modify on real status change: `/home/dowon/securedir/git/codex/central_memory/active_projects.md`
- Move after parity: `/home/dowon/securedir/git/codex/projects/llm_wiki` to `/home/dowon/securedir/git/codex/projects/legacy/llm_wiki`

**Interfaces:**
- Consumes: completed branch, validated bundle, GitHub origin, Railway link.
- Produces: integrated `main`, production Atlas, active timer, archived wiki source.

- [ ] **Step 1: Run the full local gate one heavy process at a time**

Run worker pytest, `npm test`, `npm run test:ui`, both Node syntax checks, build dry-run, and public-bundle validation. Expected: all exit `0`.

- [ ] **Step 2: Integrate with `superpowers:finishing-a-development-branch`**

Fetch origin, inspect ancestry/divergence, use the user-selected merge or PR path, and rerun the full gate before push. Do not rewrite unrelated history.

- [ ] **Step 3: Point runtime config at `service_root: portfolio-homepage`**

Keep `sessions_root: /home/dowon/.codex/sessions`, the existing HMAC path, and aliases file. Run publish without push, validate canonical bundle, then push only when staged paths are bundle-only.

- [ ] **Step 4: Verify Railway and install the timer**

Run `railway status`, `railway logs`, `railway domain`, install the timer, and inspect `systemctl --user status`. Verify health, bootstrap, projects, Map Diary V2 deep link, and Graph against the returned domain; production and local manifest versions must match.

- [ ] **Step 5: Archive LLM Wiki only after parity**

Require 33 URLs, search, six KG node types, relation filters, 3D controls, fallback, dark mode, responsive checks, and zero runtime dependency on `projects/llm_wiki`. Move it to `projects/legacy/llm_wiki`, update project inventory, update active status only if changed, and rerun discovery/catalog audit. Expected: still 33 public projects and no bundle diff.

## Completion Gate

- [ ] One approved global checkpoint exists without project copies.
- [ ] All 33 projects have manifests and final readiness statuses.
- [ ] Catalog audit has zero review, generic, missing-evidence, inferred-relation, and privacy findings.
- [ ] No-op runs do not commit; failures preserve last-good.
- [ ] Timer is active, 15-minute, and non-overlapping.
- [ ] Railway matches local manifest.
- [ ] LLM Wiki is archived only after parity and remains as legacy source.
