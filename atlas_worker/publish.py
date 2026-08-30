"""Allowlisted Git publication for an already-promoted Atlas bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Sequence

from .models import PromotionResult


PUBLISH_ROOT = "public-bundle"


class PublishError(ValueError):
    """Raised when publication would touch anything outside the bundle."""


@dataclass(frozen=True)
class PublishResult:
    committed: bool
    pushed: bool
    staged_paths: tuple[str, ...]
    deferred: bool = False


class GitRunner:
    def run(self, repo: Path, *args: str) -> str:
        try:
            completed = subprocess.run(
                ("git", *args),
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise PublishError("Git publication failed") from error
        return completed.stdout.strip()

    def lines(self, repo: Path, *args: str) -> tuple[str, ...]:
        return tuple(line for line in self.run(repo, *args).splitlines() if line)


def publish_bundle(
    repo: Path,
    promotion: PromotionResult,
    *,
    push: bool = False,
    runner: GitRunner | None = None,
) -> PublishResult:
    repository = Path(repo).resolve()
    git = runner or GitRunner()
    if not promotion.changed:
        return PublishResult(False, False, ())

    preexisting = git.lines(repository, "diff", "--cached", "--name-only")
    if preexisting:
        return PublishResult(False, False, (), deferred=True)

    tracked = git.lines(repository, "ls-files", "--", PUBLISH_ROOT)
    if not (repository / PUBLISH_ROOT).exists() and not tracked:
        return PublishResult(False, False, ())
    git.run(repository, "add", "--", PUBLISH_ROOT)
    staged = git.lines(repository, "diff", "--cached", "--name-only")
    forbidden = tuple(
        path
        for path in staged
        if path != PUBLISH_ROOT and not path.startswith(f"{PUBLISH_ROOT}/")
    )
    if forbidden:
        raise PublishError("refusing non-bundle staged paths")
    if not staged:
        return PublishResult(False, False, ())

    message = _commit_message(promotion.changed_projects)
    git.run(repository, "commit", "-m", message)
    if push:
        git.run(repository, "push", "origin", "HEAD")
    return PublishResult(True, push, staged)


def _commit_message(project_ids: Sequence[str]) -> str:
    listed = ", ".join(project_ids[:3])
    suffix = "" if len(project_ids) <= 3 else f" +{len(project_ids) - 3}"
    return f"content: update project atlas ({listed}{suffix})"
