"""Deterministic content hashes for Project Atlas bundles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Iterator, Mapping


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def project_hashes_from_files(
    projects: tuple[str, ...],
    files: Mapping[str, str],
) -> dict[str, str]:
    return {
        project_id: canonical_hash(
            {
                path: digest
                for path, digest in files.items()
                if path.startswith(f"projects/{project_id}/")
            }
        )
        for project_id in projects
    }


def content_version(
    files: Mapping[str, str],
    project_hashes: Mapping[str, str],
) -> str:
    """Derive a recomputable version only from staged public content hashes."""
    return canonical_hash(
        {
            "files": dict(sorted(files.items())),
            "projects": dict(sorted(project_hashes.items())),
        }
    )


def bundle_file_hashes(root: Path) -> dict[str, str]:
    return {
        relative_path: _file_hash(path)
        for relative_path, path in iter_tree_files(root)
        if relative_path != "manifest.json"
    }


def tree_hash(root: Path) -> str:
    """Hash a tree using only POSIX relative paths and file bytes."""
    digest = hashlib.sha256()
    for relative_path, path in iter_tree_files(root):
        encoded_path = relative_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(len(chunk).to_bytes(8, "big"))
                digest.update(chunk)
        digest.update((0).to_bytes(8, "big"))
    return digest.hexdigest()


def iter_tree_files(root: Path) -> Iterator[tuple[str, Path]]:
    root = Path(root)
    require_no_symlink_path(root)
    _require_real_directory(root)
    yield from _walk(root, root)


def require_no_symlink_path(path: Path) -> None:
    """Reject symlinks in every existing component without resolving them."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise ValueError(f"unsafe symlink path component: {current}")
        if current != absolute and not stat.S_ISDIR(mode):
            raise ValueError(f"unsafe non-directory path component: {current}")


def _walk(root: Path, directory: Path) -> Iterator[tuple[str, Path]]:
    entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    for entry in entries:
        path = Path(entry.path)
        mode = entry.stat(follow_symlinks=False).st_mode
        relative_path = path.relative_to(root).as_posix()
        if stat.S_ISLNK(mode):
            raise ValueError(f"bundle tree contains symlink: {relative_path}")
        if stat.S_ISDIR(mode):
            yield from _walk(root, path)
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"bundle tree contains unsupported entry: {relative_path}")
        yield relative_path, path


def _require_real_directory(root: Path) -> None:
    try:
        mode = root.lstat().st_mode
    except FileNotFoundError:
        raise ValueError(f"bundle tree does not exist: {root}") from None
    if stat.S_ISLNK(mode):
        raise ValueError(f"bundle tree root is a symlink: {root}")
    if not stat.S_ISDIR(mode):
        raise ValueError(f"bundle tree root is not a directory: {root}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
