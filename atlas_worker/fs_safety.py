"""No-follow filesystem boundaries for curated Atlas inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from collections.abc import Sequence

from .manifest import require_no_symlink_path
from .privacy import PrivacyGate


@dataclass(frozen=True)
class FileWrite:
    path: Path
    content: bytes
    root: Path


@dataclass(frozen=True)
class _FileSnapshot:
    content: bytes
    mode: int


def require_confined_directory(
    path: Path,
    root: Path,
    gate: PrivacyGate | None = None,
    *,
    allow_missing: bool = False,
) -> bool:
    candidate = _confined_absolute(path, root)
    require_no_symlink_path(candidate)
    try:
        mode = candidate.lstat().st_mode
    except FileNotFoundError:
        if allow_missing:
            return False
        raise ValueError("required directory is missing") from None
    if not stat.S_ISDIR(mode):
        raise ValueError("required path is not a directory")
    if gate is not None:
        gate.require_allowed_source(candidate)
    return True


def read_confined_text(
    path: Path,
    root: Path,
    gate: PrivacyGate | None = None,
    *,
    max_bytes: int | None = None,
) -> str:
    return read_confined_bytes(path, root, gate, max_bytes=max_bytes).decode("utf-8")


def read_confined_bytes(
    path: Path,
    root: Path,
    gate: PrivacyGate | None = None,
    *,
    max_bytes: int | None = None,
) -> bytes:
    if max_bytes is not None and (not isinstance(max_bytes, int) or max_bytes < 0):
        raise ValueError("max_bytes must be a non-negative integer")
    candidate = _confined_absolute(path, root)
    boundary = _absolute(root)
    if gate is not None:
        gate.require_allowed_source(candidate)
    descriptor = _open_confined_regular(candidate, boundary)
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        os.close(descriptor)
        raise ValueError("curated source is not a regular file")
    if max_bytes is not None and before.st_size > max_bytes:
        os.close(descriptor)
        raise ValueError("curated source exceeds byte limit")

    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
            if max_bytes is not None and len(content) > max_bytes:
                raise ValueError("curated source exceeds byte limit")
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if _file_identity(after) != _file_identity(before):
        raise ValueError("curated source changed during read")
    visible_descriptor = _open_confined_regular(candidate, boundary)
    try:
        if _file_identity(os.fstat(visible_descriptor)) != _file_identity(before):
            raise ValueError("curated source changed during read")
    finally:
        os.close(visible_descriptor)
    return content


def hash_confined_file(path: Path, root: Path) -> str:
    candidate = _confined_absolute(path, root)
    boundary = _absolute(root)
    descriptor = _open_confined_regular(candidate, boundary)
    before = os.fstat(descriptor)
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if _file_identity(after) != _file_identity(before):
        raise ValueError("curated source changed during read")
    visible_descriptor = _open_confined_regular(candidate, boundary)
    try:
        if _file_identity(os.fstat(visible_descriptor)) != _file_identity(before):
            raise ValueError("curated source changed during read")
    finally:
        os.close(visible_descriptor)
    return digest.hexdigest()


def _open_confined_regular(candidate: Path, boundary: Path) -> int:
    relative = candidate.relative_to(boundary)
    if not relative.parts:
        raise ValueError("curated source must name a file")
    directory_descriptor = _open_absolute_directory(boundary)
    try:
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, _directory_open_flags(), dir_fd=directory_descriptor)
                os.close(directory_descriptor)
                directory_descriptor = child
            descriptor = os.open(
                relative.parts[-1],
                _regular_open_flags(),
                dir_fd=directory_descriptor,
            )
        except OSError as error:
            _raise_unsafe_path(error)
    finally:
        os.close(directory_descriptor)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("curated source is not a regular file")
    return descriptor


def _open_absolute_directory(path: Path) -> int:
    absolute = _absolute(path)
    descriptor = os.open(absolute.anchor, _directory_open_flags())
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            except OSError as error:
                _raise_unsafe_path(error)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _raise_unsafe_path(error: OSError) -> None:
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        raise ValueError("curated source path contains a symlink or non-directory") from None
    raise error


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _regular_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def direct_regular_files(
    directory: Path,
    root: Path,
    gate: PrivacyGate | None = None,
    *,
    suffix: str,
) -> tuple[Path, ...]:
    if not require_confined_directory(directory, root, gate, allow_missing=True):
        return ()
    paths: list[Path] = []
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        if not entry.name.endswith(suffix):
            continue
        mode = entry.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError("curated source is not a regular file")
        path = Path(entry.path)
        require_no_symlink_path(path)
        if gate is not None:
            gate.require_allowed_source(path)
        paths.append(path)
    return tuple(paths)


def require_write_destination(path: Path, root: Path) -> Path:
    candidate = _confined_absolute(path, root)
    root_path = _absolute(root)
    require_no_symlink_path(root_path)
    if root_path.exists() and not stat.S_ISDIR(root_path.lstat().st_mode):
        raise ValueError("write root is not a directory")
    require_no_symlink_path(candidate)
    try:
        mode = candidate.lstat().st_mode
    except FileNotFoundError:
        return candidate
    if not stat.S_ISREG(mode):
        raise ValueError("write destination is not a regular file")
    return candidate


def commit_file_transaction(writes: Sequence[FileWrite]) -> tuple[Path, ...]:
    """Stage and atomically replace a complete write set, rolling back as a unit."""
    prepared: list[tuple[FileWrite, Path, _FileSnapshot | None]] = []
    seen: set[Path] = set()
    for write in writes:
        if not isinstance(write.content, bytes):
            raise TypeError("file transaction content must be bytes")
        path = require_write_destination(write.path, write.root)
        if path in seen:
            raise ValueError("file transaction contains a duplicate destination")
        seen.add(path)
        snapshot = _destination_snapshot(path, write.root)
        if snapshot is not None and snapshot.content == write.content:
            continue
        prepared.append((write, path, snapshot))
    if not prepared:
        return ()

    created_directories: list[Path] = []
    staged: dict[Path, Path] = {}
    committed: list[tuple[FileWrite, Path, _FileSnapshot | None]] = []
    try:
        for write, path, snapshot in prepared:
            _ensure_parent_directories(path.parent, write.root, created_directories)
            staged[path] = _stage_bytes(
                path,
                write.content,
                snapshot.mode if snapshot is not None else 0o600,
            )
        for item in prepared:
            _, path, _ = item
            _replace_file(staged[path], path)
            staged.pop(path)
            committed.append(item)
    except BaseException:
        rollback_error = _rollback_files(committed)
        cleanup_error = _cleanup_staged(tuple(staged.values()))
        directory_error = _cleanup_directories(created_directories)
        if rollback_error is not None or cleanup_error is not None or directory_error is not None:
            raise OSError("file transaction rollback failed") from None
        raise
    return tuple(path for _, path, _ in prepared)


def _destination_snapshot(path: Path, root: Path) -> _FileSnapshot | None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode):
        raise ValueError("write destination is not a regular file")
    return _FileSnapshot(
        content=read_confined_bytes(path, root),
        mode=stat.S_IMODE(mode),
    )


def _ensure_parent_directories(
    parent: Path,
    root: Path,
    created: list[Path],
) -> None:
    boundary = _absolute(root)
    candidate = _confined_absolute(parent, boundary)
    missing: list[Path] = []
    current = candidate
    while True:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            missing.append(current)
            if current == boundary:
                break
            current = current.parent
            continue
        if not stat.S_ISDIR(mode):
            raise ValueError("write ancestor is not a directory")
        break
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)


def _stage_bytes(path: Path, content: bytes, mode: int) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.atlas-txn-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as target:
            descriptor = -1
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return temporary


def _rollback_files(
    committed: list[tuple[FileWrite, Path, _FileSnapshot | None]],
) -> OSError | None:
    try:
        for _, path, snapshot in reversed(committed):
            if snapshot is None:
                mode = path.lstat().st_mode
                if not stat.S_ISREG(mode):
                    raise OSError("transaction target changed before rollback")
                path.unlink()
                continue
            temporary = _stage_bytes(path, snapshot.content, snapshot.mode)
            try:
                _replace_file(temporary, path)
            except BaseException:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                raise
    except OSError as error:
        return error
    return None


def _cleanup_staged(paths: tuple[Path, ...]) -> OSError | None:
    try:
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    except OSError as error:
        return error
    return None


def _cleanup_directories(paths: list[Path]) -> OSError | None:
    try:
        for path in reversed(paths):
            path.rmdir()
    except OSError as error:
        return error
    return None


def _replace_file(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _confined_absolute(path: Path, root: Path) -> Path:
    candidate = _absolute(path)
    boundary = _absolute(root)
    try:
        candidate.relative_to(boundary)
    except ValueError:
        raise ValueError("path escapes its filesystem boundary") from None
    return candidate


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))
