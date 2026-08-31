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


def test_user_timer_has_the_bounded_fifteen_minute_contract():
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
    assert "OnBootSec=5m" in timer
    assert "OnUnitActiveSec=15m" in timer
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
        if "commit" in args:
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
