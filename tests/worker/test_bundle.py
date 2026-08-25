import json
import os
from pathlib import Path

import pytest

import atlas_worker.bundle as bundle_module
from atlas_worker.bundle import BundleContext, SearchDocument, build_candidate_bundle, promote_bundle
from atlas_worker.manifest import tree_hash
from atlas_worker.models import (
    BundleManifest,
    GraphData,
    GraphEdge,
    GraphNode,
    ProjectMemory,
    PublicProject,
)
from atlas_worker.privacy import PrivacyGate, PrivacyViolation
from tests.worker.helpers import (
    make_challenge_events,
    make_public_project,
    refresh_fixture_manifest,
    write_bundle_fixture,
)


def _context(
    *,
    projects: tuple[PublicProject, ...] | None = None,
    decisions: tuple[str, ...] = ("Keep typed contracts",),
    source_hashes: dict[str, str] | None = None,
    gate: PrivacyGate | None = None,
) -> BundleContext:
    projects = projects or (make_public_project("alpha"),)
    memories = {
        project.project_id: ProjectMemory(
            profile=project.to_dict(),
            build_story=("Built the local pipeline",),
            decisions=decisions,
            rollbacks=(),
        )
        for project in projects
    }
    events = {project.project_id: make_challenge_events() for project in projects}
    nodes = tuple(
        GraphNode(f"project:{project.project_id}", project.display_name, "project")
        for project in reversed(projects)
    )
    edges = ()
    if len(projects) > 1:
        edges = (
            GraphEdge(
                f"project:{projects[1].project_id}",
                f"project:{projects[0].project_id}",
                "project-similarity",
                3,
                ("domain:AI",),
            ),
        )
    search_documents = tuple(
        SearchDocument(
            document_id=f"project:{project.project_id}",
            project_id=project.project_id,
            title=project.display_name,
            body=project.summary,
            url=f"/projects/{project.project_id}",
        )
        for project in reversed(projects)
    )
    return BundleContext(
        projects=projects,
        project_memories=memories,
        project_events=events,
        graph=GraphData(nodes=nodes, edges=edges),
        search_documents=search_documents,
        source_hashes=source_hashes or {"alpha": "a" * 64},
        previous_manifest=None,
        privacy_gate=gate or PrivacyGate(alias_key=b"unit-test-key"),
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and not path.is_symlink()
    }


def test_build_emits_only_exact_public_layout_and_non_empty_optional_files(tmp_path):
    staging = tmp_path / "staging"
    build_candidate_bundle(_context(), staging)

    assert tuple(_tree_bytes(staging)) == (
        "changelog.json",
        "graph/edges.json",
        "graph/nodes.json",
        "manifest.json",
        "projects/alpha/build-story.md",
        "projects/alpha/decisions.md",
        "projects/alpha/project.json",
        "projects/alpha/visuals/problem-solving.svg",
        "search-index.json",
        "topics.json",
    )
    assert not (staging / "projects/alpha/rollbacks.md").exists()


def test_build_rebuilds_staging_from_empty(tmp_path):
    staging = tmp_path / "staging"
    (staging / "raw-session").mkdir(parents=True)
    (staging / "raw-session/session.jsonl").write_text("private", encoding="utf-8")

    build_candidate_bundle(_context(), staging)

    assert not (staging / "raw-session").exists()


def test_manifest_is_schema_exact_content_derived_and_byte_deterministic(tmp_path):
    projects = (make_public_project("beta"), make_public_project("alpha"))
    first = tmp_path / "first"
    second = tmp_path / "second"

    manifest = build_candidate_bundle(_context(projects=projects), first)
    build_candidate_bundle(_context(projects=projects), second)
    payload = json.loads((first / "manifest.json").read_text(encoding="utf-8"))

    assert set(payload) == {"version", "projects", "files"}
    assert payload["projects"] == ["alpha", "beta"]
    assert "manifest.json" not in payload["files"]
    assert manifest.project_hashes.keys() == {"alpha", "beta"}
    assert manifest.to_dict() == payload
    assert _tree_bytes(first) == _tree_bytes(second)


def test_manifest_version_changes_with_source_hash_without_leaking_source_metadata(tmp_path):
    first = build_candidate_bundle(
        _context(source_hashes={"/home/dowon/.codex/sessions/raw.jsonl": "a" * 64}),
        tmp_path / "first",
    )
    second = build_candidate_bundle(
        _context(source_hashes={"/home/dowon/.codex/sessions/raw.jsonl": "b" * 64}),
        tmp_path / "second",
    )
    rendered = b"".join(_tree_bytes(tmp_path / "first").values())

    assert first.version != second.version
    assert b"/home/dowon" not in rendered
    assert b"session" not in rendered.lower()
    assert b"provenance" not in rendered.lower()
    assert b"unit-test-key" not in rendered


def test_build_strips_only_exact_managed_comments(tmp_path):
    context = _context(
        decisions=(
            "<!-- atlas:event:decision-001 -->\nKeep typed contracts\n<!-- /atlas:event:decision-001 -->",
        )
    )

    build_candidate_bundle(context, tmp_path / "staging")
    markdown = (tmp_path / "staging/projects/alpha/decisions.md").read_text(encoding="utf-8")

    assert "Keep typed contracts" in markdown
    assert "atlas:event" not in markdown


def test_build_blocks_arbitrary_html_comments(tmp_path):
    context = _context(decisions=("Keep this <!-- author note --> private",))

    with pytest.raises(PrivacyViolation, match="html_comment"):
        build_candidate_bundle(context, tmp_path / "staging")


def test_build_rejects_existing_staging_symlink_before_cleanup(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_candidate_bundle(_context(), staging)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_build_scans_every_artifact_and_complete_staging_tree(tmp_path):
    class TrackingGate(PrivacyGate):
        def __init__(self):
            super().__init__(alias_key=b"key")
            self.records = []

        def require_safe(self, record: object) -> None:
            self.records.append(record)
            super().require_safe(record)

    gate = TrackingGate()
    staging = tmp_path / "staging"

    build_candidate_bundle(_context(gate=gate), staging)

    artifact_count = len(_tree_bytes(staging))
    assert len(gate.records) == artifact_count + 1
    assert isinstance(gate.records[-1], dict)
    assert tuple(gate.records[-1]) == tuple(_tree_bytes(staging))


def test_first_publish_reports_all_projects(tmp_path):
    projects = (make_public_project("beta"), make_public_project("alpha"))
    staging = tmp_path / "staging"
    build_candidate_bundle(_context(projects=projects), staging)

    result = promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))

    assert result.changed
    assert result.changed_projects == ("alpha", "beta")
    assert not staging.exists()


def test_changed_and_removed_projects_are_reported_in_sorted_order(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, "old", "old summary", ("alpha", "beta", "gamma"))
    write_bundle_fixture(staging, "new", "new summary", ("beta",))

    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert result.changed_projects == ("alpha", "beta", "gamma")


def test_identical_candidate_is_noop_and_preserves_public_inode_and_bytes(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, version="same", summary="safe")
    write_bundle_fixture(staging, version="same", summary="safe")
    before = _tree_bytes(public_dir)
    inode = public_dir.stat().st_ino

    result = promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert not result.changed
    assert result.changed_projects == ()
    assert public_dir.stat().st_ino == inode
    assert _tree_bytes(public_dir) == before
    assert staging.exists()


def test_privacy_failure_preserves_last_good_bundle(tmp_path):
    public_dir = tmp_path / "public-bundle"
    write_bundle_fixture(public_dir, version="good", summary="safe")
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, version="bad", summary="/home/dowon/private")
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert json.loads((public_dir / "manifest.json").read_text(encoding="utf-8"))["version"] == "good"
    assert _tree_bytes(public_dir) == before


def test_full_tree_scan_preserves_duplicate_json_values_for_privacy(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, "good", "safe")
    write_bundle_fixture(staging, "candidate", "safe")
    project_path = staging / "projects/alpha/project.json"
    rendered = project_path.read_text(encoding="utf-8").replace(
        '"summary":"safe"',
        '"summary":"/home/dowon/private","summary":"safe"',
    )
    project_path.write_text(rendered, encoding="utf-8")
    refresh_fixture_manifest(staging, "candidate", ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(PrivacyViolation, match="absolute_path"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_schema_failure_preserves_last_good_bundle(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, "good", "safe")
    write_bundle_fixture(staging, "bad", "safe")
    project_path = staging / "projects/alpha/project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project.pop("tags")
    project_path.write_text(json.dumps(project, sort_keys=True) + "\n", encoding="utf-8")
    refresh_fixture_manifest(staging, "bad", ("alpha",))
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="tags"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_candidate_symlink_is_rejected_without_touching_public(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, "good", "safe")
    write_bundle_fixture(staging, "bad", "safe")
    (staging / "projects/alpha/leak.md").symlink_to(public_dir / "manifest.json")
    before = _tree_bytes(public_dir)

    with pytest.raises(ValueError, match="symlink"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before


def test_rename_failure_restores_prior_public_bundle(tmp_path, monkeypatch):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    write_bundle_fixture(public_dir, "good", "old")
    write_bundle_fixture(staging, "new", "new")
    before = _tree_bytes(public_dir)
    real_rename = bundle_module._rename
    calls = 0

    def fail_candidate_rename(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected candidate rename failure")
        real_rename(source, target)

    monkeypatch.setattr(bundle_module, "_rename", fail_candidate_rename)

    with pytest.raises(OSError, match="injected"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(public_dir) == before
    assert not (tmp_path / ".public-bundle.previous").exists()


def test_stale_backup_is_not_overwritten(tmp_path):
    public_dir = tmp_path / "public-bundle"
    staging = tmp_path / "staging"
    backup = tmp_path / ".public-bundle.previous"
    write_bundle_fixture(public_dir, "good", "old")
    write_bundle_fixture(staging, "new", "new")
    write_bundle_fixture(backup, "older", "older")
    backup_before = _tree_bytes(backup)
    public_before = _tree_bytes(public_dir)

    with pytest.raises(FileExistsError, match="stale backup"):
        promote_bundle(staging, public_dir, PrivacyGate(alias_key=b"key"))

    assert _tree_bytes(backup) == backup_before
    assert _tree_bytes(public_dir) == public_before


def test_tree_hash_uses_relative_paths_and_bytes_not_mtime(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_bundle_fixture(first, "same", "safe")
    write_bundle_fixture(second, "same", "safe")
    for path in second.rglob("*"):
        if path.is_file():
            os.utime(path, (1, 1))

    assert tree_hash(first) == tree_hash(second)


def test_promotion_rejects_unexpected_files_and_hash_mismatch(tmp_path):
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, "candidate", "safe")
    (staging / "raw.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))


def test_promotion_rejects_empty_optional_markdown(tmp_path):
    staging = tmp_path / "staging"
    write_bundle_fixture(staging, "candidate", "safe")
    (staging / "projects/alpha/decisions.md").write_text("", encoding="utf-8")
    refresh_fixture_manifest(staging, "candidate", ("alpha",))

    with pytest.raises(ValueError, match="non-empty"):
        promote_bundle(staging, tmp_path / "public-bundle", PrivacyGate(alias_key=b"key"))


def test_bundle_manifest_serialization_excludes_local_project_hashes():
    manifest = BundleManifest(
        version="v1",
        projects=("alpha",),
        files={"projects/alpha/project.json": "hash"},
        project_hashes={"alpha": "local-only"},
    )

    assert manifest.to_dict() == {
        "version": "v1",
        "projects": ["alpha"],
        "files": {"projects/alpha/project.json": "hash"},
    }
