"""Exclusive, atomic local state for the Project Atlas worker."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Iterator

class WorkerAlreadyRunning(OSError):
    """Raised when another worker owns the workspace lock."""


@dataclass
class RuntimeState:
    workspace_root: Path
    state_root: Path
    hmac_key_path: Path
    _state_dir_fd: int | None = field(default=None, init=False, repr=False)
    _lock_fd: int | None = field(default=None, init=False, repr=False)

    @property
    def state_path(self) -> Path:
        return self.state_root / "runtime-state.json"

    @property
    def is_locked(self) -> bool:
        return self._lock_fd is not None

    @classmethod
    def open(
        cls,
        workspace_root: Path,
        *,
        config_home: Path | None = None,
    ) -> "RuntimeState":
        workspace = Path(workspace_root).expanduser().resolve()
        secret_root = Path(
            config_home
            if config_home is not None
            else os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ).expanduser()
        return cls(
            workspace_root=workspace,
            state_root=workspace / ".knowledge-worker",
            hmac_key_path=secret_root / "project-atlas" / "hmac.key",
        )

    @contextmanager
    def lock(self, *, blocking: bool = False) -> Iterator[None]:
        if self.is_locked:
            raise WorkerAlreadyRunning("Project Atlas worker already running")
        state_descriptor = self._open_state_directory(create=True)
        lock_descriptor = -1
        try:
            mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(state_descriptor, mode)
            except BlockingIOError as error:
                raise WorkerAlreadyRunning("Project Atlas worker already running") from error
            lock_descriptor = _open_regular_at(
                state_descriptor,
                "worker.lock",
                os.O_RDWR | os.O_CREAT,
                mode=0o600,
            )
            _require_same_directory_entry(state_descriptor, "worker.lock", lock_descriptor)
            self._state_dir_fd = state_descriptor
            self._lock_fd = state_descriptor
            yield
        finally:
            self._lock_fd = None
            self._state_dir_fd = None
            if lock_descriptor >= 0:
                os.close(lock_descriptor)
            fcntl.flock(state_descriptor, fcntl.LOCK_UN)
            os.close(state_descriptor)

    def load_hmac_key(self) -> bytes:
        parent = self.hmac_key_path.parent
        with _open_directory_chain(parent, create=True) as parent_descriptor:
            os.fchmod(parent_descriptor, 0o700)
            try:
                descriptor = _open_regular_at(
                    parent_descriptor,
                    self.hmac_key_path.name,
                    os.O_RDONLY,
                )
            except FileNotFoundError:
                try:
                    descriptor = _open_regular_at(
                        parent_descriptor,
                        self.hmac_key_path.name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        mode=0o600,
                    )
                except FileExistsError:
                    descriptor = _open_regular_at(
                        parent_descriptor,
                        self.hmac_key_path.name,
                        os.O_RDONLY,
                    )
                else:
                    with os.fdopen(descriptor, "wb") as target:
                        descriptor = -1
                        target.write(secrets.token_bytes(32))
                        target.flush()
                        os.fsync(target.fileno())
                    os.fsync(parent_descriptor)
                    descriptor = _open_regular_at(
                        parent_descriptor,
                        self.hmac_key_path.name,
                        os.O_RDONLY,
                    )
            try:
                key = _read_key_descriptor(descriptor)
                _require_same_directory_entry(
                    parent_descriptor,
                    self.hmac_key_path.name,
                    descriptor,
                )
                return key
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

    def changed_project_ids(
        self,
        *,
        audit_hashes: Mapping[str, str],
        source_hashes: Mapping[str, str] | None = None,
        dependency_hashes: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        previous = self.load_success()
        prior_sources = previous.get("source_hashes", {})
        prior_audits = previous.get("audit_hashes", {})
        prior_dependencies = previous.get("dependency_hashes", {})
        if dependency_hashes is not None and dict(prior_dependencies) != dict(dependency_hashes):
            return tuple(sorted(set(audit_hashes) | set(source_hashes or {})))
        project_ids = set(prior_audits) | set(audit_hashes)
        if source_hashes is not None:
            project_ids |= set(prior_sources) | set(source_hashes)
        return tuple(
            sorted(
                project_id
                for project_id in project_ids
                if prior_audits.get(project_id) != audit_hashes.get(project_id)
                or (
                    source_hashes is not None
                    and prior_sources.get(project_id) != source_hashes.get(project_id)
                )
            )
        )

    def load_success(self) -> dict[str, object]:
        try:
            with self._state_directory(create=False) as state_descriptor:
                try:
                    descriptor = _open_regular_at(
                        state_descriptor,
                        "runtime-state.json",
                        os.O_RDONLY,
                    )
                except FileNotFoundError:
                    return {}
                try:
                    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
                        descriptor = -1
                        value = json.load(source)
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                self._verify_state_directory(state_descriptor)
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise ValueError("invalid Project Atlas runtime state")
        for key in ("source_hashes", "audit_hashes", "dependency_hashes"):
            hashes = value.get(key, {})
            if not isinstance(hashes, dict) or any(
                not isinstance(project_id, str) or not isinstance(digest, str)
                for project_id, digest in hashes.items()
            ):
                raise ValueError("invalid Project Atlas runtime state")
        relation_dependencies = value.get("relation_dependencies", {})
        if not isinstance(relation_dependencies, dict) or any(
            not isinstance(project_id, str)
            or not isinstance(targets, list)
            or any(not isinstance(target, str) for target in targets)
            for project_id, targets in relation_dependencies.items()
        ):
            raise ValueError("invalid Project Atlas runtime state")
        manifest = value.get("last_good_manifest", {})
        if not isinstance(manifest, dict):
            raise ValueError("invalid Project Atlas runtime state")
        return value

    def save_success(
        self,
        *,
        source_hashes: Mapping[str, str],
        audit_hashes: Mapping[str, str],
        manifest: Mapping[str, object],
        dependency_hashes: Mapping[str, str] | None = None,
        relation_dependencies: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        payload = {
            "audit_hashes": _validated_hashes(audit_hashes),
            "dependency_hashes": _validated_hashes(dependency_hashes or {}),
            "last_good_manifest": dict(manifest),
            "relation_dependencies": {
                project_id: list(targets)
                for project_id, targets in sorted((relation_dependencies or {}).items())
            },
            "source_hashes": _validated_hashes(source_hashes),
        }
        self._write_payload(payload)

    def restore_success(self, payload: Mapping[str, object]) -> None:
        if not payload:
            with self._state_directory(create=True) as state_descriptor:
                try:
                    os.unlink("runtime-state.json", dir_fd=state_descriptor)
                except FileNotFoundError:
                    pass
                os.fsync(state_descriptor)
            return
        self._write_payload(dict(payload))

    def _write_payload(self, payload: Mapping[str, object]) -> None:
        encoded = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        with self._state_directory(create=True) as state_descriptor:
            self._verify_state_directory(state_descriptor)
            _require_regular_destination(state_descriptor, "runtime-state.json")
            temporary_name, descriptor = _create_temporary_state_file(state_descriptor)
            try:
                with os.fdopen(descriptor, "wb") as target:
                    descriptor = -1
                    target.write(encoded)
                    target.flush()
                    os.fsync(target.fileno())
                self._verify_state_directory(state_descriptor)
                os.replace(
                    temporary_name,
                    "runtime-state.json",
                    src_dir_fd=state_descriptor,
                    dst_dir_fd=state_descriptor,
                )
                os.fsync(state_descriptor)
                self._verify_state_directory(state_descriptor)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                try:
                    os.unlink(temporary_name, dir_fd=state_descriptor)
                except FileNotFoundError:
                    pass

    @contextmanager
    def _state_directory(self, *, create: bool) -> Iterator[int]:
        if self._state_dir_fd is not None:
            self._verify_state_directory(self._state_dir_fd)
            yield self._state_dir_fd
            return
        descriptor = self._open_state_directory(create=create)
        try:
            yield descriptor
        finally:
            os.close(descriptor)

    def _open_state_directory(self, *, create: bool) -> int:
        workspace_descriptor = os.open(self.workspace_root, _directory_open_flags())
        try:
            if create:
                try:
                    os.mkdir(".knowledge-worker", mode=0o700, dir_fd=workspace_descriptor)
                except FileExistsError:
                    pass
            descriptor = os.open(
                ".knowledge-worker",
                _directory_open_flags(),
                dir_fd=workspace_descriptor,
            )
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise ValueError("Project Atlas state root must be a directory")
            return descriptor
        finally:
            os.close(workspace_descriptor)

    def _verify_state_directory(self, descriptor: int) -> None:
        current = self._open_state_directory(create=False)
        try:
            opened = os.fstat(descriptor)
            visible = os.fstat(current)
            if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
                raise OSError("Project Atlas state root changed during operation")
        finally:
            os.close(current)


def read_hmac_key_file(path: Path, *, strip_line_endings: bool = False) -> bytes:
    """Read an existing owner-only HMAC key without following the final path."""
    candidate = Path(path).expanduser()
    with _open_directory_chain(candidate.parent) as parent_descriptor:
        descriptor = _open_regular_at(parent_descriptor, candidate.name, os.O_RDONLY)
        try:
            key = _read_key_descriptor(descriptor, strip_line_endings=strip_line_endings)
            _require_same_directory_entry(parent_descriptor, candidate.name, descriptor)
            return key
        finally:
            os.close(descriptor)


def _validated_hashes(value: Mapping[str, str]) -> dict[str, str]:
    if any(
        not isinstance(project_id, str) or not isinstance(digest, str)
        for project_id, digest in value.items()
    ):
        raise ValueError("runtime hashes must be string mappings")
    return dict(sorted(value.items()))


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _regular_open_flags(flags: int) -> int:
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


@contextmanager
def _open_directory_chain(path: Path, *, create: bool = False) -> Iterator[int]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    parts = candidate.parts
    if not parts or any(part in {".", ".."} for part in parts[1:]):
        raise ValueError("HMAC key parent path is invalid")
    descriptor = os.open(parts[0], _directory_open_flags())
    try:
        for part in parts[1:]:
            try:
                child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _open_regular_at(
    directory_descriptor: int,
    name: str,
    flags: int,
    *,
    mode: int = 0o600,
) -> int:
    descriptor = os.open(
        name,
        _regular_open_flags(flags),
        mode,
        dir_fd=directory_descriptor,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise ValueError("Project Atlas state file must be regular")
    return descriptor


def _require_same_directory_entry(directory_descriptor: int, name: str, descriptor: int) -> None:
    visible = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(visible.st_mode) or (visible.st_dev, visible.st_ino) != (
        opened.st_dev,
        opened.st_ino,
    ):
        raise OSError("Project Atlas state file changed during operation")


def _require_regular_destination(directory_descriptor: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Project Atlas state destination must be regular")


def _create_temporary_state_file(directory_descriptor: int) -> tuple[str, int]:
    for _ in range(32):
        name = f".runtime-state.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = _open_regular_at(
                directory_descriptor,
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                mode=0o600,
            )
        except FileExistsError:
            continue
        return name, descriptor
    raise FileExistsError(errno.EEXIST, "could not allocate Project Atlas state file")


def _read_key_descriptor(descriptor: int, *, strip_line_endings: bool = False) -> bytes:
    metadata = os.fstat(descriptor)
    _require_regular_hmac_metadata(metadata)
    key = os.read(descriptor, max(metadata.st_size, 1) + 1)
    if strip_line_endings:
        key = key.rstrip(b"\r\n")
    if len(key) < 32:
        raise ValueError("HMAC key must contain at least 32 bytes")
    return key


def _require_regular_hmac_metadata(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("HMAC key must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("HMAC key permissions must be 0600")
