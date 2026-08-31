"""Allowlisted Git publication for an already-promoted Atlas bundle."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
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
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PublishError("publication tests failed") from error


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
    if not promotion.changed:
        return PublishResult(False, retried_push, ())

    preexisting = git.lines(repository, "diff", "--cached", "--name-only")
    if preexisting:
        return PublishResult(False, False, (), deferred=True)

    tracked = git.lines(repository, "ls-files", "--", PUBLISH_ROOT)
    if not (repository / PUBLISH_ROOT).exists() and not tracked:
        return PublishResult(False, False, ())
    with _isolated_index(repository, git) as index_env:
        git.run(repository, "add", "--", PUBLISH_ROOT, env=index_env)
        staged = git.lines(
            repository,
            "diff",
            "--cached",
            "--name-only",
            env=index_env,
        )
        _require_bundle_only(staged)
        if not staged:
            return PublishResult(False, retried_push, ())
        message = _commit_message(promotion.changed_projects)
        git.run(
            repository,
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--no-gpg-sign",
            "-m",
            message,
            env=index_env,
        )

    committed_paths = git.lines(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "HEAD",
    )
    _require_bundle_only(committed_paths)
    git.run(repository, "add", "--", PUBLISH_ROOT)
    if git.lines(repository, "diff", "--cached", "--name-only"):
        raise PublishError("real Git index did not synchronize after publication")
    if push:
        _record_pending_push(repository, git)
        _push_pending(repository, git)
    return PublishResult(True, push, staged)


@contextmanager
def _isolated_index(repo: Path, git: GitRunner):
    index_path = _git_path(repo, git, "index")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="project-atlas-index-",
        dir=index_path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    environment = {"GIT_INDEX_FILE": str(temporary)}
    try:
        git.run(repo, "read-tree", "HEAD", env=environment)
        yield environment
    finally:
        temporary.unlink(missing_ok=True)


def _require_bundle_only(paths: Sequence[str]) -> None:
    if any(path != PUBLISH_ROOT and not path.startswith(f"{PUBLISH_ROOT}/") for path in paths):
        raise PublishError("refusing non-bundle staged paths")


def _git_path(repo: Path, git: GitRunner, name: str) -> Path:
    value = Path(git.run(repo, "rev-parse", "--git-path", name))
    return value if value.is_absolute() else repo / value


def _pending_path(repo: Path, git: GitRunner) -> Path:
    return _git_path(repo, git, _PENDING_PUSH)


def _record_pending_push(repo: Path, git: GitRunner) -> None:
    target = _pending_path(repo, git)
    if target.is_symlink():
        raise PublishError("pending push marker must not be a symlink")
    head = git.run(repo, "rev-parse", "HEAD")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{_PENDING_PUSH}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            descriptor = -1
            handle.write(f"{head}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
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
    expected = target.read_text(encoding="ascii").strip()
    if not expected or expected != git.run(repo, "rev-parse", "HEAD"):
        raise PublishError("pending push no longer matches HEAD")
    _require_bundle_only(
        git.lines(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    )
    _push_pending(repo, git)
    return True


def _push_pending(repo: Path, git: GitRunner) -> None:
    git.run(repo, "push", "origin", "HEAD")
    _pending_path(repo, git).unlink(missing_ok=True)


def _commit_message(project_ids: Sequence[str]) -> str:
    listed = ", ".join(project_ids[:3])
    suffix = "" if len(project_ids) <= 3 else f" +{len(project_ids) - 3}"
    return f"content: update project atlas ({listed}{suffix})"
