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
    assert trace.cwd == "/workspace/projects/beta"
    assert trace.changed_paths == (
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


def test_duplicate_session_ids_fail_closed_independently_of_input_order():
    traces = (
        _trace("duplicate"),
        _trace("duplicate"),
        _trace("child", parent="duplicate"),
    )
    mappings = (
        _mapping("duplicate", "alpha", "cwd"),
        _mapping("duplicate", "beta", "changed-path"),
        _mapping("child", None, "unmapped"),
    )

    first = merge_child_evidence(traces, mappings)
    second = merge_child_evidence(tuple(reversed(traces)), tuple(reversed(mappings)))

    assert [(item.project_id, item.reason, item.child_session_ids) for item in first] == [
        (None, "ambiguous", ()),
        (None, "ambiguous", ()),
        (None, "unmapped", ()),
    ]
    assert sorted((item.session_id, item.project_id, item.reason) for item in first) == sorted(
        (item.session_id, item.project_id, item.reason) for item in second
    )


def test_parent_cycle_preserves_direct_evidence_and_fails_unmapped_members_closed():
    traces = (_trace("a", parent="b"), _trace("b", parent="a"))
    mappings = (_mapping("a", "alpha", "cwd"), _mapping("b", None, "unmapped"))

    first = merge_child_evidence(traces, mappings)
    second = merge_child_evidence(tuple(reversed(traces)), tuple(reversed(mappings)))

    assert [(item.project_id, item.reason, item.child_session_ids) for item in first] == [
        ("alpha", "cwd", ()),
        (None, "ambiguous", ()),
    ]
    assert sorted((item.session_id, item.project_id, item.reason) for item in first) == sorted(
        (item.session_id, item.project_id, item.reason) for item in second
    )


def test_self_parent_cycle_is_ambiguous_without_a_child_link():
    mapping = merge_child_evidence(
        traces=(_trace("self", parent="self"),),
        mappings=(_mapping("self", None, "unmapped"),),
    )[0]

    assert (mapping.project_id, mapping.reason, mapping.child_session_ids) == (
        None,
        "ambiguous",
        (),
    )


def test_missing_parent_remains_unmapped_without_a_child_link():
    mapping = merge_child_evidence(
        traces=(_trace("child", parent="missing"),),
        mappings=(_mapping("child", None, "unmapped"),),
    )[0]

    assert (mapping.project_id, mapping.reason, mapping.child_session_ids) == (
        None,
        "unmapped",
        (),
    )


def test_custom_tool_call_extracts_only_allowlisted_wrapper_object_paths(tmp_path):
    session_path = tmp_path / "custom.jsonl"
    records = (
        {
            "type": "session_meta",
            "payload": {"id": "custom", "cwd": "/workspace/projects/alpha"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "ignore /private/prose.py"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "item": {
                    "type": "custom_tool_call",
                    "input": (
                        'await tools.exec_command({ workdir: "/workspace/projects/beta\\u002dwork", '
                        'path: "/workspace/projects/beta-work/src/app.py", '
                        'cmd: "printf \\\"/private/cmd.py\\\"" });'
                    ),
                }
            },
        },
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/beta-work"
    assert trace.changed_paths == ("/workspace/projects/beta-work/src/app.py",)
    assert "/private/prose.py" not in trace.changed_paths
    assert "/private/cmd.py" not in trace.changed_paths


def test_custom_tool_call_skips_dynamic_or_non_wrapper_input(tmp_path):
    session_path = tmp_path / "custom-invalid.jsonl"
    records = (
        {"type": "session_meta", "payload": {"id": "custom", "cwd": "/workspace/projects/alpha"}},
        {
            "type": "response_item",
            "payload": {
                "item": {
                    "type": "custom_tool_call",
                    "input": 'await tools.exec_command({ workdir: root + "/beta", path: dynamicPath, cmd: "/private/cmd.py" });',
                }
            },
        },
        {
            "type": "response_item",
            "payload": {
                "item": {
                    "type": "custom_tool_call",
                    "input": 'ordinary prose mentioning tools.exec_command({path: "/private/prose.py"})',
                }
            },
        },
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/alpha"
    assert trace.changed_paths == ()


def test_custom_tool_call_collects_ordered_promise_all_calls_from_const_assignment(tmp_path):
    session_path = tmp_path / "custom-promise-all.jsonl"
    source = "".join(
        (
            "const results = await Promise.all([",
            'tools.exec_command({ workdir: "/workspace/projects/beta", path: "src/first.py", cmd: "/private/cmd-first.py" }),',
            'tools.exec_command({ workdir: "/workspace/projects/gamma", path: "src/second.py", cmd: "/private/cmd-second.py" })',
            "]);",
        )
    )
    records = (
        {"type": "session_meta", "payload": {"id": "promise", "cwd": "/workspace/projects/alpha"}},
        {"type": "response_item", "payload": {"item": {"type": "custom_tool_call", "input": source}}},
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/gamma"
    assert trace.changed_paths == (
        "/workspace/projects/beta/src/first.py",
        "/workspace/projects/gamma/src/second.py",
    )
    assert "/private/cmd-first.py" not in trace.changed_paths
    assert "/private/cmd-second.py" not in trace.changed_paths


def test_custom_tool_call_rejects_incomplete_prose_and_deferred_calls(tmp_path):
    session_path = tmp_path / "custom-rejected.jsonl"
    sources = (
        'await tools.exec_command({ path: "/private/missing-paren.py" };',
        'please await tools.exec_command({ path: "/private/prose.py" });',
        'const quoted = "await tools.exec_command({ path: /private/quoted.py })";',
        '// await tools.exec_command({ path: "/private/comment.py" });',
        'function deferred() { await tools.exec_command({ path: "/private/function.py" }); }',
        'const callback = () => { await tools.exec_command({ path: "/private/callback.py" }); };',
    )
    records = [{"type": "session_meta", "payload": {"id": "rejected", "cwd": "/workspace/projects/alpha"}}]
    records.extend(
        {"type": "response_item", "payload": {"item": {"type": "custom_tool_call", "input": source}}}
        for source in sources
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/alpha"
    assert trace.changed_paths == ()


def test_custom_tool_call_keeps_completed_assignment_when_other_statement_is_invalid(tmp_path):
    session_path = tmp_path / "custom-statement-boundaries.jsonl"
    source = "".join(
        (
            'await tools.exec_command({ workdir: dynamicRoot, path: "/private/dynamic.py", cmd: "/private/cmd.py" });',
            'const result = await tools.exec_command({ workdir: "/workspace/projects/beta", path: "src/kept.py", cmd: "/private/cmd-kept.py" });',
            "text(result.output);",
        )
    )
    records = (
        {"type": "session_meta", "payload": {"id": "boundaries", "cwd": "/workspace/projects/alpha"}},
        {"type": "response_item", "payload": {"item": {"type": "custom_tool_call", "input": source}}},
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/beta"
    assert trace.changed_paths == ("/workspace/projects/beta/src/kept.py",)


def test_custom_tool_call_discards_prior_evidence_when_source_has_structural_delimiter_failure(tmp_path):
    valid = 'await tools.exec_command({ workdir: "/workspace/projects/beta", path: "src/valid.py" });'
    malformed_suffixes = {
        "mismatched-closer": ")",
        "unclosed-paren": "(",
        "unclosed-brace": "const x = {",
    }

    for name, suffix in malformed_suffixes.items():
        session_path = tmp_path / f"custom-{name}.jsonl"
        records = (
            {"type": "session_meta", "payload": {"id": name, "cwd": "/workspace/projects/alpha"}},
            {"type": "response_item", "payload": {"item": {"type": "custom_tool_call", "input": valid + suffix}}},
        )
        session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

        trace = index_session(session_path)

        assert trace.cwd == "/workspace/projects/alpha"
        assert trace.changed_paths == ()


def test_custom_tool_call_keeps_valid_evidence_before_complete_unsupported_statement(tmp_path):
    session_path = tmp_path / "custom-complete-unsupported.jsonl"
    source = "".join(
        (
            'await tools.exec_command({ workdir: "/workspace/projects/beta", path: "src/valid.py" });',
            "text(result.output);",
        )
    )
    records = (
        {"type": "session_meta", "payload": {"id": "complete", "cwd": "/workspace/projects/alpha"}},
        {"type": "response_item", "payload": {"item": {"type": "custom_tool_call", "input": source}}},
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/beta"
    assert trace.changed_paths == ("/workspace/projects/beta/src/valid.py",)


def test_apply_patch_extracts_add_update_delete_and_move_targets_only(tmp_path):
    session_path = tmp_path / "move.jsonl"
    patch = "\n".join(
        (
            "*** Update File: src/old.py",
            "*** Move to: src/new.py",
            "*** Add File: src/added.py",
            "*** Delete File: src/deleted.py",
            "+*** Update File: /private/patch-prose.py",
        )
    )
    records = (
        {"type": "session_meta", "payload": {"id": "move", "cwd": "/workspace/projects/alpha"}},
        {
            "type": "response_item",
            "payload": {
                "item": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "workdir": "/workspace/projects/beta",
                    "arguments": patch,
                }
            },
        },
    )
    session_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    trace = index_session(session_path)

    assert trace.cwd == "/workspace/projects/beta"
    assert trace.changed_paths == (
        "/workspace/projects/beta/src/old.py",
        "/workspace/projects/beta/src/new.py",
        "/workspace/projects/beta/src/added.py",
        "/workspace/projects/beta/src/deleted.py",
    )
