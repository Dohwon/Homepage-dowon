# Project Atlas Automation and Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Project Atlas update selectively across independent project repositories, publish only validated public-bundle changes, deploy through GitHub and Railway, and retire the old generated wiki after parity verification.

**Architecture:** The always-on global `~/.codex/AGENTS.md` supplies the memory checkpoint and Superpowers preflight even when Codex starts inside a child Git repository. A locked user-level systemd job runs the local worker every 15 minutes, keeps state and the HMAC key outside Git, stages only `public-bundle/`, and pushes a commit only when validated public content changed.

**Tech Stack:** Python 3.10+, pytest 8.x, Linux/WSL user systemd, Git, GitHub, Railway CLI, Codex AGENTS instructions, YAML/JSON state

**Spec:** `docs/superpowers/specs/2026-08-24-project-atlas-design.md`

**Prerequisite:** Complete the local-pipeline and public-experience plans and pass both completion gates before Task 1.

## Global Constraints

- `~/.codex/AGENTS.md` is the single user-wide source for memory routing and meaningful-work checkpoints.
- `/home/dowon/securedir/git/codex/AGENTS.md` contains workspace-only deltas and does not duplicate global policy.
- Project-level `AGENTS.md` files remain local deltas and are not generated merely because work starts.
- Stable owner traits update `/home/dowon/securedir/git/codex/dowon_manager_agent_brief.md`; project-only facts do not.
- Project-specific decisions, difficult revisions, and rollbacks update that project's `project_memory/` selectively.
- The worker never hand-edits `~/.codex/memories/`.
- The timer runs every 15 minutes and on login, with one worker process at a time.
- The HMAC key is local, mode `0600`, outside every Git repository, and never appears in logs or public output.
- Automated Git staging is restricted to `public-bundle/`.
- Privacy, schema, unit, or build failure prevents commit and push.
- A no-op run creates no commit.
- `projects/llm_wiki` moves to legacy only after content, graph, search, responsive, and production parity checks pass.

---

## Planned File Structure

```text
portfolio-homepage/
├── atlas_worker/
│   ├── runtime_state.py            # lock, cursor, aliases, secret path
│   └── publish.py                  # allowlisted validate/commit/push flow
├── deploy/
│   ├── knowledge-worker/config.example.yaml
│   └── systemd-user/
│       ├── project-atlas.service
│       └── project-atlas.timer
├── scripts/
│   ├── audit_agent_memory_rules.py
│   └── install_project_atlas_timer.sh
├── tests/worker/
│   ├── test_runtime_state.py
│   ├── test_publish.py
│   └── test_agent_memory_rules.py
├── tests/fixtures/privacy/local-path.json
└── deploy/DEPLOY.md

/home/dowon/securedir/git/codex/
├── AGENTS.md                        # workspace deltas
├── dowon_manager_agent_brief.md     # curated stable owner profile
├── central_memory/adapters/AGENTS.md
├── central_memory/active_projects.md
├── central_memory/project_agent_inventory.md
└── .knowledge-worker/               # local runtime, not published
    ├── config.yaml
    ├── project-aliases.yaml
    ├── session-cursor.json
    ├── provenance/
    ├── review-queue/
    └── last-good-manifest.json

/home/dowon/.config/project-atlas/
├── env                              # optional non-secret runtime settings
└── hmac.key                         # 32-byte local secret, mode 0600

/home/dowon/.codex/AGENTS.md         # always-on global rules
```

### Task 1: Local Runtime State, Lock, and Secret Handling

**Files:**
- Create: `atlas_worker/runtime_state.py`
- Create: `deploy/knowledge-worker/config.example.yaml`
- Create: `tests/worker/test_runtime_state.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: workspace root and optional `PROJECT_ATLAS_HMAC_KEY_PATH`.
- Produces: `RuntimeState.open(workspace_root)`, `RuntimeState.lock()`, `load_aliases()`, `load_cursor()`, `save_cursor()`, and `load_hmac_key()`.

- [ ] **Step 1: Write failing permission, atomic-cursor, and exclusive-lock tests**

```python
def test_hmac_key_is_created_outside_repo_with_owner_only_permissions(tmp_path):
    state = RuntimeState.open(tmp_path / "workspace", config_home=tmp_path / ".config")
    key = state.load_hmac_key()
    assert len(key) == 32
    assert stat.S_IMODE(state.hmac_key_path.stat().st_mode) == 0o600
    assert not str(state.hmac_key_path).startswith(str(state.workspace_root))

def test_second_worker_cannot_take_lock(tmp_path):
    state = RuntimeState.open(tmp_path / "workspace", config_home=tmp_path / ".config")
    with state.lock():
        with pytest.raises(WorkerAlreadyRunning, match="already running"):
            with state.lock(blocking=False):
                pass
```

The test module imports `pytest` and `stat` before these tests.

- [ ] **Step 2: Run state tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_runtime_state.py -v`

Expected: FAIL importing `atlas_worker.runtime_state`.

- [ ] **Step 3: Implement local state directories, `fcntl` locking, and atomic JSON writes**

```python
class RuntimeState:
    @classmethod
    def open(cls, workspace_root, config_home=None):
        workspace_root = Path(workspace_root).resolve()
        state_root = workspace_root / ".knowledge-worker"
        secret_root = Path(config_home or Path.home() / ".config") / "project-atlas"
        return cls(workspace_root, state_root, secret_root / "hmac.key")

    def load_hmac_key(self):
        self.hmac_key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.hmac_key_path.exists():
            descriptor = os.open(self.hmac_key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(secrets.token_bytes(32))
        mode = stat.S_IMODE(self.hmac_key_path.stat().st_mode)
        if mode != 0o600:
            raise ConfigError(f"HMAC key permissions must be 0600, got {mode:04o}")
        return self.hmac_key_path.read_bytes()
```

Use `fcntl.flock(..., LOCK_EX | LOCK_NB)` on `.knowledge-worker/worker.lock`. Write cursor and last-good manifest through a sibling temporary file, `fsync`, then `os.replace`.

- [ ] **Step 4: Run runtime-state tests and inspect ignore rules**

Run: `.venv/bin/python -m pytest tests/worker/test_runtime_state.py -v`

Run: `git check-ignore -v .atlas-staging .public-bundle.previous`

Expected: tests PASS and transient staging/backup directories are ignored; `public-bundle/` itself is not ignored.

- [ ] **Step 5: Commit runtime state support**

```bash
git add atlas_worker/runtime_state.py deploy/knowledge-worker/config.example.yaml tests/worker/test_runtime_state.py .gitignore
git commit -m "feat: secure atlas worker runtime state"
```

### Task 2: Allowlisted Git Publisher

**Files:**
- Create: `atlas_worker/publish.py`
- Create: `tests/worker/test_publish.py`
- Create: `tests/worker/git_helpers.py`
- Modify: `atlas_worker/cli.py`

**Interfaces:**
- Consumes: a successful `PromotionResult`, the service repository, and a `GitRunner` abstraction.
- Produces: `publish_bundle(repo, promotion, push=False) -> PublishResult` and CLI command `publish --workspace ... [--push]`.

`PublishResult` has `committed: bool`, `pushed: bool`, `staged_paths: tuple[str, ...]`, and `deferred: bool = False`.

`tests/worker/git_helpers.py` exports `init_repo(root) -> Path`, `write(path, text) -> None`, and `git(repo, *args) -> str`. `init_repo` configures a local test identity and creates one baseline commit so staged restore and HEAD assertions are valid.

- [ ] **Step 1: Write failing no-op, allowlist, dirty-tree, and failed-gate tests**

```python
def test_publisher_stages_only_public_bundle(tmp_path):
    repo = init_repo(tmp_path)
    write(repo / "public-bundle/manifest.json", '{"version":"v2"}')
    write(repo / "server.js", "unrelated user edit")
    result = publish_bundle(repo, PromotionResult(changed=True, changed_projects=("alpha",)), push=False)
    assert result.staged_paths == ("public-bundle/manifest.json",)
    assert "server.js" in git(repo, "status", "--short")

def test_noop_promotion_creates_no_commit(tmp_path):
    repo = init_repo(tmp_path)
    before = git(repo, "rev-parse", "HEAD")
    result = publish_bundle(repo, PromotionResult(changed=False, changed_projects=()), push=False)
    assert not result.committed
    assert git(repo, "rev-parse", "HEAD") == before

def test_preexisting_staged_work_defers_without_touching_index(tmp_path):
    repo = init_repo(tmp_path)
    write(repo / "server.js", "staged user edit")
    git(repo, "add", "server.js")
    before = git(repo, "diff", "--cached", "--name-only")
    result = publish_bundle(repo, PromotionResult(changed=True, changed_projects=("alpha",)), push=False)
    assert result.deferred
    assert git(repo, "diff", "--cached", "--name-only") == before
```

- [ ] **Step 2: Run publisher tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_publish.py -v`

Expected: FAIL importing `atlas_worker.publish`.

- [ ] **Step 3: Implement explicit path validation and deterministic commit messages**

```python
PUBLISH_ROOT = "public-bundle"

def publish_bundle(repo, promotion, push=False, runner=GitRunner()):
    if not promotion.changed:
        return PublishResult(committed=False, pushed=False, staged_paths=())
    preexisting = tuple(runner.lines(repo, "diff", "--cached", "--name-only"))
    if preexisting:
        return PublishResult(committed=False, pushed=False, staged_paths=(), deferred=True)
    runner.run(repo, "add", "--", PUBLISH_ROOT)
    staged = tuple(runner.lines(repo, "diff", "--cached", "--name-only"))
    forbidden = [path for path in staged if path != PUBLISH_ROOT and not path.startswith(PUBLISH_ROOT + "/")]
    if forbidden:
        raise PublishError("refusing non-bundle staged paths")
    if not staged:
        return PublishResult(committed=False, pushed=False, staged_paths=())
    ids = ", ".join(promotion.changed_projects[:3])
    suffix = "" if len(promotion.changed_projects) <= 3 else f" +{len(promotion.changed_projects) - 3}"
    runner.run(repo, "commit", "-m", f"content: update project atlas ({ids}{suffix})")
    if push:
        runner.run(repo, "push", "origin", "HEAD")
    return PublishResult(committed=True, pushed=push, staged_paths=staged)
```

The `publish` CLI acquires `RuntimeState.lock()`, runs worker unit validation, generates and promotes the bundle, then calls the publisher. It never invokes `git add -A`, `git add .`, or a shell-expanded wildcard.

- [ ] **Step 4: Run publisher tests in temporary Git repositories**

Run: `.venv/bin/python -m pytest tests/worker/test_publish.py -v`

Expected: all tests PASS; an unrelated dirty `server.js` remains unstaged.

- [ ] **Step 5: Commit the publisher**

```bash
git add atlas_worker/publish.py atlas_worker/cli.py tests/worker/test_publish.py tests/worker/git_helpers.py
git commit -m "feat: publish only validated atlas content"
```

### Task 3: User-Level systemd Timer

**Files:**
- Create: `deploy/systemd-user/project-atlas.service`
- Create: `deploy/systemd-user/project-atlas.timer`
- Create: `scripts/install_project_atlas_timer.sh`
- Modify: `deploy/DEPLOY.md`

**Interfaces:**
- Consumes: installed Python environment, workspace, local key, Git credentials, and network availability.
- Produces: `project-atlas.service` and a persistent 15-minute `project-atlas.timer`.

- [ ] **Step 1: Add a shell validation mode before installation behavior**

The installer accepts `--check` and validates source files without writing:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/dowon/securedir/git/codex/portfolio-homepage"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [[ "${1:-}" == "--check" ]]; then
  grep -q '^OnUnitActiveSec=15m$' "$ROOT/deploy/systemd-user/project-atlas.timer"
  grep -q 'scripts/project_atlas.py publish.*--push' "$ROOT/deploy/systemd-user/project-atlas.service"
  exit 0
fi
```

- [ ] **Step 2: Create exact service and timer units**

`project-atlas.service`:

```ini
[Unit]
Description=Build and publish Dowon Project Atlas
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/dowon/securedir/git/codex/portfolio-homepage
EnvironmentFile=-%h/.config/project-atlas/env
ExecStart=/home/dowon/securedir/git/codex/portfolio-homepage/.venv/bin/python scripts/project_atlas.py publish --workspace /home/dowon/securedir/git/codex --push
Nice=10
IOSchedulingClass=idle
```

`project-atlas.timer`:

```ini
[Unit]
Description=Run Project Atlas after login and every 15 minutes

[Timer]
OnBootSec=5m
OnUnitActiveSec=15m
RandomizedDelaySec=60
Persistent=true
Unit=project-atlas.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Complete non-root installation and removal commands**

The installer creates `$UNIT_DIR`, copies both unit files, runs `systemctl --user daemon-reload`, and runs `systemctl --user enable --now project-atlas.timer`. A `--remove` mode disables the timer, removes only these two installed units, and reloads the user daemon.

- [ ] **Step 4: Validate, install, and inspect the timer**

Run: `bash scripts/install_project_atlas_timer.sh --check`

Run: `bash scripts/install_project_atlas_timer.sh`

Run: `systemctl --user status project-atlas.timer --no-pager`

Run: `systemctl --user list-timers project-atlas.timer --no-pager`

Expected: timer is active and the next run is within 16 minutes. The service remains `inactive (dead)` between successful oneshot runs.

- [ ] **Step 5: Commit timer deployment files**

```bash
git add deploy/systemd-user scripts/install_project_atlas_timer.sh deploy/DEPLOY.md
git commit -m "feat: schedule project atlas updates"
```

### Task 4: Global AGENTS Memory and Skill Routing

**Files:**
- Modify with approval: `/home/dowon/.codex/AGENTS.md`
- Modify: `/home/dowon/securedir/git/codex/AGENTS.md`
- Modify: `/home/dowon/securedir/git/codex/central_memory/adapters/AGENTS.md`
- Inspect and update only when a stable trait is missing: `/home/dowon/securedir/git/codex/dowon_manager_agent_brief.md`
- Create: `scripts/audit_agent_memory_rules.py`
- Create: `tests/worker/test_agent_memory_rules.py`
- Create: `tests/worker/agent_helpers.py`

**Interfaces:**
- Consumes: the global, workspace, adapter, and owner-brief files.
- Produces: `audit_agent_files(paths) -> list[AuditFinding]` and a nonduplicated instruction chain available from every child repository.

`tests/worker/agent_helpers.py` defines `VALID_GLOBAL` with the two required global headings, `VALID_WORKSPACE` with only workspace index markers, and `write_agent_fixture(root, global_text, workspace_text) -> AgentPaths`.

- [ ] **Step 1: Write failing instruction-audit tests**

```python
def test_global_rules_route_selective_memory_and_superpowers(tmp_path):
    files = write_agent_fixture(tmp_path, global_text="", workspace_text="")
    findings = audit_agent_files(files)
    assert "global_missing_meaningful_checkpoint" in [item.code for item in findings]
    assert "global_missing_superpowers_preflight" in [item.code for item in findings]

def test_workspace_does_not_duplicate_global_checkpoint(tmp_path):
    files = write_agent_fixture(tmp_path, global_text=VALID_GLOBAL, workspace_text=VALID_GLOBAL + VALID_WORKSPACE)
    findings = audit_agent_files(files)
    assert "workspace_duplicates_global_policy" in [item.code for item in findings]
```

- [ ] **Step 2: Implement the audit and establish current findings**

```python
GLOBAL_REQUIRED = {
    "meaningful_checkpoint": "## Meaningful-Work Checkpoint",
    "owner_brief": "/home/dowon/securedir/git/codex/dowon_manager_agent_brief.md",
    "project_memory": "project_memory/",
    "codex_memories": "~/.codex/memories/",
    "superpowers": "superpowers:using-superpowers",
}
WORKSPACE_ONLY_MARKERS = {"central_memory/project_agent_inventory.md", "central_memory/active_projects.md"}
```

Run: `.venv/bin/python -m pytest tests/worker/test_agent_memory_rules.py -v`

Run: `.venv/bin/python scripts/audit_agent_memory_rules.py --global /home/dowon/.codex/AGENTS.md --workspace /home/dowon/securedir/git/codex/AGENTS.md`

Expected: tests PASS; the audit reports the missing meaningful-work checkpoint and Superpowers preflight until files are updated.

- [ ] **Step 3: Update the global file after explicit sandbox approval**

Add one concise global section with these exact semantics:

```markdown
## Meaningful-Work Checkpoint

- At the end of non-trivial work, selectively persist only durable information.
- Project-specific decisions, difficult revisions, rollbacks, and hard-won fixes go to the current project's `project_memory/`; do not create empty templates.
- Stable cross-project owner traits and collaboration preferences go to `/home/dowon/securedir/git/codex/dowon_manager_agent_brief.md` and must be merged without duplication.
- Unqualified "remember this" requests still route to `~/.codex/memories/`; never hand-edit Codex-generated memory state.
- Do not store routine commands, raw transcripts, secrets, one-off details, or speculative traits.

## Skill Preflight

- For non-trivial planning, design, implementation, debugging, or review, consult `superpowers:using-superpowers` first and follow the matching Superpowers workflow before specialist execution.
- Direct factual answers and trivial terminal lookups remain lightweight.
```

Do not copy these paragraphs into workspace or project files.

- [ ] **Step 4: Reduce workspace and adapter files to local responsibilities and audit again**

The workspace file retains project index maintenance, workspace paths, local AGENTS creation policy, and change safety. The adapter lists reference order and points to the root owner brief. Remove duplicated user-wide memory routing from both files.

Inspect the owner brief. Add or merge only these already established durable preferences when absent: selective memory rather than exhaustive logging; private data must not leave the local machine; difficult revisions and rollbacks are valuable public project narrative after sanitization. Do not add implementation details as personality traits.

Run: `.venv/bin/python scripts/audit_agent_memory_rules.py --global /home/dowon/.codex/AGENTS.md --workspace /home/dowon/securedir/git/codex/AGENTS.md --adapter /home/dowon/securedir/git/codex/central_memory/adapters/AGENTS.md`

Expected: `0 findings`.

- [ ] **Step 5: Commit the audit tooling and record non-repository file verification**

```bash
git add scripts/audit_agent_memory_rules.py tests/worker/test_agent_memory_rules.py tests/worker/agent_helpers.py
git commit -m "test: audit atlas memory instruction chain"
```

Record checksums of the global/workspace/adapter files in the local `.knowledge-worker/last-good-agent-rules.json`; do not copy their full text into the service repository.

### Task 5: Initial Project Classification and Session Backfill

**Files:**
- Create under each approved `ProjectRef.root`: `project_memory/project-profile.yaml`
- Create under an approved `ProjectRef.root` when evidence exists: `project_memory/build-story.md`
- Create under an approved `ProjectRef.root` when evidence exists: `project_memory/decisions.md`
- Create under an approved `ProjectRef.root` when evidence exists: `project_memory/rollbacks.md`
- Create under an approved `ProjectRef.root` when evidence exists: `project_memory/visuals/problem-solving.svg`
- Modify: `/home/dowon/securedir/git/codex/.knowledge-worker/project-aliases.yaml`
- Modify: `/home/dowon/securedir/git/codex/central_memory/active_projects.md`
- Modify: `/home/dowon/securedir/git/codex/central_memory/project_agent_inventory.md`

**Interfaces:**
- Consumes: real discovery report, current project files, Git history, and locally retained Codex sessions.
- Produces: reviewed project classifications, alias mappings, selective project memory, and a sanitized initial bundle.

- [ ] **Step 1: Generate discovery and profile proposals without writing**

Run: `.venv/bin/python scripts/project_atlas.py discover --workspace /home/dowon/securedir/git/codex --format json`

Run: `.venv/bin/python scripts/project_atlas.py bootstrap-profiles --workspace /home/dowon/securedir/git/codex --dry-run --report /home/dowon/securedir/git/codex/.knowledge-worker/review-queue/profile-proposals.json`

Expected: every eligible `projects/finish/*` child has its own proposal, no proposal ID equals `finish`, known generated/infrastructure directories are excluded, and unclassified projects remain `private`.

- [ ] **Step 2: Review publication classification before file creation**

Classify personal project narratives as `public` after the privacy scan. Mark projects containing company-confidential source, private datasets, raw production logs, third-party credentials, or nonpublishable personal information as `private`; use `excluded` for generated output and infrastructure. Add moved historical paths to `project-aliases.yaml` rather than changing stable IDs.

Run: `.venv/bin/python scripts/project_atlas.py bootstrap-profiles --workspace /home/dowon/securedir/git/codex --apply-approved /home/dowon/securedir/git/codex/.knowledge-worker/review-queue/profile-proposals.json`

Expected: only approved profiles are written; no empty story, decision, rollback, or SVG file is created.

- [ ] **Step 3: Run historical session backfill in dry-run mode**

Run: `.venv/bin/python scripts/project_atlas.py backfill --workspace /home/dowon/securedir/git/codex --sessions /home/dowon/.codex/sessions --since 2026-02-11 --dry-run --report /home/dowon/securedir/git/codex/.knowledge-worker/review-queue/session-backfill.json`

Expected: session files stream without being copied; mapped claims contain evidence hashes and confidence but no raw turns; unmapped paths and conflicting claims enter the local review queue.

- [ ] **Step 4: Apply high-confidence reviewed claims and build the initial bundle**

Run: `.venv/bin/python scripts/project_atlas.py backfill --workspace /home/dowon/securedir/git/codex --sessions /home/dowon/.codex/sessions --apply-reviewed /home/dowon/securedir/git/codex/.knowledge-worker/review-queue/session-backfill.json`

Run: `.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex`

Run: `rg -n "/home/dowon|\.jsonl|BEGIN .*PRIVATE KEY|sk-[A-Za-z0-9_-]{12,}" public-bundle`

Expected: the worker creates only evidence-backed memory files and SVGs; the final `rg` returns no matches.

- [ ] **Step 5: Update central indexes and commit only repository-local project memories deliberately**

Update `active_projects.md` and `project_agent_inventory.md` from the reviewed discovery report. For each independent project Git repository, inspect its status and commit only that project's intended `project_memory/` changes; do not create repositories, include unrelated user changes, or make one workspace-wide commit. Keep uncommitted memory local when a project has no valid repository.

### Task 6: GitHub and Railway Production Cutover

**Files:**
- Modify: `railway.json` only when current health/start settings fail verification
- Modify: `deploy/DEPLOY.md`
- Modify after parity: `/home/dowon/securedir/git/codex/central_memory/active_projects.md`
- Move after parity: `/home/dowon/securedir/git/codex/projects/llm_wiki` to `/home/dowon/securedir/git/codex/projects/legacy/llm_wiki`

**Interfaces:**
- Consumes: clean service code, validated `public-bundle/`, GitHub remote, and linked Railway service.
- Produces: a deployed manifest whose version matches the pushed commit and a reversible legacy migration.

- [ ] **Step 1: Run the complete pre-push gate**

Run: `.venv/bin/python -m pytest tests/worker -v`

Run: `npm test`

Run: `npm run test:ui`

Run: `.venv/bin/python scripts/project_atlas.py validate --workspace /home/dowon/securedir/git/codex`

Run: `git diff --check`

Expected: every command PASSes and privacy validation reports zero findings.

- [ ] **Step 2: Verify GitHub and Railway linkage without changing production**

Run: `git remote -v`

Run: `railway status`

The current local Railway CLI session is known to be expired. If `railway status` prints `Unauthorized`, run `railway login`, complete the browser login, and rerun `railway status`. Verify required variable names in the Railway dashboard without copying their values into terminal or committed logs.

Expected: GitHub remote is `Dohwon/Homepage-dowon` and Railway is linked to the intended service.

- [ ] **Step 3: Push the validated service and observe automatic deployment**

Run: `git push origin main`

Run: `railway logs`

Expected: Railway builds `main`, starts `node server.js`, and the health check at `/api/health` succeeds. Do not run a second manual `railway up` when the GitHub deployment is already in progress.

- [ ] **Step 4: Verify production content version and interaction parity**

Run `railway domain`, then store the returned HTTPS origin as `PROJECT_ATLAS_PRODUCTION_URL` in `/home/dowon/.config/project-atlas/env`. Run production checks without embedding the domain in scripts:

```bash
set -a
source /home/dowon/.config/project-atlas/env
set +a
curl -sS "$PROJECT_ATLAS_PRODUCTION_URL/api/health"
curl -sS "$PROJECT_ATLAS_PRODUCTION_URL/api/atlas/bootstrap"
```

Confirm the deployed manifest version matches local `public-bundle/manifest.json`, then run Playwright against production for Home, Projects, Topics, Graph, Changelog, Search, all project tabs, dark mode, and mobile navigation.

- [ ] **Step 5: Move the old generated wiki only after the parity gate**

Create `projects/legacy/` if absent, move the complete `projects/llm_wiki` directory there, and update central indexes so it is excluded from project discovery. Preserve `/home/dowon/securedir/git/codex/projects/scripts/generate_llm_wiki.py` as migration reference until the first stable release has operated for seven days; then archive it with the legacy wiki rather than deleting it.

### Task 7: Timer and Rollback Verification

**Files:**
- Modify: `deploy/DEPLOY.md`
- Modify: `README.md`
- Create: `tests/fixtures/privacy/local-path.json`

**Interfaces:**
- Consumes: installed timer and deployed service.
- Produces: tested no-op behavior, tested failed-gate behavior, and documented rollback commands.

- [ ] **Step 1: Run a no-op timer cycle**

Run: `systemctl --user start project-atlas.service`

Run: `journalctl --user -u project-atlas.service -n 100 --no-pager`

Run: `git status --short`

Expected: service exits successfully, logs `no public changes`, creates no commit, and leaves the service repository clean.

- [ ] **Step 2: Simulate a privacy failure without exposing a real secret**

Create the fixture with `{"summary":"read /home/dowon/private"}`. Run `.venv/bin/python scripts/project_atlas.py validate --fixture tests/fixtures/privacy/local-path.json`; do not modify the production bundle.

Expected: exit code `3`, no Git commit, no push, and the deployed manifest remains unchanged.

- [ ] **Step 3: Verify rollback to the previous public bundle commit**

Identify and revert the latest content commit without rewriting history:

```bash
CONTENT_COMMIT="$(git log -1 --format=%H -- public-bundle)"
git revert "$CONTENT_COMMIT"
```

Run the full pre-push gate and push only after tests pass. Do not use `git reset --hard` or rewrite `main` history.

- [ ] **Step 4: Document operational commands and failure meanings**

Document timer status, manual dry run, manual publish, logs, privacy exit code `3`, validation exit code `2`, I/O exit code `4`, Railway health/version verification, timer removal, and Git-revert rollback.

- [ ] **Step 5: Commit final operations documentation**

```bash
git add README.md deploy/DEPLOY.md
git commit -m "docs: add project atlas operations guide"
```

## Plan Completion Gate

```bash
.venv/bin/python -m pytest tests/worker -v
npm test
npm run test:ui
.venv/bin/python scripts/project_atlas.py validate --workspace /home/dowon/securedir/git/codex
.venv/bin/python scripts/audit_agent_memory_rules.py --global /home/dowon/.codex/AGENTS.md --workspace /home/dowon/securedir/git/codex/AGENTS.md --adapter /home/dowon/securedir/git/codex/central_memory/adapters/AGENTS.md
systemctl --user status project-atlas.timer --no-pager
git status --short
```

Expected: all tests and audits pass, the timer is active, the production manifest matches the validated local bundle, `projects/finish/*` remains independently indexed, and the repository is clean after a no-op timer run.
