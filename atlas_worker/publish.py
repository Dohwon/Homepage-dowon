"""Allowlisted Git publication for an already-promoted Atlas bundle."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Sequence

from .models import PromotionResult


PUBLISH_ROOT = "public-bundle"
_PENDING_PUSH = "project-atlas-pending-push"


class PublishError(ValueError):
    """Raised when publication would touch anything outside the bundle."""


@dataclass(frozen=True)
class PublishResult:
    committed: bool
    pushed: bool
    staged_paths: tuple[str, ...]
    deferred: bool = False


class GitRunner:
    def run(
        self,
        repo: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> str:
        try:
            command_env = os.environ.copy()
            if env:
                command_env.update(env)
            completed = subprocess.run(
                ("git", *args),
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                env=command_env,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise PublishError("Git publication failed") from error
        return completed.stdout.strip()

    def lines(
        self,
        repo: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> tuple[str, ...]:
        return tuple(line for line in self.run(repo, *args, env=env).splitlines() if line)


def run_publication_tests(
    repo: Path,
    *,
    command: Sequence[str] | None = None,
) -> None:
    test_command = tuple(command) if command is not None else (
        sys.executable,
        "-m",
        "pytest",
        "tests/worker",
        "-q",
    )
    environment = os.environ.copy()
    environment.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    last_error: BaseException | None = None
    environment.pop("PROJECT_ATLAS_HMAC_KEY", None)
    environment.pop("PROJECT_ATLAS_HMAC_KEY_PATH", None)
    with tempfile.TemporaryDirectory(prefix="project-atlas-test-config-") as config_home:
        environment["XDG_CONFIG_HOME"] = config_home
        for _attempt in range(2):
            try:
                subprocess.run(
                    test_command,
                    cwd=Path(repo),
                    check=True,
                    capture_output=True,
                    text=True,
                    env=environment,
                    timeout=1800,
                )
                return
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                last_error = error
    if isinstance(last_error, subprocess.CalledProcessError):
        if last_error.stdout:
            print(last_error.stdout, file=sys.stderr, end="")
        if last_error.stderr:
            print(last_error.stderr, file=sys.stderr, end="")
    raise PublishError("publication tests failed") from last_error


def publish_bundle(
    repo: Path,
    promotion: PromotionResult,
    *,
    push: bool = False,
    runner: GitRunner | None = None,
) -> PublishResult:
    repository = Path(repo).resolve()
    git = runner or GitRunner()
    retried_push = _retry_pending_push(repository, git) if push else False
    bundle_work = git.lines(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        PUBLISH_ROOT,
    )
    if not bundle_work:
        return PublishResult(False, retried_push, ())

    preexisting = git.lines(repository, "diff", "--cached", "--name-only")
    if any(
        path != PUBLISH_ROOT and not path.startswith(f"{PUBLISH_ROOT}/")
        for path in preexisting
    ):
        return PublishResult(False, False, (), deferred=True)

    tracked = git.lines(repository, "ls-files", "--", PUBLISH_ROOT)
    if not (repository / PUBLISH_ROOT).exists() and not tracked:
        return PublishResult(False, False, ())
    git.run(repository, "add", "--", PUBLISH_ROOT)
    staged = git.lines(repository, "diff", "--cached", "--name-only")
    try:
        _require_bundle_only(staged)
        if not staged:
            return PublishResult(False, retried_push, ())
        base = git.run(repository, "rev-parse", "HEAD")
        branch_ref = git.run(repository, "symbolic-ref", "--quiet", "HEAD")
        if not branch_ref.startswith("refs/heads/"):
            raise PublishError("publication requires an attached branch")
        if push:
            _write_pending_marker(
                repository,
                git,
                {"phase": "commit", "base": base, "ref": branch_ref},
            )
        tree = git.run(repository, "write-tree")
        tree_paths = git.lines(
            repository,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            base,
            tree,
        )
        _require_bundle_only(tree_paths)
        committed = git.run(
            repository,
            "-c",
            "commit.gpgSign=false",
            "commit-tree",
            tree,
            "-p",
            base,
            "-m",
            _commit_message(promotion.changed_projects),
        )
        if push:
            _write_pending_marker(
                repository,
                git,
                {
                    "phase": "advance",
                    "base": base,
                    "commit": committed,
                    "ref": branch_ref,
                },
            )
        git.run(repository, "update-ref", branch_ref, committed, base)
    except BaseException:
        git.run(repository, "restore", "--staged", "--source=HEAD", "--", PUBLISH_ROOT)
        raise

    committed_paths = git.lines(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        committed,
    )
    _require_bundle_only(committed_paths)
    if push:
        _write_pending_marker(
            repository,
            git,
            {"phase": "push", "commit": committed, "ref": branch_ref},
        )
        _push_pending(repository, git)
    return PublishResult(True, push, staged)


def _require_bundle_only(paths: Sequence[str]) -> None:
    if any(path != PUBLISH_ROOT and not path.startswith(f"{PUBLISH_ROOT}/") for path in paths):
        raise PublishError("refusing non-bundle staged paths")


def _git_path(repo: Path, git: GitRunner, name: str) -> Path:
    value = Path(git.run(repo, "rev-parse", "--git-path", name))
    return value if value.is_absolute() else repo / value


def _pending_path(repo: Path, git: GitRunner) -> Path:
    return _git_path(repo, git, _PENDING_PUSH)


def _write_pending_marker(repo: Path, git: GitRunner, payload: dict[str, str]) -> None:
    target = _pending_path(repo, git)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise PublishError("pending push marker is invalid")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{_PENDING_PUSH}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            descriptor = -1
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _retry_pending_push(repo: Path, git: GitRunner) -> bool:
    target = _pending_path(repo, git)
    if target.is_symlink():
        raise PublishError("pending push marker is invalid")
    if not target.exists():
        return False
    if not target.is_file():
        raise PublishError("pending push marker is invalid")
    try:
        payload = json.loads(target.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublishError("pending push marker is invalid") from error
    if not isinstance(payload, dict) or payload.get("phase") not in {
        "commit",
        "advance",
        "push",
    }:
        raise PublishError("pending push marker is invalid")
    branch_ref = payload.get("ref")
    if not isinstance(branch_ref, str) or not branch_ref.startswith("refs/heads/"):
        raise PublishError("pending push marker is invalid")
    if payload["phase"] == "commit":
        base = payload.get("base")
        if not isinstance(base, str) or not base:
            raise PublishError("pending push marker is invalid")
        if git.run(repo, "symbolic-ref", "--quiet", "HEAD") != branch_ref:
            raise PublishError("pending push branch changed")
        head = git.run(repo, "rev-parse", "HEAD")
        if head == base:
            return False
        raise PublishError("pending publication commit is ambiguous")
    if payload["phase"] == "advance":
        base = payload.get("base")
        commit = payload.get("commit")
        if not isinstance(base, str) or not isinstance(commit, str) or not base or not commit:
            raise PublishError("pending push marker is invalid")
        if git.run(repo, "symbolic-ref", "--quiet", "HEAD") != branch_ref:
            raise PublishError("pending push branch changed")
        if git.run(repo, "rev-parse", f"{commit}^") != base:
            raise PublishError("pending publication commit is invalid")
        _require_bundle_only(
            git.lines(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
        )
        head = git.run(repo, "rev-parse", "HEAD")
        if head == base:
            git.run(repo, "update-ref", branch_ref, commit, base)
        elif head != commit:
            raise PublishError("pending publication commit is ambiguous")
        payload = {"phase": "push", "commit": commit, "ref": branch_ref}
        _write_pending_marker(repo, git, payload)
    commit = payload.get("commit")
    if not isinstance(commit, str) or not commit:
        raise PublishError("pending push marker is invalid")
    _require_bundle_only(
        git.lines(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    )
    _push_pending(repo, git)
    return True


def _push_pending(repo: Path, git: GitRunner) -> None:
    target = _pending_path(repo, git)
    try:
        payload = json.loads(target.read_text(encoding="ascii"))
        commit = payload["commit"]
        branch_ref = payload["ref"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise PublishError("pending push marker is invalid") from error
    if not isinstance(commit, str) or not isinstance(branch_ref, str):
        raise PublishError("pending push marker is invalid")
    git.run(repo, "push", "origin", f"{commit}:{branch_ref}")
    _pending_path(repo, git).unlink(missing_ok=True)


def _commit_message(project_ids: Sequence[str]) -> str:
    if not project_ids:
        return "content: update project atlas"
    listed = ", ".join(project_ids[:3])
    suffix = "" if len(project_ids) <= 3 else f" +{len(project_ids) - 3}"
    return f"content: update project atlas ({listed}{suffix})"
