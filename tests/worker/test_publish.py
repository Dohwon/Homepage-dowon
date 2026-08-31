from pathlib import Path
import subprocess
import sys

import pytest

import atlas_worker.cli as cli_module
from atlas_worker.cli import build_parser
from atlas_worker.models import PromotionResult
from atlas_worker.publish import (
    GitRunner,
    PublishError,
    publish_bundle,
    run_publication_tests,
)
from tests.worker.git_helpers import git, init_repo, write
from tests.worker.helpers import make_workspace_fixture


def test_publish_cli_exposes_changed_only_and_explicit_push():
    args = build_parser().parse_args(
        ["publish", "--workspace", "/workspace", "--changed-only", "--push"]
    )

    assert args.command == "publish"
    assert args.changed_only
    assert args.push


def test_user_timer_has_the_bounded_daily_contract():
    root = Path(__file__).parents[2]
    service = (root / "deploy/systemd-user/project-atlas.service").read_text(
        encoding="utf-8"
    )
    timer = (root / "deploy/systemd-user/project-atlas.timer").read_text(
        encoding="utf-8"
    )

    assert (
        "publish --workspace /home/dowon/securedir/git/codex --changed-only --push"
        in service
    )
    assert "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1" in service
    assert "prlimit --as=2147483648 --cpu=1800" in service
    assert "ReadWritePaths=/home/dowon/securedir/git/codex/.knowledge-worker /home/dowon/securedir/git/codex/portfolio-homepage" in service
    assert "ReadOnlyPaths=/home/dowon/.config/project-atlas" in service
    assert "ReadWritePaths=/home/dowon/securedir/git/codex /" not in service
    assert "OnBootSec=1h" in timer
    assert "OnUnitActiveSec=1d" in timer
    assert "RandomizedDelaySec=60" in timer
    assert "Persistent=true" in timer


def test_publisher_stages_only_public_bundle(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')
    write(repo / "server.js", "unrelated user edit\n")

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
    )

    assert result.staged_paths == ("public-bundle/manifest.json",)
    assert result.committed
    assert not result.pushed
    assert "?? server.js" in git(repo, "status", "--short")
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == "public-bundle/manifest.json"


def test_noop_promotion_creates_no_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    before = git(repo, "rev-parse", "HEAD")

    result = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=False,
    )

    assert not result.committed
    assert not result.deferred
    assert git(repo, "rev-parse", "HEAD") == before


def test_preexisting_staged_work_defers_without_touching_index(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "server.js", "staged user edit\n")
    git(repo, "add", "--", "server.js")
    before = git(repo, "diff", "--cached", "--name-only")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
    )

    assert result.deferred
    assert not result.committed
    assert git(repo, "diff", "--cached", "--name-only") == before
    assert "?? public-bundle/" in git(repo, "status", "--short")


def test_changed_promotion_without_bundle_diff_creates_no_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    before = git(repo, "rev-parse", "HEAD")

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
    )

    assert not result.committed
    assert result.staged_paths == ()
    assert git(repo, "rev-parse", "HEAD") == before


def test_commit_message_lists_at_most_three_changed_projects(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    publish_bundle(
        repo,
        PromotionResult(
            changed=True,
            changed_projects=("alpha", "beta", "delta", "gamma"),
        ),
        push=False,
    )

    assert git(repo, "log", "-1", "--format=%s") == (
        "content: update project atlas (alpha, beta, delta +1)"
    )


def test_automated_commit_cannot_run_hook_that_stages_unrelated_work(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')
    write(repo / "server.js", "unrelated user edit\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    write(hook, "#!/bin/sh\ngit add -- server.js\n")
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", ".git/hooks")

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
    )

    assert result.committed
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == (
        "public-bundle/manifest.json"
    )
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert "?? server.js" in git(repo, "status", "--short")


class _FailCommitRunner(GitRunner):
    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if "commit-tree" in args:
            raise PublishError("injected commit failure")
        return super().run(repo, *args, **kwargs)


def test_commit_failure_preserves_the_real_git_index(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')
    before = git(repo, "write-tree")

    with pytest.raises(PublishError, match="injected commit failure"):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=False,
            runner=_FailCommitRunner(),
        )

    assert git(repo, "write-tree") == before
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert "?? public-bundle/" in git(repo, "status", "--short")


def test_failed_push_is_retried_on_the_next_unchanged_run(tmp_path):
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    git(repo, "remote", "add", "origin", str(remote))
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    with pytest.raises(PublishError):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=True,
        )
    local_head = git(repo, "rev-parse", "HEAD")
    subprocess.run(("git", "init", "--bare", "--quiet", str(remote)), check=True)

    result = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=True,
    )

    assert not result.committed
    assert result.pushed
    assert git(remote, "rev-parse", "refs/heads/master") == local_head


def test_deferred_bundle_is_committed_after_staged_work_is_cleared(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "server.js", "staged user edit\n")
    git(repo, "add", "--", "server.js")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    deferred = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
    )
    git(repo, "restore", "--staged", "--", "server.js")
    retried = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=False,
    )

    assert deferred.deferred
    assert retried.committed
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == (
        "public-bundle/manifest.json"
    )


def test_commit_failure_is_retried_after_the_index_is_restored(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    with pytest.raises(PublishError):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=False,
            runner=_FailCommitRunner(),
        )
    retried = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=False,
    )

    assert retried.committed
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_bundle_stage_left_by_an_interrupted_run_is_recovered(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')
    git(repo, "add", "--", "public-bundle")

    result = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=False,
    )

    assert result.committed
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == (
        "public-bundle/manifest.json"
    )


class _StageUnrelatedBeforeCommitRunner(GitRunner):
    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if "commit-tree" in args:
            write(repo / "server.js", "concurrent staged edit\n")
            super().run(repo, "add", "--", "server.js")
        return super().run(repo, *args, **kwargs)


def test_concurrent_unrelated_stage_cannot_enter_the_atlas_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
        runner=_StageUnrelatedBeforeCommitRunner(),
    )

    assert result.committed
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == (
        "public-bundle/manifest.json"
    )
    assert git(repo, "diff", "--cached", "--name-only") == "server.js"


class _ChangeBundleAfterStageRunner(GitRunner):
    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "write-tree":
            write(repo / "public-bundle" / "manifest.json", '{"version":"v3"}\n')
        return super().run(repo, *args, **kwargs)


def test_bundle_worktree_change_after_stage_cannot_enter_the_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=False,
        runner=_ChangeBundleAfterStageRunner(),
    )

    assert result.committed
    assert git(repo, "show", "HEAD:public-bundle/manifest.json") == '{"version":"v2"}'
    assert (repo / "public-bundle" / "manifest.json").read_text(encoding="utf-8") == (
        '{"version":"v3"}\n'
    )


class _AdvanceBranchBeforeCasRunner(GitRunner):
    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "update-ref":
            write(repo / "later.txt", "concurrent local commit\n")
            super().run(repo, "add", "--", "later.txt")
            super().run(
                repo,
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "--no-gpg-sign",
                "--only",
                "-m",
                "test: concurrent local commit",
                "--",
                "later.txt",
            )
        return super().run(repo, *args, **kwargs)


def test_branch_advance_before_cas_cannot_become_an_atlas_commit_ancestor(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    with pytest.raises(PublishError):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=False,
            runner=_AdvanceBranchBeforeCasRunner(),
        )

    assert git(repo, "show", "--name-only", "--format=", "HEAD") == "later.txt"
    assert "public-bundle/manifest.json" not in git(
        repo, "show", "--name-only", "--format=", "HEAD"
    )


class _CommitCompetingBundleBeforeCasRunner(GitRunner):
    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "update-ref":
            super().run(
                repo,
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "--no-gpg-sign",
                "-m",
                "content: competing bundle commit",
            )
        return super().run(repo, *args, **kwargs)


def test_cas_race_cannot_push_a_different_bundle_only_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", "--quiet", str(remote)), check=True)
    git(repo, "remote", "add", "origin", str(remote))
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    with pytest.raises(PublishError):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=True,
            runner=_CommitCompetingBundleBeforeCasRunner(),
        )
    competing = git(repo, "rev-parse", "HEAD")

    with pytest.raises(PublishError):
        publish_bundle(
            repo,
            PromotionResult(changed=False, changed_projects=()),
            push=True,
        )

    assert git(repo, "rev-parse", "HEAD") == competing
    remote_head = subprocess.run(
        ("git", "--git-dir", str(remote), "rev-parse", "--verify", "refs/heads/master"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert remote_head.returncode != 0


class _FailAfterBranchAdvanceRunner(GitRunner):
    def __init__(self):
        self.advanced = False

    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "update-ref":
            result = super().run(repo, *args, **kwargs)
            self.advanced = True
            return result
        if self.advanced and args and args[0] == "diff-tree":
            self.advanced = False
            raise PublishError("injected post-advance failure")
        return super().run(repo, *args, **kwargs)


def test_advance_marker_recovers_the_exact_commit_after_a_post_cas_crash(tmp_path):
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", "--quiet", str(remote)), check=True)
    git(repo, "remote", "add", "origin", str(remote))
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')

    with pytest.raises(PublishError, match="post-advance"):
        publish_bundle(
            repo,
            PromotionResult(changed=True, changed_projects=("alpha",)),
            push=True,
            runner=_FailAfterBranchAdvanceRunner(),
        )
    committed = git(repo, "rev-parse", "HEAD")

    recovered = publish_bundle(
        repo,
        PromotionResult(changed=False, changed_projects=()),
        push=True,
    )

    assert recovered.pushed
    assert not recovered.committed
    assert git(remote, "rev-parse", "refs/heads/master") == committed


class _MoveHeadBeforePushRunner(GitRunner):
    def __init__(self):
        self.validated_head = ""

    def run(self, repo: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "push":
            self.validated_head = super().run(repo, "rev-parse", "HEAD")
            write(repo / "later.txt", "later local commit\n")
            super().run(repo, "add", "--", "later.txt")
            super().run(
                repo,
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "--no-gpg-sign",
                "-m",
                "test: later local commit",
            )
        return super().run(repo, *args, **kwargs)


def test_push_uses_the_recorded_commit_even_if_head_moves(tmp_path):
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", "--quiet", str(remote)), check=True)
    git(repo, "remote", "add", "origin", str(remote))
    write(repo / "public-bundle" / "manifest.json", '{"version":"v2"}\n')
    runner = _MoveHeadBeforePushRunner()

    result = publish_bundle(
        repo,
        PromotionResult(changed=True, changed_projects=("alpha",)),
        push=True,
        runner=runner,
    )

    assert result.pushed
    assert git(remote, "rev-parse", "refs/heads/master") == runner.validated_head
    assert git(repo, "rev-parse", "HEAD") != runner.validated_head


def test_publication_test_gate_fails_closed_on_a_nonzero_test_command(tmp_path):
    repo = init_repo(tmp_path / "repo")

    with pytest.raises(PublishError, match="publication tests failed"):
        run_publication_tests(
            repo,
            command=(sys.executable, "-c", "raise SystemExit(7)"),
        )


def test_publish_command_stops_before_build_when_release_tests_fail(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)

    class ReadyCatalog:
        ready = True
        project_ids = tuple(f"project-{index}" for index in range(33))

    monkeypatch.setattr(
        "scripts.audit_public_atlas_catalog.audit_public_catalog",
        lambda _workspace: ReadyCatalog(),
    )
    monkeypatch.setattr(
        cli_module,
        "run_publication_tests",
        lambda _repo: (_ for _ in ()).throw(PublishError("publication tests failed")),
    )
    monkeypatch.setattr(
        cli_module,
        "_execute_build",
        lambda *_args, **_kwargs: pytest.fail("build ran after a failed release gate"),
    )

    code = cli_module.main(["publish", "--workspace", str(workspace)])

    assert code == 2
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert "traceback" not in capsys.readouterr().err.casefold()


def test_publish_rejects_source_drift_after_catalog_and_tests(
    tmp_path, monkeypatch, capsys
):
    workspace = make_workspace_fixture(tmp_path)

    class StaleCatalog:
        ready = True
        project_ids = tuple(f"project-{index}" for index in range(33))
        input_digest = "stale-catalog-input"
        bundle_version = "stale-catalog-bundle"

    monkeypatch.setattr(
        "scripts.audit_public_atlas_catalog.audit_public_catalog",
        lambda _workspace: StaleCatalog(),
    )
    monkeypatch.setattr(cli_module, "run_publication_tests", lambda _repo: None)
    monkeypatch.setenv(
        "PROJECT_ATLAS_HMAC_KEY",
        "0123456789abcdef0123456789abcdef",
    )

    code = cli_module.main(["publish", "--workspace", str(workspace)])

    assert code == 2
    assert not (workspace / "portfolio-homepage" / "public-bundle").exists()
    assert "stale-catalog-input" not in capsys.readouterr().err
