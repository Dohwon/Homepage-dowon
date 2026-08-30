from pathlib import Path

from atlas_worker.cli import build_parser
from atlas_worker.models import PromotionResult
from atlas_worker.publish import publish_bundle
from tests.worker.git_helpers import git, init_repo, write


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
