# Project Atlas Local Knowledge Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only worker that discovers every real project, extracts selective project history, generates sanitized project memory and SVG maps, and atomically produces the Project Atlas public bundle.

**Architecture:** A Python package inside `portfolio-homepage` reads workspace projects, curated memory, Git metadata, and locally retained Codex JSONL sessions. Typed records and JSON Schema form the boundary between discovery, evidence, privacy, graph generation, and bundle publication; the worker writes to a staging directory and promotes only a fully validated public bundle.

**Tech Stack:** Python 3.10+, pytest 8.x, PyYAML 6.x, jsonschema 4.x, JSON/JSONL, Markdown, SVG, HMAC-SHA256

**Spec:** `docs/superpowers/specs/2026-08-24-project-atlas-design.md`

## Global Constraints

- `projects/finish/` is a status container; each eligible direct child is an independent project.
- New ambiguous projects default to `private` and cannot enter the public bundle.
- Publication precedence is manual profile override, then curated project memory, then verified inference.
- Raw Codex sessions, local provenance, HMAC keys, and absolute `/home/dowon` paths never enter `public-bundle/`.
- Semantic tag limits are Domain 1-2, Problem 1-3, Pattern 1-3, and Outcome 1-2.
- Inferred semantic tags require two distinct source classes; manual profile overrides can approve or reject tags.
- Each project publishes at most five project-similarity neighbors.
- Privacy failures block atomic promotion and preserve the last good bundle.
- Empty project memory templates are not generated.
- A no-op run changes no generated file.

---

## Planned File Structure

```text
portfolio-homepage/
├── atlas_worker/
│   ├── __init__.py                 # package version and public exports
│   ├── cli.py                      # command parsing and stage orchestration
│   ├── config.py                   # workspace paths and discovery policy
│   ├── models.py                   # typed records shared by all stages
│   ├── discovery.py                # active/finished project discovery
│   ├── evidence.py                 # source precedence and claim merging
│   ├── memory.py                   # project profile and Markdown readers
│   ├── sessions.py                 # streaming Codex JSONL reader and mapper
│   ├── backfill.py                 # high-signal event extraction
│   ├── memory_writer.py            # idempotent curated memory updates
│   ├── privacy.py                  # denylist, scanners, HMAC aliases
│   ├── visuals.py                  # accessible problem-solving SVG renderer
│   ├── taxonomy.py                 # evidence-backed tag selection
│   ├── graph.py                    # typed nodes and bounded similarity edges
│   ├── bundle.py                   # staging build and atomic promotion
│   └── manifest.py                 # hashes, changed-project set, last-good state
├── schemas/
│   ├── project-profile.schema.json
│   ├── public-project.schema.json
│   └── public-manifest.schema.json
├── scripts/
│   ├── project_atlas.py            # stable local entry point
│   └── scan_projects.py            # compatibility wrapper during migration
├── tests/worker/
│   ├── __init__.py
│   ├── helpers.py
│   ├── test_models.py
│   ├── test_discovery.py
│   ├── test_memory.py
│   ├── test_privacy.py
│   ├── test_sessions.py
│   ├── test_backfill.py
│   ├── test_visuals.py
│   ├── test_taxonomy_graph.py
│   ├── test_bundle.py
│   └── test_cli.py
└── requirements-atlas.txt
```

The local runtime state remains outside this Git repository at `/home/dowon/securedir/git/codex/.knowledge-worker/` and is introduced in the automation plan.

### Task 1: Typed Records and Schema Contracts

**Files:**
- Create: `atlas_worker/__init__.py`
- Create: `atlas_worker/models.py`
- Create: `schemas/project-profile.schema.json`
- Create: `schemas/public-project.schema.json`
- Create: `schemas/public-manifest.schema.json`
- Create: `requirements-atlas.txt`
- Create: `tests/__init__.py`
- Create: `tests/worker/__init__.py`
- Create: `tests/worker/helpers.py`
- Create: `tests/worker/test_models.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `Path` values supplied by later configuration.
- Produces: `ProjectRef`, `TagSet`, `EvidenceClaim`, `ProjectKnowledge`, `ProjectMemory`, `ProjectEvent`, `SessionEvent`, `TagCandidate`, `PublicProject`, `DiscoveryReport`, `GraphData`, `BundleManifest`, `MemoryUpdate`, `PromotionResult`, and `validate_schema(instance, schema_name) -> None`.

- [ ] **Step 1: Write failing model and schema tests**

```python
from pathlib import Path
import pytest

from atlas_worker.models import ProjectRef, TagSet, validate_schema


def test_finished_project_serializes_as_independent_project():
    ref = ProjectRef(
        project_id="260410-keyboard-piano",
        display_name="Keyboard Piano",
        root=Path("/workspace/projects/finish/260410_keyboard_piano"),
        relative_path="projects/finish/260410_keyboard_piano",
        lifecycle="finished",
        publication="public",
        aliases=(),
    )
    assert ref.to_dict()["lifecycle"] == "finished"
    assert ref.project_id != "finish"

def test_tag_limits_are_enforced():
    with pytest.raises(ValueError, match=r"domain supports 1\.\.2 values"):
        TagSet(domain=("AI", "Product", "Data"), problem=("Routing",), pattern=("Eval",), technology=(), outcome=("Tool",))

def test_private_project_is_rejected_by_public_schema():
    candidate = {
        "id": "secret",
        "name": "Secret",
        "lifecycle": "active",
        "publication": "private",
        "summary": "Not publishable",
        "tags": {"domain": ["AI"], "problem": ["Routing"], "pattern": ["Evaluation"], "technology": ["Python"], "outcome": ["Tool"]}
    }
    with pytest.raises(ValueError, match="publication"):
        validate_schema(candidate, "public-project")
```

- [ ] **Step 2: Run the tests and confirm the package is missing**

Run: `python3 -m venv .venv`

Run: `.venv/bin/pip install "PyYAML>=6.0,<7" "jsonschema>=4.22,<5" "pytest>=8,<9"`

Run: `.venv/bin/python -m pytest tests/worker/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atlas_worker'`.

- [ ] **Step 3: Implement dataclasses, schema lookup, and pinned dependency ranges**

```python
# atlas_worker/models.py
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Lifecycle = Literal["active", "finished"]
Publication = Literal["public", "private", "excluded"]
TagKind = Literal["domain", "problem", "pattern", "technology", "outcome"]

TAG_LIMITS = {"domain": (1, 2), "problem": (1, 3), "pattern": (1, 3), "technology": (0, 12), "outcome": (1, 2)}

@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    display_name: str
    root: Path
    relative_path: str
    lifecycle: Lifecycle
    publication: Publication
    aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["root"] = str(self.root)
        return value

@dataclass(frozen=True)
class TagSet:
    domain: tuple[str, ...]
    problem: tuple[str, ...]
    pattern: tuple[str, ...]
    technology: tuple[str, ...]
    outcome: tuple[str, ...]

    def __post_init__(self) -> None:
        for field, (minimum, maximum) in TAG_LIMITS.items():
            count = len(getattr(self, field))
            if count < minimum or count > maximum:
                raise ValueError(f"{field} supports {minimum}..{maximum} values")

@dataclass(frozen=True)
class EvidenceClaim:
    field: str
    value: object
    source_class: str
    confidence: float
    evidence_id: str
    claim_type: str = "fact"
    event_date: str = ""

@dataclass(frozen=True)
class ProjectKnowledge:
    values: dict[str, object]
    winners: dict[str, EvidenceClaim]

@dataclass(frozen=True)
class PromotionResult:
    changed: bool
    changed_projects: tuple[str, ...]
```

Use these exact supplemental record signatures in the same module: `SessionEvent(session_id, timestamp, cwd, role, text, source_path="", line_number=0, parse_error="")`, `ProjectEvent(event_id, date, title, context, decision, outcome, stage)`, `TagCandidate(label, kind, source_class, evidence_id, confidence)`, and `MemoryUpdate(changed_files: tuple[str, ...])`. `GraphData.project_neighbors(project_id) -> tuple[GraphEdge, ...]` returns only project-similarity edges.

`requirements-atlas.txt`:

```text
PyYAML>=6.0,<7
jsonschema>=4.22,<5
pytest>=8,<9
```

Define the three schemas with `additionalProperties: false`; require stable IDs, publication state, lifecycle, summary, typed tags, and bundle version. `public-project.schema.json` permits only `publication: "public"`.

Create empty `tests/__init__.py` and `tests/worker/__init__.py`. Add `make_project_ref(root: Path, project_id="alpha", lifecycle="active", publication="public") -> ProjectRef` and `write_project_profile(root: Path, **overrides) -> Path` to `tests/worker/helpers.py`; later tasks extend this file when they introduce new record types. Add `.venv/`, `.atlas-staging/`, and `.public-bundle.previous/` to `.gitignore`, but do not ignore `public-bundle/`.

- [ ] **Step 4: Run contract tests**

Run: `.venv/bin/pip install -r requirements-atlas.txt`

Run: `.venv/bin/python -m pytest tests/worker/test_models.py -v`

Expected: all three tests PASS.

- [ ] **Step 5: Commit the contracts**

```bash
git add atlas_worker schemas requirements-atlas.txt tests .gitignore
git commit -m "feat: define project atlas data contracts"
```

### Task 2: Deterministic Project Discovery

**Files:**
- Create: `atlas_worker/config.py`
- Create: `atlas_worker/discovery.py`
- Create: `tests/worker/test_discovery.py`
- Modify: `scripts/scan_projects.py`

**Interfaces:**
- Consumes: `DiscoveryConfig(workspace_root, projects_root, excluded_names)` and optional `project_memory/project-profile.yaml`.
- Produces: `discover_projects(config: DiscoveryConfig) -> DiscoveryReport`, whose `projects` are sorted by stable ID and whose `ambiguous` entries never publish.

- [ ] **Step 1: Write failing active, finish-child, exclusion, and nested-repo tests**

```python
def test_finish_children_are_projects_but_finish_is_not(tmp_path):
    projects = tmp_path / "projects"
    (projects / "alpha").mkdir(parents=True)
    (projects / "finish" / "beta").mkdir(parents=True)
    (projects / "finish" / "gamma").mkdir(parents=True)
    (projects / "scripts").mkdir()

    report = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert [item.project_id for item in report.projects] == ["alpha", "beta", "gamma"]
    assert [item.lifecycle for item in report.projects] == ["active", "finished", "finished"]
    assert "finish" not in [item.project_id for item in report.projects]
    assert "scripts" not in [item.project_id for item in report.projects]
```

Add a second test where `alpha/nested/.git` exists: it remains part of `alpha` until `alpha/nested/project_memory/project-profile.yaml` declares a distinct ID.

- [ ] **Step 2: Run the discovery test and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_discovery.py -v`

Expected: FAIL because `atlas_worker.discovery` does not exist.

- [ ] **Step 3: Implement configured discovery and profile overrides**

```python
DEFAULT_EXCLUDED = frozenset({
    ".cache", ".codex", ".git", ".pytest_cache", ".venv", "__pycache__",
    "docs", "legacy", "llm_wiki", "node_modules", "scripts", "tests", "tmp",
})

def discover_projects(config: DiscoveryConfig) -> DiscoveryReport:
    candidates = [(path, "active") for path in config.projects_root.iterdir() if path.is_dir() and path.name != "finish"]
    finish = config.projects_root / "finish"
    if finish.is_dir():
        candidates.extend((path, "finished") for path in finish.iterdir() if path.is_dir())
    refs, ambiguous = [], []
    for root, lifecycle in candidates:
        if root.name.startswith(".") or root.name in config.excluded_names:
            continue
        profile = load_optional_profile(root / "project_memory" / "project-profile.yaml")
        ref = classify_candidate(config.workspace_root, root, lifecycle, profile)
        refs.append(ref)
        if ref.publication == "private" and not profile:
            ambiguous.append(ref)
    return DiscoveryReport(projects=tuple(sorted(refs, key=lambda item: item.project_id)), ambiguous=tuple(ambiguous))
```

Use normalized relative paths, slug collision detection, and profile aliases. Do not recurse through `finish/` beyond its direct children.

- [ ] **Step 4: Convert the old scanner into a compatibility wrapper and rerun tests**

`scripts/scan_projects.py` becomes a deprecation wrapper that calls `atlas_worker.cli.main(["discover"])`; remove its keyword-category and single-file auto-project behavior.

Run: `.venv/bin/python -m pytest tests/worker/test_discovery.py -v`

Expected: all discovery tests PASS.

- [ ] **Step 5: Commit deterministic discovery**

```bash
git add atlas_worker/config.py atlas_worker/discovery.py scripts/scan_projects.py tests/worker/test_discovery.py
git commit -m "feat: discover active and finished projects"
```

### Task 3: Curated Memory Loading and Evidence Precedence

**Files:**
- Create: `atlas_worker/memory.py`
- Create: `atlas_worker/evidence.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_memory.py`

**Interfaces:**
- Consumes: project profile YAML, optional `project_memory/*.md`, legacy `manager_memory/`, source facts, and inferred claims.
- Produces: `load_project_memory(ref: ProjectRef) -> ProjectMemory` and `merge_claims(claims: Iterable[EvidenceClaim]) -> ProjectKnowledge`.

- [ ] **Step 1: Write failing precedence and empty-template tests**

```python
def test_manual_profile_beats_curated_and_inferred_claims():
    claims = [
        EvidenceClaim(field="summary", value="inferred", source_class="session", confidence=0.92, evidence_id="s1"),
        EvidenceClaim(field="summary", value="curated", source_class="project_memory", confidence=1.0, evidence_id="m1"),
        EvidenceClaim(field="summary", value="manual", source_class="profile", confidence=1.0, evidence_id="p1"),
    ]
    assert merge_claims(claims).values["summary"] == "manual"

def test_missing_optional_memory_files_return_empty_sections(tmp_path):
    ref = make_project_ref(tmp_path)
    (tmp_path / "project_memory").mkdir()
    write_project_profile(tmp_path, publication="public")
    memory = load_project_memory(ref)
    assert memory.rollbacks == ()
    assert not (tmp_path / "project_memory" / "rollbacks.md").exists()
```

- [ ] **Step 2: Run tests and verify missing modules**

Run: `.venv/bin/python -m pytest tests/worker/test_memory.py -v`

Expected: FAIL importing `atlas_worker.memory`.

- [ ] **Step 3: Implement profile validation, Markdown section parsing, and ranked claims**

```python
SOURCE_PRIORITY = {"session": 10, "source": 20, "git": 30, "project_memory": 40, "profile": 50}

def merge_claims(claims):
    grouped = defaultdict(list)
    for claim in claims:
        grouped[claim.field].append(claim)
    values = {}
    winners = {}
    for field, options in grouped.items():
        winner = max(options, key=lambda item: (SOURCE_PRIORITY[item.source_class], item.confidence, item.evidence_id))
        values[field] = winner.value
        winners[field] = winner
    return ProjectKnowledge(values=values, winners=winners)
```

Parse Markdown by explicit second-level headings and list items rather than arbitrary string slicing. Keep absolute evidence paths only in local claim metadata.

- [ ] **Step 4: Run memory tests**

Run: `.venv/bin/python -m pytest tests/worker/test_memory.py -v`

Expected: all memory and precedence tests PASS.

- [ ] **Step 5: Commit memory ingestion**

```bash
git add atlas_worker/memory.py atlas_worker/evidence.py tests/worker/test_memory.py
git commit -m "feat: merge curated project knowledge"
```

### Task 4: Fail-Closed Privacy Gate

**Files:**
- Create: `atlas_worker/privacy.py`
- Create: `tests/worker/test_privacy.py`

**Interfaces:**
- Consumes: structured candidate public records and rendered Markdown/SVG/JSON text.
- Produces: `PrivacyGate.scan(record: object) -> PrivacyReport`, `PrivacyGate.require_safe(record) -> None`, `PrivacyGate.require_allowed_source(path: Path) -> None`, and `hmac_alias(value: str, key: bytes, prefix: str) -> str`.

- [ ] **Step 1: Write failing private-data, path, source-map, comment, and alias tests**

```python
def test_public_bundle_rejects_local_paths_and_secrets():
    gate = PrivacyGate(alias_key=b"unit-test-key")
    report = gate.scan({"summary": "read /home/dowon/private", "token": "sk-test-secret-value"})
    assert {finding.category for finding in report.findings} == {"absolute_path", "secret"}

def test_alias_is_deterministic_and_does_not_embed_source():
    first = hmac_alias("Private Client", b"local-key", "CLIENT")
    second = hmac_alias("Private Client", b"local-key", "CLIENT")
    assert first == second
    assert re.fullmatch(r"CLIENT_[A-F0-9]{8}", first)
    assert "Private" not in first

def test_html_comments_and_source_maps_are_blocked():
    gate = PrivacyGate(alias_key=b"unit-test-key")
    report = gate.scan("<!-- internal -->\n//# sourceMappingURL=app.js.map")
    assert {item.category for item in report.findings} == {"html_comment", "source_map"}

def test_source_denylist_blocks_environment_sessions_and_raw_logs(tmp_path):
    gate = PrivacyGate(alias_key=b"unit-test-key")
    for relative in [".env", ".codex/sessions/session.jsonl", "logs/raw.log"]:
        with pytest.raises(PrivacyViolation):
            gate.require_allowed_source(tmp_path / relative)

def test_explicit_public_contact_is_allowlisted_but_other_email_is_blocked():
    gate = PrivacyGate(alias_key=b"unit-test-key", approved_public_values={"public@example.com"})
    assert not gate.scan({"publicEmail": "public@example.com"}).findings
    assert {item.category for item in gate.scan({"notes": "private@example.com"}).findings} == {"email"}
```

The test module imports `re` and `pytest` in addition to the privacy interfaces.

- [ ] **Step 2: Run tests and verify privacy module is absent**

Run: `.venv/bin/python -m pytest tests/worker/test_privacy.py -v`

Expected: FAIL importing `atlas_worker.privacy`.

- [ ] **Step 3: Implement recursive scanning and non-reversible aliases**

```python
SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
ABSOLUTE_PATH = re.compile(r"(?:/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
PRIVATE_IP = re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")
DENIED_SOURCE_NAMES = {".env", "credentials.json", "auth.json"}
DENIED_SOURCE_PARTS = {".codex/sessions", "logs", "raw-logs", "private-data"}

def hmac_alias(value: str, key: bytes, prefix: str) -> str:
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:8].upper()
    return f"{prefix}_{digest}"

class PrivacyGate:
    def require_safe(self, record: object) -> None:
        report = self.scan(record)
        if report.findings:
            categories = ", ".join(sorted({item.category for item in report.findings}))
            raise PrivacyViolation(f"public bundle blocked: {categories}")
```

Traverse mapping keys and values, lists, Markdown, SVG, and JSON. Report category and JSON pointer only; never copy the matching sensitive value into the report.

- [ ] **Step 4: Run privacy tests**

Run: `.venv/bin/python -m pytest tests/worker/test_privacy.py -v`

Expected: all privacy tests PASS.

- [ ] **Step 5: Commit the privacy boundary**

```bash
git add atlas_worker/privacy.py tests/worker/test_privacy.py
git commit -m "feat: block private data from atlas bundles"
```

### Task 5: Streaming Session Mapping and Selective Backfill

**Files:**
- Create: `atlas_worker/sessions.py`
- Create: `atlas_worker/backfill.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_sessions.py`
- Create: `tests/worker/test_backfill.py`

**Interfaces:**
- Consumes: Codex session JSONL paths, project aliases, and `session-cursor.json` checksums.
- Produces: `iter_session_events(path: Path) -> Iterator[SessionEvent]`, `map_session(event, projects, aliases) -> str | None`, and `extract_signal_claims(events) -> tuple[EvidenceClaim, ...]`.

- [ ] **Step 1: Write failing streaming, alias, cursor, and signal-selection tests**

```python
def test_session_maps_by_historical_cwd_alias(tmp_path):
    projects = (make_project_ref(tmp_path / "current", project_id="tmap-clone"),)
    aliases = {"/old/codex/projects/260329_tmap_clone": "tmap-clone"}
    event = SessionEvent(session_id="s1", timestamp="2026-04-01T10:00:00Z", cwd="/old/codex/projects/260329_tmap_clone", role="user", text="두 시안 중 첫 번째로 롤백해")
    assert map_session(event, projects, aliases) == "tmap-clone"

def test_routine_turn_is_ignored_but_rollback_is_selected():
    events = [
        make_session_event("파일 목록 보여줘"),
        make_session_event("새 시안 말고 이전 탐색 구조로 롤백해"),
    ]
    claims = extract_signal_claims(events)
    assert [claim.claim_type for claim in claims] == ["rollback"]
```

Include a 10,000-line fixture generated inside the test and assert `iter_session_events` is an iterator, not a list.

Extend `tests/worker/helpers.py` with `make_session_event(text: str, cwd="/workspace/projects/alpha", session_id="s1") -> SessionEvent` after defining `SessionEvent` in `atlas_worker.models`.

- [ ] **Step 2: Run session tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v`

Expected: FAIL because session modules do not exist.

- [ ] **Step 3: Implement line-by-line parsing, path normalization, and signal rules**

```python
SIGNAL_RULES = {
    "rollback": re.compile(r"롤백|되돌려|이전 (?:버전|시안)|revert|rollback", re.I),
    "revision": re.compile(r"다른 시안|다시 수정|여러 시안|재설계|방향 변경", re.I),
    "failure": re.compile(r"테스트 실패|회귀|오류|깨졌|실패 원인", re.I),
    "decision": re.compile(r"결정|채택|선택|trade-?off|대안", re.I),
}

def iter_session_events(path):
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                yield SessionEvent.parse_error(path, line_number)
                continue
            event = normalize_codex_record(raw, path, line_number)
            if event is not None:
                yield event
```

Store only session ID, timestamps, normalized claim, evidence hash, confidence, and local source pointer. Do not store full turn text in project memory or provenance summaries.

Use explicit confidence thresholds: verified claims at `>= 0.85` may merge automatically, claims from `0.60` through `0.84` enter the review queue, and claims below `0.60` are ignored. Explicit rollback language scores `0.95`; a user correction confirmed by a later change scores `0.90`; a test failure followed by a passing result or an explicit architecture choice scores `0.85`; three or more edits to the same file or multiple visual alternatives score `0.75` until corroborated. Session length alone scores at most `0.55` and cannot create memory.

- [ ] **Step 4: Run streaming and selection tests**

Run: `.venv/bin/python -m pytest tests/worker/test_sessions.py tests/worker/test_backfill.py -v`

Expected: all session and backfill tests PASS.

- [ ] **Step 5: Commit selective backfill**

```bash
git add atlas_worker/sessions.py atlas_worker/backfill.py tests/worker/test_sessions.py tests/worker/test_backfill.py
git commit -m "feat: extract selective history from codex sessions"
```

### Task 6: Idempotent Project Memory and SVG Updates

**Files:**
- Create: `atlas_worker/memory_writer.py`
- Create: `atlas_worker/visuals.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_visuals.py`

**Interfaces:**
- Consumes: verified `ProjectKnowledge` and selected historical claims.
- Produces: `update_project_memory(ref, knowledge, dry_run=False) -> MemoryUpdate` and `render_problem_solving_svg(project, events) -> str`.

- [ ] **Step 1: Write failing selective-write, deduplication, and SVG accessibility tests**

```python
def test_writer_creates_only_sections_with_evidence(tmp_path):
    ref = make_project_ref(tmp_path)
    update_project_memory(ref, make_decision_knowledge(), dry_run=False)
    assert (tmp_path / "project_memory" / "decisions.md").exists()
    assert not (tmp_path / "project_memory" / "rollbacks.md").exists()

def test_svg_contains_accessible_metadata_and_no_script():
    svg = render_problem_solving_svg(make_project_ref(Path("/workspace/atlas"), project_id="atlas"), make_challenge_events())
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    assert '<title id="title">' in svg
    assert '<desc id="desc">' in svg
    assert 'viewBox="0 0 1200 640"' in svg
    assert "<script" not in svg.lower()
```

- [ ] **Step 2: Run memory-writer and visual tests**

Run: `.venv/bin/python -m pytest tests/worker/test_visuals.py -v`

Expected: FAIL importing the new modules.

- [ ] **Step 3: Implement stable event IDs, managed Markdown blocks, and escaped SVG nodes**

```python
def managed_event_block(event):
    return (
        f"<!-- atlas:event:{event.event_id} -->\n"
        f"### {event.date} · {event.title}\n\n"
        f"- 상황: {event.context}\n"
        f"- 선택: {event.decision}\n"
        f"- 결과: {event.outcome}\n"
        f"<!-- /atlas:event:{event.event_id} -->\n"
    )
```

Preserve user-authored text outside managed blocks. Escape every SVG text node with `html.escape`, embed no external resources, use CSS custom properties with light/dark fallbacks, and emit the sequence Constraint -> Attempt -> Revision -> Decision -> Result.

Extend `tests/worker/helpers.py` with `make_decision_knowledge() -> ProjectKnowledge` containing one verified decision claim and `make_challenge_events() -> tuple[ProjectEvent, ...]` containing one event for each of constraint, attempt, revision, decision, and result.

- [ ] **Step 4: Run tests twice to verify idempotence**

Run: `.venv/bin/python -m pytest tests/worker/test_visuals.py -v`

Then run the update fixture twice and assert the second `MemoryUpdate.changed_files` is empty.

Expected: tests PASS and second update reports no changes.

- [ ] **Step 5: Commit memory and SVG generation**

```bash
git add atlas_worker/memory_writer.py atlas_worker/visuals.py tests/worker/test_visuals.py
git commit -m "feat: maintain project stories and visual maps"
```

### Task 7: Evidence-Backed Taxonomy and Bounded Graph

**Files:**
- Create: `atlas_worker/taxonomy.py`
- Create: `atlas_worker/graph.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_taxonomy_graph.py`

**Interfaces:**
- Consumes: public project candidates and local tag evidence grouped by source class.
- Produces: `select_tags(project, candidates) -> TagSet` and `build_graph(projects) -> GraphData` with typed nodes and at most five similarity neighbors per project.

- [ ] **Step 1: Write failing evidence threshold, limits, weighting, and neighbor-bound tests**

```python
def test_inferred_semantic_tag_requires_two_source_classes():
    candidates = [
        TagCandidate("Agent Routing", "problem", "source", "code-1", 0.9),
        TagCandidate("Agent Routing", "problem", "session", "session-1", 0.8),
        TagCandidate("Generic", "pattern", "session", "session-2", 0.9),
    ]
    selected = select_tags(make_public_project("alpha"), candidates)
    assert "Agent Routing" in selected.problem
    assert "Generic" not in selected.pattern

def test_similarity_edges_are_limited_to_five_neighbors():
    graph = build_graph(tuple(make_public_project(f"project-{index}") for index in range(7)))
    neighbors = graph.project_neighbors("project-0")
    assert len(neighbors) <= 5
```

- [ ] **Step 2: Run graph tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_taxonomy_graph.py -v`

Expected: FAIL importing taxonomy and graph modules.

- [ ] **Step 3: Implement source-class voting and deterministic similarity scoring**

```python
TAG_WEIGHTS = {"domain": 4, "problem": 6, "pattern": 5, "technology": 1, "outcome": 4}

def similarity(left: PublicProject, right: PublicProject) -> int:
    total = 0
    for kind, weight in TAG_WEIGHTS.items():
        total += len(set(getattr(left.tags, kind)) & set(getattr(right.tags, kind))) * weight
    return total

def top_neighbors(project, projects, limit=5):
    scored = [(similarity(project, other), other.project_id) for other in projects if other.project_id != project.project_id]
    return [(score, project_id) for score, project_id in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0][:limit]
```

Build typed Project, Domain, Problem, Pattern, Technology, and Outcome nodes. Emit one canonical tag node per normalized label and aggregate shared-tag reasons into similarity edge metadata.

Extend `tests/worker/helpers.py` with `make_public_project(project_id: str) -> PublicProject`; use one shared Domain, Problem, and Pattern so the seven-project fixture creates more than five candidate neighbors.

- [ ] **Step 4: Run taxonomy and graph tests**

Run: `.venv/bin/python -m pytest tests/worker/test_taxonomy_graph.py -v`

Expected: all tests PASS with stable ordering.

- [ ] **Step 5: Commit graph generation**

```bash
git add atlas_worker/taxonomy.py atlas_worker/graph.py tests/worker/test_taxonomy_graph.py
git commit -m "feat: generate evidence-backed project graph"
```

### Task 8: Atomic Public Bundle and Incremental Manifest

**Files:**
- Create: `atlas_worker/manifest.py`
- Create: `atlas_worker/bundle.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_bundle.py`

**Interfaces:**
- Consumes: sanitized public projects, graph data, search documents, current source hashes, and previous manifest.
- Produces: `build_candidate_bundle(context, staging_dir) -> BundleManifest` and `promote_bundle(staging_dir, public_dir, gate) -> PromotionResult`.

- [ ] **Step 1: Write failing atomicity, no-op, privacy-failure, and path-leak tests**

```python
def test_privacy_failure_preserves_last_good_bundle(tmp_path):
    public_dir = tmp_path / "public-bundle"
    write_bundle_fixture(public_dir, version="good", summary="safe")
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, version="bad", summary="/home/dowon/private")

    with pytest.raises(PrivacyViolation):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert json.loads((public_dir / "manifest.json").read_text(encoding="utf-8"))["version"] == "good"

def test_identical_candidate_is_noop(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version="same", summary="safe")
    write_bundle_fixture(staging, version="same", summary="safe")
    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))
    assert not result.changed
    assert result.changed_projects == ()
```

The test module imports `json` and `pytest` for the manifest assertion and `pytest.raises`.

- [ ] **Step 2: Run bundle tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py -v`

Expected: FAIL importing bundle modules.

- [ ] **Step 3: Implement content hashing, staged validation, and atomic rename**

```python
def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def promote_bundle(staging_dir, public_dir, gate):
    candidate = load_bundle_tree(staging_dir)
    gate.require_safe(candidate)
    validate_bundle(candidate)
    previous_hash = tree_hash(public_dir) if public_dir.exists() else None
    candidate_hash = tree_hash(staging_dir)
    if previous_hash == candidate_hash:
        return PromotionResult(changed=False, changed_projects=())
    backup = public_dir.with_name(".public-bundle.previous")
    atomic_replace_directory(staging_dir, public_dir, backup)
    return PromotionResult(changed=True, changed_projects=changed_project_ids(public_dir, backup))
```

Generate project JSON/Markdown/SVG, graph nodes/edges, topics, changelog, and search index exactly as specified. Run privacy scanning after rendering every format and once more over the full staging tree.

Manifest hashes and versions are content-derived. Do not include the current wall-clock time in hashed fields; store a source event date only when source evidence changed. This keeps identical runs byte-for-byte stable.

Extend `tests/worker/helpers.py` with `write_bundle_fixture(root: Path, version: str, summary: str) -> None`; it writes a schema-valid one-project bundle with empty graph edges and a deterministic manifest.

- [ ] **Step 4: Run bundle tests**

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py -v`

Expected: all bundle tests PASS.

- [ ] **Step 5: Commit atomic bundling**

```bash
git add atlas_worker/manifest.py atlas_worker/bundle.py tests/worker/test_bundle.py
git commit -m "feat: build atomic public atlas bundles"
```

### Task 9: Worker CLI and End-to-End Dry Run

**Files:**
- Create: `atlas_worker/cli.py`
- Create: `scripts/project_atlas.py`
- Modify: `tests/worker/helpers.py`
- Create: `tests/worker/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior modules and command arguments.
- Produces commands `discover`, `backfill`, `build`, `validate`, and `run`; every command supports `--workspace`, and mutating commands support `--dry-run`.

- [ ] **Step 1: Write failing CLI integration tests**

```python
def test_run_dry_run_does_not_write_bundle(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    code = main(["run", "--workspace", str(workspace), "--dry-run"])
    assert code == 0
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()

def test_discovery_report_has_no_finish_aggregate(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    output = invoke_cli_json(["discover", "--workspace", str(workspace), "--format", "json"])
    assert "finish" not in [item["id"] for item in output["projects"]]
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_cli.py -v`

Expected: FAIL importing `atlas_worker.cli`.

- [ ] **Step 3: Implement command orchestration and stable exit codes**

```python
EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_PRIVACY = 3
EXIT_IO = 4

def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except PrivacyViolation as error:
        print(str(error), file=sys.stderr)
        return EXIT_PRIVACY
    except (SchemaError, ConfigError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_VALIDATION
```

`scripts/project_atlas.py` imports `main` after adding the repository root to `sys.path` and exits with its code. Support `discover`, `bootstrap-profiles`, `backfill`, `build`, `validate`, and `run`; `validate` accepts either `--workspace` or `--fixture`. Mutating commands support `--dry-run`, and profile/backfill commands support reviewed-report application. Extend `tests/worker/helpers.py` with `make_workspace_fixture(root: Path) -> Path`, creating one active and one finished project plus the service directory, and `invoke_cli_json(args: list[str]) -> dict[str, object]`, which captures stdout from `main(args)` and parses it. Document exact dry-run and validation commands in `README.md`.

- [ ] **Step 4: Run the complete worker suite and real-workspace discovery**

Run: `.venv/bin/python -m pytest tests/worker -v`

Run: `.venv/bin/python scripts/project_atlas.py discover --workspace /home/dowon/securedir/git/codex --format json`

Run: `.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex --dry-run`

Expected: tests PASS; discovery lists active projects plus individual `finish/*` children; no entry has ID `finish`; dry run writes no project memory or public bundle.

- [ ] **Step 5: Commit the local pipeline entry point**

```bash
git add atlas_worker/cli.py scripts/project_atlas.py tests/worker/test_cli.py README.md
git commit -m "feat: add project atlas worker commands"
```

## Plan Completion Gate

Run all of the following before starting the public experience plan:

```bash
.venv/bin/python -m pytest tests/worker -v
.venv/bin/python scripts/project_atlas.py discover --workspace /home/dowon/securedir/git/codex --format json
.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex --dry-run
git status --short
```

Expected: every unit/integration test passes, the real-workspace report contains no aggregate `finish` project, the dry run reports privacy status without writes, and only intentionally committed files are present.
