"""Exclusive, atomic local state for the Project Atlas worker."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Iterator


class WorkerAlreadyRunning(OSError):
    """Raised when another worker owns the workspace lock."""


@dataclass(frozen=True)
class RuntimeState:
    workspace_root: Path
    state_root: Path
    hmac_key_path: Path

    @property
    def state_path(self) -> Path:
        return self.state_root / "runtime-state.json"

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
        self.state_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_root / "worker.lock"
        with lock_path.open("a+b") as handle:
            mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(handle, mode)
            except BlockingIOError as error:
                raise WorkerAlreadyRunning("Project Atlas worker already running") from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load_hmac_key(self) -> bytes:
        parent = self.hmac_key_path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent.chmod(0o700)
        if not self.hmac_key_path.exists():
            descriptor = os.open(
                self.hmac_key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as target:
                target.write(secrets.token_bytes(32))
                target.flush()
                os.fsync(target.fileno())
        metadata = self.hmac_key_path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("HMAC key must be a regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError("HMAC key permissions must be 0600")
        key = self.hmac_key_path.read_bytes()
        if len(key) < 32:
            raise ValueError("HMAC key must contain at least 32 bytes")
        return key

    def changed_project_ids(
        self,
        *,
        source_hashes: Mapping[str, str],
        audit_hashes: Mapping[str, str],
    ) -> tuple[str, ...]:
        previous = self.load_success()
        prior_sources = previous.get("source_hashes", {})
        prior_audits = previous.get("audit_hashes", {})
        project_ids = set(prior_sources) | set(prior_audits) | set(source_hashes) | set(audit_hashes)
        return tuple(
            sorted(
                project_id
                for project_id in project_ids
                if prior_sources.get(project_id) != source_hashes.get(project_id)
                or prior_audits.get(project_id) != audit_hashes.get(project_id)
            )
        )

    def load_success(self) -> dict[str, object]:
        if not self.state_path.is_file():
            return {}
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid Project Atlas runtime state")
        for key in ("source_hashes", "audit_hashes"):
            hashes = value.get(key, {})
            if not isinstance(hashes, dict) or any(
                not isinstance(project_id, str) or not isinstance(digest, str)
                for project_id, digest in hashes.items()
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
    ) -> None:
        payload = {
            "audit_hashes": _validated_hashes(audit_hashes),
            "last_good_manifest": dict(manifest),
            "source_hashes": _validated_hashes(source_hashes),
        }
        self.state_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime-state.",
            suffix=".tmp",
            dir=self.state_root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                json.dump(payload, target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.state_path)
            _fsync_directory(self.state_root)
        finally:
            temporary.unlink(missing_ok=True)


def _validated_hashes(value: Mapping[str, str]) -> dict[str, str]:
    if any(
        not isinstance(project_id, str) or not isinstance(digest, str)
        for project_id, digest in value.items()
    ):
        raise ValueError("runtime hashes must be string mappings")
    return dict(sorted(value.items()))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
