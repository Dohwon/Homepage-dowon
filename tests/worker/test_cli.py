import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import atlas_worker.cli as cli_module
from atlas_worker.cli import (
    EXIT_IO,
    EXIT_OK,
    EXIT_PRIVACY,
    EXIT_VALIDATION,
    build_parser,
    main,
)
from tests.worker.helpers import (
    invoke_cli_json,
    make_workspace_fixture,
    write_bundle_fixture,
    write_project_profile,
)


def _snapshot(root: Path) -> dict[str, tuple[str, bytes]]:
    snapshot = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path).encode("utf-8"))
        elif path.is_dir():
            snapshot[relative] = ("directory", b"")
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


def _write_session(path: Path, workspace: Path, raw_text: str = "TOP_SECRET rollback request") -> None:
    records = (
        {
            "type": "session_meta",
            "timestamp": "2026-08-24T10:00:00Z",
            "payload": {"id": "session-one", "cwd": str(workspace / "projects" / "alpha")},
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-24T10:01:00Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": raw_text}],
            },
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _reviewed_profile(project_id: str, lifecycle: str = "active") -> dict[str, object]:
    return {
        "id": project_id,
        "name": project_id.title(),
        "lifecycle": lifecycle,
        "publication": "private",
        "summary": f"{project_id.title()} reviewed profile",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
        },
    }


def test_parser_exposes_all_worker_commands_and_required_options(tmp_path):
    parser = build_parser()
    workspace = str(tmp_path)

    assert parser.parse_args(["discover", "--workspace", workspace]).command == "discover"
    assert parser.parse_args(
        ["bootstrap-profiles", "--workspace", workspace, "--dry-run"]
    ).dry_run
    assert parser.parse_args(["backfill", "--workspace", workspace, "--dry-run"]).dry_run
    assert parser.parse_args(["build", "--workspace", workspace, "--dry-run"]).dry_run
    assert parser.parse_args(["validate", "--fixture", workspace]).fixture == Path(workspace)
    assert parser.parse_args(["run", "--workspace", workspace, "--dry-run"]).dry_run


def test_discover_reports_active_and_finish_children_without_roots_or_aggregate(tmp_path):
    workspace = make_workspace_fixture(tmp_path)

    output = invoke_cli_json(["discover", "--workspace", str(workspace), "--format", "json"])

    assert [item["id"] for item in output["projects"]] == ["alpha", "beta"]
    assert [item["lifecycle"] for item in output["projects"]] == ["active", "finished"]
    assert all(
        set(item) == {"id", "name", "lifecycle", "publication", "relative_path", "aliases"}
        for item in output["projects"]
    )
    assert "finish" not in [item["id"] for item in output["projects"]]
    assert output["ambiguous"] == []
    assert str(workspace) not in json.dumps(output)


def test_discover_is_read_only(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    before = _snapshot(workspace)

    assert main(["discover", "--workspace", str(workspace)]) == EXIT_OK

    assert _snapshot(workspace) == before


def test_bootstrap_profiles_dry_run_reports_ambiguous_without_writes(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    ambiguous = workspace / "projects" / "gamma"
    ambiguous.mkdir()
    before = _snapshot(workspace)

    output = invoke_cli_json(
        ["bootstrap-profiles", "--workspace", str(workspace), "--dry-run"]
    )

    assert [item["id"] for item in output["ambiguous"]] == ["gamma"]
    assert output["written"] == []
    assert _snapshot(workspace) == before


def test_bootstrap_profiles_requires_reviewed_report_for_real_write(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    target = workspace / "projects" / "gamma"
    target.mkdir()

    code = main(["bootstrap-profiles", "--workspace", str(workspace)])

    assert code == EXIT_VALIDATION
    assert not (target / "project_memory" / "project-profile.yaml").exists()
    assert "traceback" not in capsys.readouterr().err.casefold()


def test_bootstrap_profiles_applies_schema_valid_reviewed_profiles_atomically(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    target = workspace / "projects" / "gamma"
    target.mkdir()
    report = tmp_path / "reviewed-profiles.json"
    report.write_text(json.dumps({"profiles": [_reviewed_profile("gamma")]}), encoding="utf-8")

    output = invoke_cli_json(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    profile = target / "project_memory" / "project-profile.yaml"
    assert output["written"] == ["projects/gamma/project_memory/project-profile.yaml"]
    assert profile.is_file()
    assert not tuple(profile.parent.glob(".*.tmp"))


def test_bootstrap_profiles_preflights_entire_report_before_any_write(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    gamma = workspace / "projects" / "gamma"
    delta = workspace / "projects" / "delta"
    gamma.mkdir()
    delta.mkdir()
    invalid = _reviewed_profile("delta")
    invalid["tags"] = {}
    report = tmp_path / "invalid-reviewed-profiles.json"
    report.write_text(
        json.dumps({"profiles": [_reviewed_profile("gamma"), invalid]}),
        encoding="utf-8",
    )

    code = main(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    assert code == EXIT_VALIDATION
    assert not (gamma / "project_memory" / "project-profile.yaml").exists()
    assert not (delta / "project_memory" / "project-profile.yaml").exists()
    assert "delta" not in capsys.readouterr().err


def test_backfill_dry_run_without_session_config_is_valid_zero_session_run(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    before = _snapshot(workspace)

    output = invoke_cli_json(["backfill", "--workspace", str(workspace), "--dry-run"])

    assert output["sessions"] == {"files": 0, "mapped_events": 0, "parse_errors": 0, "unmapped_events": 0}
    assert output["claim_counts"] == {}
    assert output["claims"] == []
    assert not output["cursor_written"]
    assert _snapshot(workspace) == before


def test_backfill_streams_explicit_sessions_and_reports_only_sanitized_claims(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    before = _snapshot(workspace)

    output = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )

    rendered = json.dumps(output)
    assert output["sessions"]["files"] == 1
    assert output["claim_counts"] == {"rollback": 1}
    assert output["claims"][0]["value"] == "rollback requested"
    assert "TOP_SECRET" not in rendered
    assert str(sessions) not in rendered
    assert "TOP_SECRET" not in capsys.readouterr().err
    assert _snapshot(workspace) == before


def test_backfill_reads_sessions_root_from_runtime_config_without_state_writes(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(yaml.safe_dump({"sessions_root": str(sessions)}), encoding="utf-8")
    before = _snapshot(workspace)

    output = invoke_cli_json(["backfill", "--workspace", str(workspace), "--dry-run"])

    assert output["sessions"]["files"] == 1
    assert output["claim_counts"] == {"rollback": 1}
    assert _snapshot(workspace) == before


def test_backfill_real_write_requires_reviewed_report(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)

    code = main(
        ["backfill", "--workspace", str(workspace), "--sessions-root", str(sessions)]
    )

    assert code == EXIT_VALIDATION
    assert not (workspace / ".knowledge-worker" / "session-cursor.json").exists()
    assert not (workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md").exists()


def test_backfill_applies_only_selected_current_sanitized_claims_and_cursor(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    dry = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )
    reviewed_claim = dict(dry["claims"][0])
    reviewed_claim["selected"] = True
    report = tmp_path / "reviewed-backfill.json"
    report.write_text(json.dumps({"claims": [reviewed_claim]}), encoding="utf-8")

    output = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    memory = workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md"
    assert output["applied"] == {"claims": 1, "files": 1, "projects": 1}
    assert output["cursor_written"]
    assert memory.is_file()
    assert "TOP_SECRET" not in memory.read_text(encoding="utf-8")
    assert (workspace / ".knowledge-worker" / "session-cursor.json").is_file()


def test_backfill_rejects_tampered_reviewed_claim_without_memory_or_cursor_write(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    dry = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )
    tampered = dict(dry["claims"][0])
    tampered["selected"] = True
    tampered["value"] = "RAW_SESSION_TEXT"
    report = tmp_path / "tampered-backfill.json"
    report.write_text(json.dumps({"claims": [tampered]}), encoding="utf-8")

    code = main(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    assert code == EXIT_VALIDATION
    assert "RAW_SESSION_TEXT" not in capsys.readouterr().err
    assert not (workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md").exists()
    assert not (workspace / ".knowledge-worker" / "session-cursor.json").exists()


def test_backfill_rejects_symlink_cursor_before_memory_write(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    dry = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )
    selected = dict(dry["claims"][0])
    selected["selected"] = True
    report = tmp_path / "reviewed-backfill.json"
    report.write_text(json.dumps({"claims": [selected]}), encoding="utf-8")
    outside = tmp_path / "outside-cursor.json"
    outside.write_text("{}\n", encoding="utf-8")
    cursor = workspace / ".knowledge-worker" / "session-cursor.json"
    cursor.parent.mkdir()
    cursor.symlink_to(outside)
    outside_before = outside.read_bytes()

    code = main(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    assert code == EXIT_VALIDATION
    assert outside.read_bytes() == outside_before
    assert not (workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md").exists()


def test_build_dry_run_omits_private_ambiguous_and_unprofiled_projects(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    private = workspace / "projects" / "private-project"
    excluded = workspace / "projects" / "excluded-project"
    unprofiled = workspace / "projects" / "unprofiled"
    private.mkdir()
    excluded.mkdir()
    unprofiled.mkdir()
    write_project_profile(
        private,
        id="private-project",
        name="Private Project",
        publication="private",
    )
    write_project_profile(
        excluded,
        id="excluded-project",
        name="Excluded Project",
        publication="excluded",
    )
    before = _snapshot(workspace)

    output = invoke_cli_json(["build", "--workspace", str(workspace), "--dry-run"])

    assert output["projects"] == ["alpha", "beta"]
    assert output["validated"]
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert _snapshot(workspace) == before
    assert "private-project" not in json.dumps(output)
    assert "excluded-project" not in json.dumps(output)
    assert "unprofiled" not in json.dumps(output)


def test_build_real_write_requires_explicit_runtime_alias_key(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)

    code = main(["build", "--workspace", str(workspace)])

    assert code == EXIT_VALIDATION
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert "traceback" not in capsys.readouterr().err.casefold()


def test_build_real_write_promotes_valid_public_profiles_and_direct_memory(tmp_path, monkeypatch):
    workspace = make_workspace_fixture(tmp_path)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", "approved-unit-test-key")

    output = invoke_cli_json(["build", "--workspace", str(workspace)])

    public = workspace / "portfolio-homepage" / "public-bundle"
    assert output["projects"] == ["alpha", "beta"]
    assert output["changed"]
    assert (public / "manifest.json").is_file()
    assert "Keep direct curated memory" in (
        public / "projects" / "alpha" / "decisions.md"
    ).read_text(encoding="utf-8")
    project = json.loads((public / "projects" / "alpha" / "project.json").read_text(encoding="utf-8"))
    assert project["aliases"] == []


def test_build_real_write_accepts_explicit_runtime_alias_key_file(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    key_path = tmp_path / "atlas-hmac.key"
    key_path.write_bytes(b"approved-key-file-material")
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(yaml.safe_dump({"hmac_key_path": str(key_path)}), encoding="utf-8")

    output = invoke_cli_json(["build", "--workspace", str(workspace)])

    assert output["changed"]
    assert key_path.read_text(encoding="utf-8") not in json.dumps(output)


def test_build_dry_run_blocks_encoded_route_without_leaking_value_or_writing(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    raw_value = "%252Ftmp/private-secret"
    alpha = workspace / "projects" / "alpha"
    write_project_profile(alpha, summary=f'<a href="{raw_value}">Alpha</a>')

    code = main(["build", "--workspace", str(workspace), "--dry-run"])

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert "absolute_path" in captured.err
    assert raw_value not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()


def test_validate_fixture_is_read_only_and_workspace_validation_uses_public_api(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture-bundle"
    write_bundle_fixture(fixture, version=None, summary="safe")
    before = _snapshot(fixture)
    monkeypatch.setattr(
        cli_module,
        "promote_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("validate must not promote")),
    )

    fixture_output = invoke_cli_json(["validate", "--fixture", str(fixture)])

    workspace = make_workspace_fixture(tmp_path / "nested")
    public = workspace / "portfolio-homepage" / "public-bundle"
    write_bundle_fixture(public, version=None, summary="safe")
    workspace_before = _snapshot(public)
    workspace_output = invoke_cli_json(["validate", "--workspace", str(workspace)])

    assert fixture_output["projects"] == ["alpha"]
    assert workspace_output["projects"] == ["alpha"]
    assert _snapshot(fixture) == before
    assert _snapshot(public) == workspace_before


def test_validate_invalid_bundle_returns_sanitized_validation_exit_without_writes(tmp_path, capsys):
    fixture = tmp_path / "invalid-bundle"
    write_bundle_fixture(fixture, version=None, summary="safe")
    manifest = fixture / "manifest.json"
    manifest.write_text('{"private":"RAW_SESSION_TEXT"}', encoding="utf-8")
    before = _snapshot(fixture)

    code = main(["validate", "--fixture", str(fixture)])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert "RAW_SESSION_TEXT" not in captured.err
    assert str(fixture) not in captured.err
    assert "traceback" not in captured.err.casefold()
    assert _snapshot(fixture) == before


def test_run_dry_run_with_sessions_changes_no_durable_workspace_tree(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = workspace / "runtime-input" / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    before = _snapshot(workspace)

    output = invoke_cli_json(
        [
            "run",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )

    assert output["discovery"]["projects"] == 2
    assert output["backfill"]["claim_counts"] == {"rollback": 1}
    assert output["build"]["projects"] == ["alpha", "beta"]
    assert output["validation"]["valid"]
    assert _snapshot(workspace) == before
    assert not (workspace / ".knowledge-worker" / "session-cursor.json").exists()
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert str(workspace) not in json.dumps(output)


def test_run_non_dry_key_guard_precedes_reviewed_backfill_writes(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "one.jsonl", workspace)
    dry = invoke_cli_json(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )
    selected = dict(dry["claims"][0])
    selected["selected"] = True
    report = tmp_path / "reviewed-backfill.json"
    report.write_text(json.dumps({"claims": [selected]}), encoding="utf-8")

    code = main(
        [
            "run",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    assert code == EXIT_VALIDATION
    assert not (workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md").exists()
    assert not (workspace / ".knowledge-worker" / "session-cursor.json").exists()
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()


def test_run_dry_run_missing_session_config_is_valid_and_invalid_profile_is_validation_error(
    tmp_path, capsys
):
    workspace = make_workspace_fixture(tmp_path)

    assert main(["run", "--workspace", str(workspace), "--dry-run"]) == EXIT_OK

    alpha = workspace / "projects" / "alpha"
    write_project_profile(alpha, tags={}, summary="RAW_PROFILE_VALUE")
    code = main(["run", "--workspace", str(workspace), "--dry-run"])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert "RAW_PROFILE_VALUE" not in captured.err
    assert str(alpha) not in captured.err


def test_missing_explicit_review_report_returns_sanitized_io_exit(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    missing = tmp_path / "private" / "missing-reviewed-report.json"

    code = main(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(missing),
        ]
    )

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert str(missing) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_parser_errors_return_validation_exit_without_system_exit(capsys):
    code = main(["validate"])

    assert code == EXIT_VALIDATION
    assert "traceback" not in capsys.readouterr().err.casefold()


def test_project_atlas_script_adds_repository_root_and_returns_main_code(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    script = Path(__file__).parents[2] / "scripts" / "project_atlas.py"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "discover",
            "--workspace",
            str(workspace),
            "--format",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_OK
    assert json.loads(result.stdout)["ambiguous"] == []
    assert str(workspace) not in result.stdout
    assert result.stderr == ""
