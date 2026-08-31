"""Private, deterministic source manifests for Atlas project evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
from typing import Protocol

import yaml

from .fs_safety import hash_confined_file, read_confined_text, require_confined_directory
from .manifest import canonical_hash, require_no_symlink_path
from .models import ProjectRef


SOURCE_PATTERNS = (
    ("spec", ("docs/superpowers/specs/**/*.md", "docs/specs/**/*.md")),
    ("plan", ("docs/superpowers/plans/**/*.md", "docs/plans/**/*.md")),
    ("test", ("tests/**/*", "test/**/*", "e2e/**/*")),
    ("project_memory", ("project_memory/**/*.md", "project_memory/**/*.yaml")),
    ("manager_memory", ("manager_memory/**/*.md",)),
    ("source", ("src/**/*", "app/**/*", "lib/**/*", "*.py", "*.js", "*.ts")),
)

_SKIPPED_DIRECTORIES = frozenset(
    {".git", ".pytest_cache", "__pycache__", "node_modules"}
)
_PREDECESSOR_ID = "project_id"


class GitRunner(Protocol):
    """Small injectable boundary around the Git command-line client."""

    def run(self, cwd: Path, *args: str) -> str:
        """Return stripped command output or an empty string when Git has no value."""

    def is_ignored(self, cwd: Path, path: Path) -> bool:
        """Return whether Git explicitly ignores the relative project path."""


class SubprocessGitRunner:
    """GitRunner implementation for local, read-only Git metadata queries."""

    def run(self, cwd: Path, *args: str) -> str:
        try:
            completed = subprocess.run(
                ("git", *args),
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return ""
        return completed.stdout.strip() if completed.returncode == 0 else ""

    def is_ignored(self, cwd: Path, path: Path) -> bool:
        try:
            completed = subprocess.run(
                ("git", "check-ignore", "--quiet", "--", path.as_posix()),
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False
        return completed.returncode == 0


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    content_hash: str
    source_class: str
    project_id: str


@dataclass(frozen=True)
class SourceManifest:
    project_id: str
    files: tuple[SourceFile, ...]
    predecessor_ids: tuple[str, ...]
    git_head_fingerprint: str
    git_common_dir_fingerprint: str

    def audit_payload(self) -> dict[str, object]:
        """Return a relative-path-free summary suitable for command output."""
        counts = Counter(item.source_class for item in self.files)
        return {
            "project_id": self.project_id,
            "files": {"count": len(self.files), "by_class": dict(sorted(counts.items()))},
            "content_hash": canonical_hash(
                {item.relative_path: item.content_hash for item in self.files}
            ),
        }


def build_source_manifest(project: ProjectRef, runner: GitRunner) -> SourceManifest:
    """Hash a project's regular files without exposing local paths or Git values."""
    root = project.root
    read_boundary = root.parent if project.standalone_asset else root
    files = tuple(
        SourceFile(
            relative_path=relative_path,
            content_hash=_content_hash(path, read_boundary),
            source_class=_source_class(relative_path),
            project_id=project.project_id,
        )
        for relative_path, path in _project_files(root, project.standalone_asset, runner)
    )
    return SourceManifest(
        project_id=project.project_id,
        files=files,
        predecessor_ids=_reviewed_predecessors(root, project.standalone_asset),
        git_head_fingerprint=_fingerprint(runner.run(root, "rev-parse", "HEAD")),
        git_common_dir_fingerprint=_fingerprint(
            _git_common_dir(root, runner) or ""
        ),
    )


def resolve_git_owner(
    path: Path,
    projects: Sequence[ProjectRef],
    runner: GitRunner,
) -> str | None:
    """Resolve a worktree only when exactly one project shares its common Git dir."""
    candidate = _git_common_dir(path, runner)
    if candidate is None:
        return None
    owners = {
        project.project_id
        for project in projects
        if _git_common_dir(project.root, runner) == candidate
    }
    return next(iter(owners)) if len(owners) == 1 else None


def _project_files(
    root: Path,
    standalone_asset: bool,
    runner: GitRunner,
) -> Iterator[tuple[str, Path]]:
    if standalone_asset:
        if not root.exists():
            return
        boundary = root.parent
        require_confined_directory(boundary, boundary)
        yield root.name, root
        return
    if not root.exists():
        return
    require_confined_directory(root, root)
    yield from _walk_project_files(root, root, runner)


def _walk_project_files(
    root: Path,
    directory: Path,
    runner: GitRunner,
) -> Iterator[tuple[str, Path]]:
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        path = Path(entry.path)
        if entry.name == ".git":
            continue
        mode = entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            if runner.is_ignored(root, path.relative_to(root)):
                continue
            raise ValueError("source manifest contains symlink")
        if stat.S_ISDIR(mode):
            if entry.name not in _SKIPPED_DIRECTORIES:
                yield from _walk_project_files(root, path, runner)
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("source manifest contains unsupported file")
        yield path.relative_to(root).as_posix(), path


def _content_hash(path: Path, root: Path) -> str:
    return hash_confined_file(path, root)


def _source_class(relative_path: str) -> str:
    path = Path(relative_path)
    if relative_path.startswith("docs/superpowers/specs/") and path.suffix == ".md":
        return "spec"
    if relative_path.startswith("docs/specs/") and path.suffix == ".md":
        return "spec"
    if relative_path.startswith("docs/superpowers/plans/") and path.suffix == ".md":
        return "plan"
    if relative_path.startswith("docs/plans/") and path.suffix == ".md":
        return "plan"
    if relative_path.startswith(("tests/", "test/", "e2e/")):
        return "test"
    if relative_path.startswith("project_memory/") and path.suffix in {".md", ".yaml"}:
        return "project_memory"
    if relative_path.startswith("manager_memory/") and path.suffix == ".md":
        return "manager_memory"
    return "source"


def _reviewed_predecessors(root: Path, standalone_asset: bool) -> tuple[str, ...]:
    if standalone_asset or not root.is_dir():
        return ()
    article = _read_yaml_mapping(root / "project_memory/project-atlas/article.yaml", root)
    relations = _read_yaml_mapping(root / "project_memory/project-atlas/relations.yaml", root)
    values: set[str] = set()
    prior_context = article.get("prior_context")
    if isinstance(prior_context, dict):
        _add_predecessor(values, prior_context.get(_PREDECESSOR_ID))
    for key in ("predecessor_ids", "predecessors"):
        relation = relations.get(key)
        if isinstance(relation, (list, tuple)):
            for item in relation:
                _add_predecessor(values, item.get(_PREDECESSOR_ID) if isinstance(item, dict) else item)
    return tuple(sorted(values))


def _read_yaml_mapping(path: Path, root: Path) -> dict[str, object]:
    try:
        content = read_confined_text(path, root)
    except FileNotFoundError:
        return {}
    value = yaml.safe_load(content)
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("reviewed project relation must be a mapping")
    return dict(value)


def _add_predecessor(values: set[str], value: object) -> None:
    if isinstance(value, str) and value.strip():
        values.add(value.strip())


def _git_common_dir(path: Path, runner: GitRunner) -> str | None:
    value = runner.run(path, "rev-parse", "--git-common-dir").strip()
    if not value:
        return None
    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(os.fspath(path), value))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""
