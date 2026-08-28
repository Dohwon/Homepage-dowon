import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import atlas_worker.bundle as bundle_module
import atlas_worker.cli as cli_module
import atlas_worker.fs_safety as fs_safety_module
from atlas_worker.cli import (
    EXIT_IO,
    EXIT_OK,
    EXIT_PRIVACY,
    EXIT_VALIDATION,
    build_parser,
    main,
)
from atlas_worker.models import SessionEvent, SessionTrace
from tests.worker.helpers import (
    invoke_cli_json,
    make_workspace_fixture,
    refresh_fixture_manifest,
    write_bundle_fixture,
    write_project_profile,
)


PRODUCTION_ALIAS_KEY = "0123456789abcdef0123456789abcdef"


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


def _write_session(
    path: Path,
    workspace: Path,
    raw_text: str = "TOP_SECRET rollback request",
    project_relative_path: str = "projects/alpha",
    historical_cwd: str | None = None,
) -> None:
    records = (
        {
            "type": "session_meta",
            "timestamp": "2026-08-24T10:00:00Z",
            "payload": {
                "id": f"session-{path.stem}",
                "cwd": historical_cwd or str(workspace / project_relative_path),
            },
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


def _write_revision_session(path: Path, workspace: Path) -> None:
    records = (
        {
            "type": "session_meta",
            "timestamp": "2026-08-24T10:00:00Z",
            "payload": {
                "id": f"session-{path.stem}",
                "cwd": str(workspace / "projects" / "alpha"),
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-24T10:01:00Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "다시 수정해"}],
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-08-24T10:02:00Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "수정 완료"}],
            },
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


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


def _write_ready_article(
    workspace: Path,
    readiness: str = "ready",
    *,
    project_id: str = "alpha",
    article_title: str = "Routing record",
    evidence_id: str | None = None,
) -> None:
    evidence_id = evidence_id or f"{project_id}-proof"
    source = workspace / "projects" / project_id / "project_memory" / "project-atlas"
    source.mkdir(parents=True)
    (source / "article.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": project_id,
                "title": article_title,
                "summary": "Public routing decision",
                "readiness": readiness,
                "sections": [{
                    "id": "routing",
                    "title": "Routing",
                    "section_type": "decision",
                    "body": "The public routing contract is deterministic.",
                    "evidence_ids": [evidence_id],
                }],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (source / "evidence.yaml").write_text(
        yaml.safe_dump([{
            "id": evidence_id,
            "project_id": project_id,
            "label": "Public routing contract",
            "source_type": "test",
            "source_locator": "/private/atlas/test.py:1",
            "observed_at": "2026-08-24T10:00:00Z",
            "privacy_class": "private",
            "content_hash": "a" * 64,
        }], sort_keys=False),
        encoding="utf-8",
    )


def test_build_publishes_audited_structured_article_and_section_search(tmp_path, monkeypatch):
    workspace = make_workspace_fixture(tmp_path)
    _write_ready_article(workspace)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)

    output = invoke_cli_json(["build", "--workspace", str(workspace)])

    public = workspace / "portfolio-homepage" / "public-bundle"
    article = json.loads((public / "projects" / "alpha" / "article.json").read_text(encoding="utf-8"))
    evidence = json.loads((public / "projects" / "alpha" / "evidence.json").read_text(encoding="utf-8"))
    search = json.loads((public / "search-index.json").read_text(encoding="utf-8"))
    assert output["validated"]
    assert article["sections"][0]["id"] == "routing"
    assert set(evidence[0]) == {"id", "label", "source_type", "observed_at"}
    assert {item["id"] for item in search} >= {"project:alpha", "article:alpha:routing"}
    assert "/private/atlas" not in json.dumps({"article": article, "evidence": evidence, "search": search})


def test_build_rejects_curated_article_that_is_not_ready_before_promotion(tmp_path, monkeypatch, capsys):
    workspace = make_workspace_fixture(tmp_path)
    _write_ready_article(workspace, readiness="review-required")
    public = workspace / "portfolio-homepage" / "public-bundle"
    write_bundle_fixture(public, version=None, summary="last good")
    before = _snapshot(public)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)

    code = main(["build", "--workspace", str(workspace)])

    assert code == EXIT_VALIDATION
    assert _snapshot(public) == before
    assert json.loads(capsys.readouterr().err) == {
        "error": {"category": "config", "pointer": "/project-atlas/readiness"}
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
    assert parser.parse_args(
        ["audit-content", "--workspace", workspace, "--format", "json"]
    ).project is None
    assert parser.parse_args(
        ["audit-content", "--workspace", workspace, "--project", "alpha", "--format", "json"]
    ).project == "alpha"


def test_audit_content_emits_relative_manifest_summary_without_private_paths(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    project = workspace / "projects" / "alpha"
    (project / "src").mkdir()
    (project / "src/main.py").write_text("print('audit')\n", encoding="utf-8")

    output = invoke_cli_json(
        ["audit-content", "--workspace", str(workspace), "--project", "alpha", "--format", "json"]
    )

    assert output["project_id"] == "alpha"
    assert output["files"]["count"] >= 2
    assert len(output["content_hash"]) == 64
    assert str(workspace) not in json.dumps(output)
    assert "/git/" not in json.dumps(output)


def test_audit_content_without_project_emits_sanitized_manifest_and_content_audit(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    _write_ready_article(workspace)

    alpha = workspace / "projects" / "alpha"
    (alpha / "src").mkdir()
    (alpha / "src/main.py").write_text("print('alpha')\n", encoding="utf-8")

    beta = workspace / "projects" / "finish" / "beta"
    (beta / "lib").mkdir()
    (beta / "lib/index.js").write_text("console.log('beta');\n", encoding="utf-8")

    zeta = workspace / "projects" / "zeta"
    zeta.mkdir()
    write_project_profile(zeta, id="zeta", name="Zeta", publication="public")
    (zeta / "docs").mkdir()
    (zeta / "docs/notes.md").write_text("zeta notes\n", encoding="utf-8")

    private = workspace / "projects" / "private-only"
    private.mkdir()
    write_project_profile(private, id="private-only", name="Private Only", publication="private")
    (private / "notes.md").write_text("private evidence\n", encoding="utf-8")

    excluded = workspace / "projects" / "excluded-one"
    excluded.mkdir()
    write_project_profile(excluded, id="excluded-one", name="Excluded One", publication="excluded")
    (excluded / "notes.md").write_text("excluded evidence\n", encoding="utf-8")

    ambiguous = workspace / "projects" / "unreviewed"
    ambiguous.mkdir()
    (ambiguous / ".git").write_text("gitdir: /private/ambiguous\n", encoding="utf-8")
    (ambiguous / "notes.md").write_text("ambiguous evidence\n", encoding="utf-8")

    output = invoke_cli_json(["audit-content", "--workspace", str(workspace), "--format", "json"])

    items = output["projects"]
    project_ids = [item["project_id"] for item in items]
    rendered = json.dumps(output)
    assert project_ids == ["alpha", "beta", "zeta"]
    assert len(project_ids) == len(set(project_ids))
    alpha_item = items[0]
    beta_item = items[1]
    assert set(alpha_item) == {"project_id", "source_manifest", "content_audit"}
    assert alpha_item["source_manifest"] == {
        "status": "ready",
        "summary": {"files": {"count": 5, "by_class": {"project_memory": 4, "source": 1}}, "content_hash": alpha_item["source_manifest"]["summary"]["content_hash"]},
        "finding_codes": [],
    }
    assert len(alpha_item["source_manifest"]["summary"]["content_hash"]) == 64
    assert alpha_item["content_audit"] == {
        "readiness": "ready",
        "evidence_counts": {"context": 0, "contradicts": 0, "supports": 1, "total": 1},
        "session_counts": {"ambiguous": 0, "mapped": 0, "total": 0, "unmapped": 0},
        "finding_codes": [],
    }
    assert beta_item["source_manifest"]["status"] == "ready"
    assert beta_item["content_audit"]["readiness"] == "insufficient-evidence"
    assert beta_item["content_audit"]["finding_codes"] == ["missing-curated-article"]
    assert str(workspace) not in rendered
    assert "/git/" not in rendered
    assert "gitdir" not in rendered
    assert "/private/ambiguous" not in rendered
    assert "private-only" not in project_ids
    assert "excluded-one" not in project_ids
    assert "unreviewed" not in project_ids


def test_audit_content_without_project_keeps_broken_public_project_once_and_continues(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    _write_ready_article(workspace)

    alpha = workspace / "projects" / "alpha"
    (alpha / "src").mkdir()
    (alpha / "src/main.py").write_text("print('alpha')\n", encoding="utf-8")

    broken = workspace / "projects" / "gamma"
    broken.mkdir()
    write_project_profile(broken, id="gamma", name="Gamma", publication="public")
    (broken / "keep.txt").write_text("gamma\n", encoding="utf-8")
    (broken / "broken-link").symlink_to("/private/symlink-target")

    zeta = workspace / "projects" / "zeta"
    zeta.mkdir()
    write_project_profile(zeta, id="zeta", name="Zeta", publication="public")
    (zeta / "src").mkdir()
    (zeta / "src/main.py").write_text("print('zeta')\n", encoding="utf-8")
    _write_ready_article(workspace, project_id="zeta", article_title="Zeta record")

    output = invoke_cli_json(["audit-content", "--workspace", str(workspace), "--format", "json"])

    items = output["projects"]
    project_ids = [item["project_id"] for item in items]
    broken_item = next(item for item in items if item["project_id"] == "gamma")
    rendered = json.dumps(output)
    assert project_ids == ["alpha", "beta", "gamma", "zeta"]
    assert project_ids.count("gamma") == 1
    assert project_ids[-1] == "zeta"
    assert broken_item == {
        "project_id": "gamma",
        "source_manifest": {
            "status": "review-required",
            "summary": None,
            "finding_codes": ["source-manifest-error"],
        },
        "content_audit": {
            "readiness": "review-required",
            "evidence_counts": {"context": 0, "contradicts": 0, "supports": 0, "total": 0},
            "session_counts": {"ambiguous": 0, "mapped": 0, "total": 0, "unmapped": 0},
            "finding_codes": ["source-manifest-error"],
        },
    }
    assert next(item for item in items if item["project_id"] == "zeta")["content_audit"]["readiness"] == "ready"
    assert str(workspace) not in rendered
    assert "/private/symlink-target" not in rendered
    assert "broken-link" not in rendered


def test_audit_content_rejects_unknown_project_as_validation_error(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)

    code = main(
        ["audit-content", "--workspace", str(workspace), "--project", "missing", "--format", "json"]
    )

    assert code == EXIT_VALIDATION
    assert json.loads(capsys.readouterr().err) == {
        "error": {"category": "config", "pointer": "/project"}
    }


def test_audit_content_allows_ambiguous_private_project_without_path_or_git_leak(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    private = workspace / "projects" / "unreviewed"
    private.mkdir()
    (private / ".git").write_text("gitdir: /private/audit-source\n", encoding="utf-8")
    (private / "notes.md").write_text("local evidence\n", encoding="utf-8")

    output = invoke_cli_json(
        [
            "audit-content",
            "--workspace",
            str(workspace),
            "--project",
            "unreviewed",
            "--format",
            "json",
        ]
    )

    rendered = json.dumps(output)
    assert output["project_id"] == "unreviewed"
    assert output["files"] == {"count": 1, "by_class": {"source": 1}}
    assert len(output["content_hash"]) == 64
    assert str(workspace) not in rendered
    assert "gitdir" not in rendered
    assert "/private/audit-source" not in rendered


def test_operator_readme_documents_atlas_setup_key_and_recovery_contracts():
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")

    for required in (
        "Python 3.10+",
        "python3 -m venv .venv",
        "requirements-atlas.txt",
        "32 bytes",
        "chmod 600",
        "same filesystem",
        ".public-bundle.previous",
        ".public-bundle.recovery",
        "validate --fixture",
        "category\":\"io",
    ):
        assert required in readme


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


def test_private_symlink_candidate_remains_discoverable_but_never_publishes(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    outside = workspace / "private-linked-source"
    outside.mkdir()
    linked = workspace / "projects" / "private-link"
    linked.symlink_to(outside, target_is_directory=True)
    before = _snapshot(workspace)

    discovery = invoke_cli_json(["discover", "--workspace", str(workspace)])
    run = invoke_cli_json(["run", "--workspace", str(workspace), "--dry-run"])

    private_id = "private-link"
    assert private_id in [project["id"] for project in discovery["projects"]]
    assert private_id in discovery["ambiguous"]
    assert private_id not in run["build"]["projects"]
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


def test_registered_notebook_sidecar_bootstrap_update_and_build_lifecycle(
    tmp_path, monkeypatch
):
    workspace = make_workspace_fixture(tmp_path)
    projects = workspace / "projects"
    asset = projects / "analysis_notebook.ipynb"
    asset.write_text('{"cells": []}\n', encoding="utf-8")
    ignored = projects / "ignored_notebook.ipynb"
    ignored.write_text('{"cells": []}\n', encoding="utf-8")
    ignored_sidecar = projects / "ignored_notebook.ipynb.project-profile.yaml"
    ignored_sidecar.write_text(
        yaml.safe_dump(_reviewed_profile("ignored-notebook")), encoding="utf-8"
    )
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(
        yaml.safe_dump({"registered_assets": ["projects/analysis_notebook.ipynb"]}),
        encoding="utf-8",
    )
    report = tmp_path / "asset-profile.json"
    private_profile = _reviewed_profile("analysis-notebook")
    report.write_text(json.dumps({"profiles": [private_profile]}), encoding="utf-8")

    initial = invoke_cli_json(["discover", "--workspace", str(workspace)])
    created = invoke_cli_json(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(report),
        ]
    )
    sidecar = projects / "analysis_notebook.ipynb.project-profile.yaml"
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
    private_build = invoke_cli_json(["build", "--workspace", str(workspace)])

    assert "analysis-notebook" in initial["ambiguous"]
    assert created["written"] == [
        "projects/analysis_notebook.ipynb.project-profile.yaml"
    ]
    assert sidecar.is_file()
    assert "analysis-notebook" not in private_build["projects"]
    assert "ignored-notebook" not in [item["id"] for item in initial["projects"]]

    public_profile = dict(private_profile)
    public_profile["publication"] = "public"
    public_profile["summary"] = "Reviewed public notebook"
    report.write_text(json.dumps({"profiles": [public_profile]}), encoding="utf-8")
    updated = invoke_cli_json(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(report),
        ]
    )
    public_build = invoke_cli_json(["build", "--workspace", str(workspace)])
    rerun = invoke_cli_json(["build", "--workspace", str(workspace)])

    assert updated["written"] == [
        "projects/analysis_notebook.ipynb.project-profile.yaml"
    ]
    assert "analysis-notebook" in public_build["projects"]
    assert (
        workspace
        / "portfolio-homepage"
        / "public-bundle"
        / "projects"
        / "analysis-notebook"
        / "project.json"
    ).is_file()
    assert not rerun["changed"]


def test_registered_asset_source_denylist_fails_before_discovery_output(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    asset = workspace / "projects" / "logs" / "analysis.ipynb"
    asset.parent.mkdir()
    asset.write_text('{"cells": []}\n', encoding="utf-8")
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(
        yaml.safe_dump({"registered_assets": ["projects/logs/analysis.ipynb"]}),
        encoding="utf-8",
    )

    code = main(["discover", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert json.loads(captured.err) == {
        "error": {"category": "denied_source", "pointer": "$"}
    }
    assert str(workspace) not in captured.err


def test_standalone_bootstrap_rechecks_asset_no_follow_before_sidecar_write(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)
    asset = workspace / "projects" / "analysis.ipynb"
    asset.write_text('{"cells": []}\n', encoding="utf-8")
    outside = tmp_path / "outside.ipynb"
    outside.write_text("outside stays intact\n", encoding="utf-8")
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(
        yaml.safe_dump({"registered_assets": ["projects/analysis.ipynb"]}),
        encoding="utf-8",
    )
    report = tmp_path / "asset-profile.json"
    report.write_text(
        json.dumps({"profiles": [_reviewed_profile("analysis")]}), encoding="utf-8"
    )
    real_load = cli_module._load_reviewed_profiles

    def swap_asset_after_discovery(path):
        profiles = real_load(path)
        asset.unlink()
        asset.symlink_to(outside)
        return profiles

    monkeypatch.setattr(cli_module, "_load_reviewed_profiles", swap_asset_after_discovery)

    code = main(
        [
            "bootstrap-profiles",
            "--workspace",
            str(workspace),
            "--apply-reviewed-report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert not (workspace / "projects" / "analysis.ipynb.project-profile.yaml").exists()
    assert outside.read_text(encoding="utf-8") == "outside stays intact\n"
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_cli_backfill_maps_discovered_relative_profile_aliases_on_posix_and_windows(
    tmp_path,
):
    workspace = make_workspace_fixture(tmp_path)
    profile_path = (
        workspace / "projects" / "alpha" / "project_memory" / "project-profile.yaml"
    )
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["aliases"] = ["projects/old-alpha"]
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    sessions = tmp_path / "sessions"
    _write_session(
        sessions / "posix.jsonl",
        workspace,
        raw_text="We adopted X for the architecture.",
        historical_cwd="/archive/codex/projects/old-alpha/nested",
    )
    _write_session(
        sessions / "windows.jsonl",
        workspace,
        raw_text="We adopted X for the architecture.",
        historical_cwd=r"C:\Archive\Codex\projects\old-alpha\nested",
    )

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

    assert output["sessions"] == {
        "files": 2,
        "mapped_events": 4,
        "parse_errors": 0,
        "unmapped_events": 0,
        "parent_sessions": 0,
        "child_sessions": 0,
        "mapped_by_reason": {"alias": 2},
        "ambiguous_sessions": 0,
    }
    assert len(output["claims"]) == 2
    assert {claim["project_id"] for claim in output["claims"]} == {"alpha"}


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


def test_bootstrap_profiles_rolls_back_entire_report_on_second_profile_failure(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)
    gamma = workspace / "projects" / "gamma"
    delta = workspace / "projects" / "delta"
    gamma.mkdir()
    delta.mkdir()
    report = tmp_path / "reviewed-profiles.json"
    report.write_text(
        json.dumps(
            {"profiles": [_reviewed_profile("gamma"), _reviewed_profile("delta")]}
        ),
        encoding="utf-8",
    )
    before = _snapshot(workspace)
    real_replace = os.replace
    profile_replacements = 0

    def fail_second_profile(source, destination):
        nonlocal profile_replacements
        if Path(destination).name == "project-profile.yaml":
            profile_replacements += 1
            if profile_replacements == 2:
                raise OSError("injected second profile failure")
        return real_replace(source, destination)

    monkeypatch.setattr(
        fs_safety_module,
        "_replace_file",
        fail_second_profile,
        raising=False,
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

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert profile_replacements == 2
    assert _snapshot(workspace) == before
    assert "injected" not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_backfill_dry_run_without_session_config_is_valid_zero_session_run(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    before = _snapshot(workspace)

    output = invoke_cli_json(["backfill", "--workspace", str(workspace), "--dry-run"])

    assert output["sessions"] == {
        "files": 0,
        "mapped_events": 0,
        "parse_errors": 0,
        "unmapped_events": 0,
        "parent_sessions": 0,
        "child_sessions": 0,
        "mapped_by_reason": {},
        "ambiguous_sessions": 0,
    }
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
    assert "session-one" not in rendered
    assert str(sessions) not in rendered
    assert "TOP_SECRET" not in capsys.readouterr().err
    assert _snapshot(workspace) == before


def test_backfill_indexes_and_maps_each_session_once(tmp_path, monkeypatch):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    session_path = sessions / "one.jsonl"
    session_path.parent.mkdir()
    session_path.write_text("placeholder\n", encoding="utf-8")
    indexed = 0
    mapped = 0

    def one_pass_index(path):
        nonlocal indexed
        assert path == session_path
        indexed += 1
        if indexed > 1:
            raise AssertionError("session source was indexed more than once")
        events = tuple(
            SessionEvent(
                session_id="session-alpha",
                timestamp="2026-08-24T10:00:00Z",
                cwd=str(workspace / "projects" / "alpha"),
                role=role,
                text=content,
            )
            for role, content in (
                ("user", "테스트 실패"),
                ("assistant", "테스트 통과"),
            )
        )
        return SessionTrace(
            session_id="session-alpha",
            parent_session_id="",
            cwd=str(workspace / "projects" / "alpha"),
            changed_paths=(),
            git_common_dirs=(),
            events=events,
        )

    def counting_map(*args, **kwargs):
        nonlocal mapped
        mapped += 1
        return real_map(*args, **kwargs)

    current_cli_module = importlib.import_module("atlas_worker.cli")
    real_map = current_cli_module.map_session_trace
    monkeypatch.setattr(current_cli_module, "index_session", one_pass_index)
    monkeypatch.setattr(current_cli_module, "map_session_trace", counting_map)

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

    assert indexed == 1
    assert mapped == 1
    assert output["sessions"]["mapped_events"] == 2
    assert output["sessions"]["mapped_by_reason"] == {"cwd": 1}
    assert [
        (claim["project_id"], claim["claim_type"])
        for claim in output["claims"]
    ] == [("alpha", "failure")]


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


def test_backfill_rejects_symlinked_memory_target_before_outside_or_cursor_write(tmp_path, capsys):
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
    outside = tmp_path / "outside-rollbacks.md"
    outside.write_text("## Rollbacks\n\n- outside bytes\n", encoding="utf-8")
    target = workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md"
    target.symlink_to(outside)
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

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert outside.read_bytes() == outside_before
    assert target.is_symlink()
    assert not (workspace / ".knowledge-worker" / "session-cursor.json").exists()
    assert "outside bytes" not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_backfill_rolls_back_entire_report_on_second_memory_failure(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(sessions / "alpha.jsonl", workspace)
    _write_session(
        sessions / "beta.jsonl",
        workspace,
        project_relative_path="projects/finish/beta",
    )
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
    selected = []
    for claim in dry["claims"]:
        record = dict(claim)
        record["selected"] = True
        selected.append(record)
    assert [record["project_id"] for record in selected] == ["alpha", "beta"]
    report = tmp_path / "reviewed-backfill.json"
    report.write_text(json.dumps({"claims": selected}), encoding="utf-8")
    for relative in (
        "projects/alpha/project_memory/rollbacks.md",
        "projects/finish/beta/project_memory/rollbacks.md",
    ):
        target = workspace / relative
        target.write_text("## Rollbacks\n\n- original bytes\n", encoding="utf-8")
    before = _snapshot(workspace)
    real_replace = os.replace
    memory_replacements = 0

    def fail_second_memory(source, destination):
        nonlocal memory_replacements
        if Path(destination).name == "rollbacks.md":
            memory_replacements += 1
            if memory_replacements == 2:
                raise OSError("injected second memory failure")
        return real_replace(source, destination)

    monkeypatch.setattr(
        fs_safety_module,
        "_replace_file",
        fail_second_memory,
        raising=False,
    )

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

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert memory_replacements >= 3
    assert _snapshot(workspace) == before
    assert "injected" not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_backfill_rolls_back_memory_when_cursor_commit_fails(tmp_path, monkeypatch, capsys):
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
    memory = workspace / "projects" / "alpha" / "project_memory" / "rollbacks.md"
    memory.write_text("## Rollbacks\n\n- original bytes\n", encoding="utf-8")
    cursor = workspace / ".knowledge-worker" / "session-cursor.json"
    cursor.parent.mkdir()
    cursor.write_text("{}\n", encoding="utf-8")
    before = _snapshot(workspace)
    real_replace = os.replace
    cursor_failures = 0

    def fail_cursor(source, destination):
        nonlocal cursor_failures
        if Path(destination).name == "session-cursor.json" and cursor_failures == 0:
            cursor_failures += 1
            raise OSError("injected cursor failure")
        return real_replace(source, destination)

    monkeypatch.setattr(
        fs_safety_module,
        "_replace_file",
        fail_cursor,
        raising=False,
    )

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

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert cursor_failures == 1
    assert _snapshot(workspace) == before
    assert "injected" not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


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


def test_build_real_write_promotes_valid_public_profiles_without_unstructured_memory(tmp_path, monkeypatch):
    workspace = make_workspace_fixture(tmp_path)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)

    output = invoke_cli_json(["build", "--workspace", str(workspace)])

    public = workspace / "portfolio-homepage" / "public-bundle"
    assert output["projects"] == ["alpha", "beta"]
    assert output["changed"]
    assert (public / "manifest.json").is_file()
    assert not (public / "projects" / "alpha" / "decisions.md").exists()
    project = json.loads((public / "projects" / "alpha" / "project.json").read_text(encoding="utf-8"))
    assert project["aliases"] == []


def test_build_real_write_accepts_explicit_runtime_alias_key_file(tmp_path):
    workspace = make_workspace_fixture(tmp_path)
    key_path = tmp_path / "atlas-hmac.key"
    key_path.write_bytes(PRODUCTION_ALIAS_KEY.encode("utf-8") + b"\n")
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


def test_build_dry_run_blocks_encoded_unsafe_scheme_without_leak_or_write(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    raw_value = "%256A%2561vascript%253Aprivate-call"
    alpha = workspace / "projects" / "alpha"
    write_project_profile(alpha, summary=f'<a href="{raw_value}">Alpha</a>')
    before = _snapshot(workspace)

    code = main(["build", "--workspace", str(workspace), "--dry-run"])

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert json.loads(captured.err) == {
        "error": {"category": "absolute_path", "pointer": "$"}
    }
    assert raw_value not in captured.err
    assert str(workspace) not in captured.err
    assert _snapshot(workspace) == before
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()


def test_build_rejects_unsafe_scheme_and_preserves_last_good_bundle(tmp_path, monkeypatch, capsys):
    workspace = make_workspace_fixture(tmp_path)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
    public = workspace / "portfolio-homepage" / "public-bundle"
    write_bundle_fixture(public, version=None, summary="last good")
    public_before = _snapshot(public)
    raw_value = "blob%3Ahttps%3A%2F%2Fprivate.example/identifier"
    write_project_profile(
        workspace / "projects" / "alpha",
        summary=f'<a href="{raw_value}">Alpha</a>',
    )

    code = main(["build", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert json.loads(captured.err) == {
        "error": {"category": "absolute_path", "pointer": "$"}
    }
    assert raw_value not in captured.err
    assert _snapshot(public) == public_before


@pytest.mark.parametrize("source_kind", ("project-root", "profile", "memory"))
@pytest.mark.parametrize("dry_run", (True, False))
def test_build_rejects_symlinked_public_sources_before_candidate_or_promotion(
    tmp_path, monkeypatch, capsys, source_kind, dry_run
):
    workspace = make_workspace_fixture(tmp_path)
    alpha = workspace / "projects" / "alpha"
    outside: Path
    if source_kind == "project-root":
        outside = workspace / "outside-alpha-project"
        alpha.rename(outside)
        alpha.symlink_to(outside, target_is_directory=True)
    elif source_kind == "profile":
        profile = alpha / "project_memory" / "project-profile.yaml"
        outside = tmp_path / "outside-profile.yaml"
        profile.replace(outside)
        profile.symlink_to(outside)
    else:
        memory = alpha / "project_memory" / "decisions.md"
        outside = tmp_path / "outside-decisions.md"
        memory.replace(outside)
        memory.symlink_to(outside)
    outside_before = _snapshot(outside) if outside.is_dir() else outside.read_bytes()
    public = workspace / "portfolio-homepage" / "public-bundle"
    if not dry_run:
        monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
        write_bundle_fixture(public, version=None, summary="last good")
        public_before = _snapshot(public)

    arguments = ["build", "--workspace", str(workspace)]
    if dry_run:
        arguments.append("--dry-run")
    code = main(arguments)

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert set(json.loads(captured.err)["error"]) == {"category", "pointer"}
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()
    assert (_snapshot(outside) if outside.is_dir() else outside.read_bytes()) == outside_before
    if dry_run:
        assert not public.exists()
    else:
        assert _snapshot(public) == public_before
    assert not tuple((workspace / "portfolio-homepage").glob(".project-atlas-staging-*"))


def test_build_rejects_denied_curated_source_parts_before_candidate(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    denied = workspace / "projects" / "logs"
    denied.mkdir()
    write_project_profile(denied, id="logs", name="Logs", publication="public")

    code = main(["build", "--workspace", str(workspace), "--dry-run"])

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert json.loads(captured.err) == {
        "error": {"category": "denied_source", "pointer": "$"}
    }
    assert str(workspace) not in captured.err
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert not tuple((workspace / "portfolio-homepage").glob(".project-atlas-staging-*"))


@pytest.mark.parametrize(
    "runtime_payload",
    (
        [],
        {"registered_assets": {}},
        {"sessions_root": []},
        {"sessions": "not-a-container"},
        {"sessions": []},
        {"sessions": {"root": []}},
        {"aliases_file": []},
        {"service_root": []},
        {"alias_key_file": []},
        {"hmac_key_path": {}},
    ),
)
def test_runtime_config_type_matrix_returns_sanitized_config_exit(
    tmp_path, capsys, runtime_payload
):
    workspace = make_workspace_fixture(tmp_path)
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(yaml.safe_dump(runtime_payload), encoding="utf-8")

    code = main(["discover", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert set(json.loads(captured.err)["error"]) == {"category", "pointer"}
    assert json.loads(captured.err)["error"]["category"] == "config"
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


@pytest.mark.parametrize(
    "aliases_payload",
    (
        {"aliases": []},
        {"aliases": {"alias": ["alpha"]}},
        {"aliases": {1: "alpha"}},
    ),
)
def test_malformed_aliases_return_sanitized_config_exit(tmp_path, capsys, aliases_payload):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text(yaml.safe_dump(aliases_payload), encoding="utf-8")
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(yaml.safe_dump({"aliases_file": str(aliases)}), encoding="utf-8")

    code = main(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert set(json.loads(captured.err)["error"]) == {"category", "pointer"}
    assert json.loads(captured.err)["error"]["category"] == "config"
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


def test_malformed_alias_yaml_returns_sanitized_config_exit(tmp_path, capsys):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("aliases: [unterminated", encoding="utf-8")
    runtime = workspace / ".knowledge-worker" / "config.yaml"
    runtime.parent.mkdir()
    runtime.write_text(yaml.safe_dump({"aliases_file": str(aliases)}), encoding="utf-8")

    code = main(
        [
            "backfill",
            "--workspace",
            str(workspace),
            "--sessions-root",
            str(sessions),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert json.loads(captured.err) == {
        "error": {"category": "config", "pointer": "/aliases"}
    }
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()


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


@pytest.mark.parametrize("mutation", ("dangling", "six-neighbors"))
def test_cli_validate_rejects_rehashed_cross_graph_contract_violations(
    tmp_path, capsys, mutation
):
    fixture = tmp_path / "malformed-graph"
    project_ids = tuple(f"project-{index}" for index in range(7))
    write_bundle_fixture(fixture, None, "safe", project_ids=project_ids)
    edges_path = fixture / "graph" / "edges.json"
    edges = json.loads(edges_path.read_text(encoding="utf-8"))
    if mutation == "dangling":
        edges.append(
            {
                "kind": "project-similarity",
                "reasons": ["domain:AI"],
                "source": "project:project-0",
                "target": "project:missing",
                "weight": 4,
            }
        )
    else:
        edges = [edge for edge in edges if edge["kind"] != "project-similarity"]
        edges.extend(
            {
                "kind": "project-similarity",
                "reasons": [
                    "domain:AI",
                    "outcome:Tool",
                    "pattern:Evaluation",
                    "problem:Routing",
                    "technology:Python",
                ],
                "source": "project:project-0",
                "target": f"project:project-{index}",
                "weight": 20,
            }
            for index in range(1, 7)
        )
    edges_path.write_text(
        json.dumps(edges, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    refresh_fixture_manifest(fixture, None, project_ids)
    before = _snapshot(fixture)

    code = main(["validate", "--fixture", str(fixture)])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert json.loads(captured.err)["error"]["category"] == "validation"
    assert str(fixture) not in captured.err
    assert _snapshot(fixture) == before


def test_cli_promotion_rejects_malformed_graph_and_preserves_last_good(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)
    public = workspace / "portfolio-homepage" / "public-bundle"
    write_bundle_fixture(public, None, "last good", project_ids=("alpha", "beta"))
    before = _snapshot(public)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
    real_build = cli_module.build_candidate_bundle
    real_validate = cli_module.validate_bundle
    candidate_manifest = None

    def build_malformed(context, staging):
        nonlocal candidate_manifest
        candidate_manifest = real_build(context, staging)
        edges_path = staging / "graph" / "edges.json"
        edges = json.loads(edges_path.read_text(encoding="utf-8"))
        edges.append(
            {
                "kind": "project-similarity",
                "reasons": ["domain:AI"],
                "source": "project:alpha",
                "target": "project:missing",
                "weight": 4,
            }
        )
        edges_path.write_text(
            json.dumps(edges, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        refresh_fixture_manifest(staging, None, ("alpha", "beta"))
        return candidate_manifest

    def defer_staging_validation_to_promoter(root, gate):
        if ".project-atlas-staging-" in root.as_posix():
            assert candidate_manifest is not None
            return candidate_manifest
        return real_validate(root, gate)

    monkeypatch.setattr(cli_module, "build_candidate_bundle", build_malformed)
    monkeypatch.setattr(cli_module, "validate_bundle", defer_staging_validation_to_promoter)

    code = main(["build", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert json.loads(captured.err)["error"]["category"] == "validation"
    assert str(workspace) not in captured.err
    assert _snapshot(public) == before
    assert not tuple((workspace / "portfolio-homepage").glob(".project-atlas-staging-*"))


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


@pytest.mark.parametrize("dry_run", (True, False))
def test_cli_build_blocks_configured_alias_key_without_output_or_bundle_leak(
    tmp_path, monkeypatch, capsys, dry_run
):
    workspace = make_workspace_fixture(tmp_path)
    service = workspace / "portfolio-homepage"
    public = service / "public-bundle"
    if not dry_run:
        write_bundle_fixture(public, None, "last good")
    public_before = _snapshot(public) if public.exists() else None
    encoded_key = PRODUCTION_ALIAS_KEY.encode("utf-8").hex().upper()
    write_project_profile(
        workspace / "projects" / "alpha",
        summary=f"prefix:{encoded_key}:suffix",
    )
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
    before = _snapshot(workspace)
    arguments = ["build", "--workspace", str(workspace)]
    if dry_run:
        arguments.append("--dry-run")

    code = main(arguments)

    captured = capsys.readouterr()
    assert code == EXIT_PRIVACY
    assert json.loads(captured.err) == {
        "error": {"category": "alias_key", "pointer": "$"}
    }
    assert PRODUCTION_ALIAS_KEY not in captured.err
    assert encoded_key not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()
    assert _snapshot(workspace) == before
    if public_before is None:
        assert not public.exists()
    else:
        assert _snapshot(public) == public_before
    assert not tuple(service.glob(".project-atlas-staging-*"))


def test_non_dry_cli_rejects_short_alias_key_before_publication(tmp_path, monkeypatch, capsys):
    workspace = make_workspace_fixture(tmp_path)
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", "short-test-key")

    code = main(["build", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_VALIDATION
    assert json.loads(captured.err) == {
        "error": {"category": "config", "pointer": "/alias-key"}
    }
    assert "short-test-key" not in captured.err
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()


@pytest.mark.parametrize("failure_stage", ("copy", "validation", "rename"))
def test_cli_recovery_failures_return_sanitized_io_and_preserve_last_good(
    tmp_path, monkeypatch, capsys, failure_stage
):
    workspace = make_workspace_fixture(tmp_path)
    service = workspace / "portfolio-homepage"
    public = service / "public-bundle"
    backup = service / ".public-bundle.previous"
    recovery = service / ".public-bundle.recovery"
    write_bundle_fixture(public, None, "last good")
    before = _snapshot(public)
    write_project_profile(workspace / "projects" / "alpha", summary="new candidate")
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)
    real_rename = bundle_module._rename
    real_validate = bundle_module._validate_bundle

    def fail_candidate_and_restore_renames(source: Path, target: Path) -> None:
        if target == public and (
            source.name == "candidate"
            or source == backup
            or (source == recovery and failure_stage == "rename")
        ):
            raise OSError("injected private recovery path")
        real_rename(source, target)

    def fail_copy(source: Path, target: Path) -> None:
        raise OSError("injected private recovery copy")

    def fail_validation(root: Path, tree):
        if root == recovery:
            raise ValueError("injected private recovery validation")
        return real_validate(root, tree)

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_and_restore_renames)
    if failure_stage == "copy":
        monkeypatch.setattr(bundle_module, "_copytree", fail_copy)
    if failure_stage == "validation":
        monkeypatch.setattr(bundle_module, "_validate_bundle", fail_validation)

    code = main(["build", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert json.loads(captured.err) == {
        "error": {"category": "io", "pointer": "$"}
    }
    assert "injected" not in captured.err
    assert str(workspace) not in captured.err
    assert "traceback" not in captured.err.casefold()
    last_good = public if public.exists() else backup
    assert _snapshot(last_good) == before
    assert not recovery.exists()
    assert not tuple(service.glob(".project-atlas-staging-*"))


def test_cli_does_not_hide_programming_runtime_errors(tmp_path, monkeypatch):
    workspace = make_workspace_fixture(tmp_path)

    def fail_dispatch(args):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(cli_module, "dispatch", fail_dispatch)

    with pytest.raises(RuntimeError, match="programming defect"):
        main(["discover", "--workspace", str(workspace)])


def test_reviewed_history_round_trips_into_local_and_public_svg_changelog_idempotently(
    tmp_path, monkeypatch
):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(
        sessions / "decision.jsonl",
        workspace,
        raw_text="We decided the architecture trade-off.",
    )
    _write_session(
        sessions / "rollback.jsonl",
        workspace,
        raw_text="Rollback to the reviewed path.",
    )
    _write_revision_session(sessions / "revision.jsonl", workspace)
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
    assert [claim["claim_type"] for claim in dry["claims"]] == [
        "decision",
        "revision",
        "rollback",
    ]
    selected = []
    for claim in dry["claims"]:
        reviewed = dict(claim)
        reviewed["selected"] = True
        selected.append(reviewed)
    report = tmp_path / "reviewed-history.json"
    report.write_text(json.dumps({"claims": selected}), encoding="utf-8")
    monkeypatch.setenv("PROJECT_ATLAS_HMAC_KEY", PRODUCTION_ALIAS_KEY)

    first = invoke_cli_json(
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

    local_memory = workspace / "projects" / "alpha" / "project_memory"
    local_svg = local_memory / "visuals" / "problem-solving.svg"
    public = workspace / "portfolio-homepage" / "public-bundle"
    changelog = json.loads((public / "changelog.json").read_text(encoding="utf-8"))
    assert first["backfill"]["applied"] == {"claims": 3, "files": 4, "projects": 1}
    assert local_svg.is_file()
    assert not (public / "projects" / "alpha" / "decisions.md").exists()
    assert not (public / "projects" / "alpha" / "visuals" / "problem-solving.svg").exists()
    assert {(entry["stage"], entry["date"]) for entry in changelog} == {
        ("decision", "2026-08-24"),
        ("revision", "2026-08-24"),
        ("rollback", "2026-08-24"),
    }
    assert all(set(entry) == {
        "context",
        "date",
        "decision",
        "event_id",
        "outcome",
        "project_id",
        "stage",
        "title",
    } for entry in changelog)
    assert str(sessions) not in json.dumps(changelog)
    before_rerun = _snapshot(workspace)

    second = invoke_cli_json(
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

    assert not second["build"]["changed"]
    assert second["backfill"]["applied"] == {"claims": 3, "files": 0, "projects": 1}
    assert _snapshot(workspace) == before_rerun


def test_reviewed_svg_is_in_same_rollback_transaction_as_memory_and_cursor(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)
    sessions = tmp_path / "sessions"
    _write_session(
        sessions / "decision.jsonl",
        workspace,
        raw_text="We decided the architecture trade-off.",
    )
    _write_session(
        sessions / "rollback.jsonl",
        workspace,
        raw_text="Rollback to the reviewed path.",
    )
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
    selected = []
    for claim in dry["claims"]:
        reviewed = dict(claim)
        reviewed["selected"] = True
        selected.append(reviewed)
    report = tmp_path / "reviewed-history.json"
    report.write_text(json.dumps({"claims": selected}), encoding="utf-8")
    before = _snapshot(workspace)
    real_replace = fs_safety_module._replace_file
    visual_replacements = 0

    def fail_cursor_after_visual(source, destination):
        nonlocal visual_replacements
        if Path(destination).name == "problem-solving.svg":
            visual_replacements += 1
        if Path(destination).name == "session-cursor.json":
            raise OSError("injected cursor failure after SVG")
        return real_replace(source, destination)

    monkeypatch.setattr(fs_safety_module, "_replace_file", fail_cursor_after_visual)

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

    captured = capsys.readouterr()
    assert code == EXIT_IO
    assert visual_replacements == 1
    assert _snapshot(workspace) == before
    assert "injected" not in captured.err
    assert str(workspace) not in captured.err
