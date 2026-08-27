from __future__ import annotations

from pathlib import Path

import pytest

from atlas_worker.models import ProjectRef
from atlas_worker.source_manifest import build_source_manifest, resolve_git_owner


class FakeGitRunner:
    def __init__(
        self,
        *,
        common_dirs: dict[Path, str] | None = None,
        heads: dict[Path, str] | None = None,
    ) -> None:
        self.common_dirs = common_dirs or {}
        self.heads = heads or {}

    def run(self, cwd: Path, *args: str) -> str:
        if args == ("rev-parse", "--git-common-dir"):
            return self.common_dirs.get(cwd, "")
        if args == ("rev-parse", "HEAD"):
            return self.heads.get(cwd, "")
        raise AssertionError(f"unexpected Git arguments: {args}")


def project_ref(root: Path, project_id: str) -> ProjectRef:
    return ProjectRef(
        project_id=project_id,
        display_name=project_id.title(),
        root=root,
        relative_path=f"projects/{project_id}",
        lifecycle="active",
        publication="private",
        aliases=(),
    )


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


def test_multiple_git_common_dir_owners_fail_closed(tmp_path):
    alpha = project_ref(tmp_path / "projects/alpha", "alpha")
    beta = project_ref(tmp_path / "projects/beta", "beta")
    worktree = tmp_path / "projects/alpha/.worktrees/review"
    runner = FakeGitRunner(
        common_dirs={alpha.root: "/git/shared", beta.root: "/git/shared", worktree: "/git/shared"}
    )

    assert resolve_git_owner(worktree, (alpha, beta), runner) is None


def test_similar_version_names_do_not_create_predecessor(tmp_path):
    root = tmp_path / "projects/map-v2"
    root.mkdir(parents=True)

    manifest = build_source_manifest(project_ref(root, "map-v2"), FakeGitRunner())

    assert manifest.predecessor_ids == ()


def test_manifest_uses_confined_relative_hashes_and_reviewed_predecessors_only(tmp_path):
    root = tmp_path / "projects/current"
    article = root / "project_memory/project-atlas/article.yaml"
    article.parent.mkdir(parents=True)
    article.write_text("prior_context:\n  project_id: reviewed-previous\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src/main.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "notes-v3.md").write_text("name-only evidence\n", encoding="utf-8")

    manifest = build_source_manifest(
        project_ref(root, "current"),
        FakeGitRunner(common_dirs={root: "/git/current"}, heads={root: "abc123"}),
    )

    assert [(item.relative_path, item.source_class, item.project_id) for item in manifest.files] == [
        ("notes-v3.md", "source", "current"),
        ("project_memory/project-atlas/article.yaml", "project_memory", "current"),
        ("src/main.py", "source", "current"),
    ]
    assert all(len(item.content_hash) == 64 for item in manifest.files)
    assert manifest.predecessor_ids == ("reviewed-previous",)
    assert manifest.git_head_fingerprint != "abc123"
    assert manifest.git_common_dir_fingerprint != "/git/current"


def test_manifest_rejects_symlinked_source_file(tmp_path):
    root = tmp_path / "projects/alpha"
    root.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("private\n", encoding="utf-8")
    (root / "notes.md").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        build_source_manifest(project_ref(root, "alpha"), FakeGitRunner())
