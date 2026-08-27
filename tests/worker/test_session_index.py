import json
from pathlib import Path

from atlas_worker.models import SessionEvent, SessionMapping, SessionTrace
from atlas_worker.session_index import index_session, map_session_trace, merge_child_evidence
from tests.worker.helpers import make_project_ref


class FakeGitOwner:
    def __init__(self, owners: dict[str, str] | None = None):
        self.owners = owners or {}

    def __call__(self, path: Path, projects):
        return self.owners.get(str(path))


def _projects(tmp_path):
    return (
        make_project_ref(tmp_path / "projects" / "alpha", project_id="alpha"),
        make_project_ref(tmp_path / "projects" / "beta", project_id="beta"),
    )


def _trace(session_id: str, *, parent: str = "", cwd: str = "") -> SessionTrace:
    return SessionTrace(
        session_id=session_id,
        parent_session_id=parent,
        cwd=cwd,
        changed_paths=(),
        git_common_dirs=(),
        events=(),
    )


def _mapping(session_id: str, project_id: str | None, reason: str) -> SessionMapping:
    return SessionMapping(session_id=session_id, project_id=project_id, reason=reason)


def test_index_session_retains_messages_and_structured_patch_targets_only(tmp_path):
    session_path = tmp_path / "session.jsonl"
    records = (
        {
            "type": "session_meta",
            "payload": {
                "id": "child",
                "parent_session_id": "parent",
                "cwd": "/workspace/projects/alpha",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "do not scan /private/prose.py"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "item": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "arguments": "*** Update File: src/app.py\n@@\n-old\n+new\n",
                    "workdir": "/workspace/projects/beta",
                }
            },
        },
        {"type": "response_item", "payload": {"item": {"type": "function_call", "name": "pwd", "arguments": {"path": "/workspace/projects/beta/config.yaml"}}}},
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.session_id == "child"
    assert trace.parent_session_id == "parent"
    assert trace.cwd == "/workspace/projects/alpha"
    assert trace.changed_paths == (
        "/workspace/projects/beta",
        "/workspace/projects/beta/src/app.py",
        "/workspace/projects/beta/config.yaml",
    )
    assert [event.text for event in trace.events] == ["", "do not scan /private/prose.py"]


def test_changed_file_path_outranks_parent_cwd(tmp_path):
    trace = SessionTrace(
        session_id="child",
        parent_session_id="parent",
        cwd=str(tmp_path / "projects" / "alpha"),
        changed_paths=(str(tmp_path / "projects" / "beta" / "src" / "app.js"),),
        git_common_dirs=(),
        events=(),
    )

    mapping = map_session_trace(trace, _projects(tmp_path), {}, FakeGitOwner())

    assert mapping.project_id == "beta"
    assert mapping.reason == "changed-path"


def test_worktree_git_owner_outranks_cwd_when_no_changed_root_matches(tmp_path):
    worktree = tmp_path / "scratch" / "atlas-worktree"
    trace = SessionTrace(
        session_id="child",
        parent_session_id="",
        cwd=str(tmp_path / "projects" / "alpha"),
        changed_paths=(str(worktree / "src" / "app.py"),),
        git_common_dirs=(str(worktree),),
        events=(),
    )

    mapping = map_session_trace(trace, _projects(tmp_path), {}, FakeGitOwner({str(worktree / "src" / "app.py"): "beta", str(worktree): "beta"}))

    assert mapping.project_id == "beta"
    assert mapping.reason == "git-common-dir"


def test_same_strength_conflict_is_ambiguous(tmp_path):
    trace = SessionTrace(
        session_id="conflict",
        parent_session_id="",
        cwd="",
        changed_paths=(
            str(tmp_path / "projects" / "alpha" / "a.py"),
            str(tmp_path / "projects" / "beta" / "b.py"),
        ),
        git_common_dirs=(),
        events=(),
    )

    mapping = map_session_trace(trace, _projects(tmp_path), {}, FakeGitOwner())

    assert mapping.project_id is None
    assert mapping.reason == "ambiguous"


def test_trace_mapping_preserves_relative_and_windows_alias_behavior(tmp_path):
    project = make_project_ref(tmp_path / "projects" / "atlas", project_id="atlas")
    project = project.__class__(**{**project.__dict__, "aliases": ("projects/old-atlas",)})
    aliases = {r"C:\\Archive\\Atlas": "atlas"}

    relative = map_session_trace(
        _trace("relative", cwd="/archive/projects/old-atlas/nested"), (project,), aliases, FakeGitOwner()
    )
    windows = map_session_trace(
        _trace("windows", cwd="c:/archive/atlas/nested"), (project,), aliases, FakeGitOwner()
    )

    assert (relative.project_id, relative.reason) == ("atlas", "alias")
    assert (windows.project_id, windows.reason) == ("atlas", "alias")


def test_child_without_direct_evidence_inherits_parent_project():
    mappings = merge_child_evidence(
        traces=(_trace("parent"), _trace("child", parent="parent")),
        mappings=(_mapping("parent", "alpha", "cwd"), _mapping("child", None, "unmapped")),
    )

    assert mappings[1].project_id == "alpha"
    assert mappings[1].reason == "parent-session"
    assert mappings[0].child_session_ids == ("child",)


def test_conflicting_direct_child_evidence_is_not_overridden_by_parent():
    mappings = merge_child_evidence(
        traces=(_trace("parent"), _trace("child", parent="parent")),
        mappings=(
            _mapping("parent", "alpha", "cwd"),
            _mapping("child", "beta", "changed-path"),
        ),
    )

    assert mappings[1].project_id == "beta"
    assert mappings[1].reason == "changed-path"


def test_ambiguous_direct_child_evidence_is_not_resolved_from_parent():
    mappings = merge_child_evidence(
        traces=(_trace("parent"), _trace("child", parent="parent")),
        mappings=(
            _mapping("parent", "alpha", "cwd"),
            _mapping("child", None, "ambiguous"),
        ),
    )

    assert mappings[1].project_id is None
    assert mappings[1].reason == "ambiguous"
