import json
import os
import stat

import pytest

from atlas_worker.runtime_state import RuntimeState, WorkerAlreadyRunning


def test_hmac_key_is_created_outside_repo_with_owner_only_permissions(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")

    key = state.load_hmac_key()

    assert len(key) == 32
    assert stat.S_IMODE(state.hmac_key_path.stat().st_mode) == 0o600
    assert not state.hmac_key_path.is_relative_to(workspace)


def test_hmac_key_rejects_weak_permissions_and_short_content(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.hmac_key_path.parent.mkdir(parents=True)
    state.hmac_key_path.write_bytes(b"short")
    state.hmac_key_path.chmod(0o644)

    with pytest.raises(ValueError, match="HMAC key"):
        state.load_hmac_key()


def test_hmac_key_symlink_cannot_redirect_secret_read(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    external = tmp_path / "external.key"
    external.write_bytes(b"x" * 32)
    external.chmod(0o600)
    state.hmac_key_path.parent.mkdir(parents=True)
    state.hmac_key_path.symlink_to(external)

    with pytest.raises((OSError, ValueError)):
        state.load_hmac_key()

    assert external.read_bytes() == b"x" * 32


def test_second_worker_cannot_take_lock(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")

    with state.lock():
        with pytest.raises(WorkerAlreadyRunning, match="already running"):
            with state.lock(blocking=False):
                pass


def test_state_root_symlink_cannot_redirect_worker_lock(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "external-state"
    external.mkdir()
    (workspace / ".knowledge-worker").symlink_to(external, target_is_directory=True)
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")

    with pytest.raises((OSError, ValueError)):
        with state.lock():
            pass

    assert not (external / "worker.lock").exists()


def test_worker_lock_symlink_cannot_redirect_lock_descriptor(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.state_root.mkdir()
    external = tmp_path / "external.lock"
    external.write_bytes(b"outside")
    (state.state_root / "worker.lock").symlink_to(external)

    with pytest.raises((OSError, ValueError)):
        with state.lock():
            pass

    assert external.read_bytes() == b"outside"


def test_changed_projects_compare_source_and_audit_hashes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.save_success(
        source_hashes={"alpha": "source-a", "beta": "source-b"},
        audit_hashes={"alpha": "audit-a", "beta": "audit-b"},
        manifest={"version": "last-good", "projects": ["alpha", "beta"]},
    )

    changed = state.changed_project_ids(
        source_hashes={"alpha": "source-a", "beta": "source-b2", "gamma": "source-c"},
        audit_hashes={"alpha": "audit-a2", "beta": "audit-b", "gamma": "audit-c"},
    )

    assert changed == ("alpha", "beta", "gamma")


def test_global_dependency_change_invalidates_every_current_project(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.save_success(
        source_hashes={"alpha": "source-a", "beta": "source-b"},
        audit_hashes={"alpha": "audit-a", "beta": "audit-b"},
        dependency_hashes={"config": "config-a", "schema": "schema-a", "taxonomy": "taxonomy-a"},
        manifest={"version": "last-good", "projects": ["alpha", "beta"]},
    )

    unchanged = state.changed_project_ids(
        audit_hashes={"alpha": "audit-a", "beta": "audit-b"},
        dependency_hashes={"config": "config-a", "schema": "schema-a", "taxonomy": "taxonomy-a"},
    )
    invalidated = state.changed_project_ids(
        audit_hashes={"alpha": "audit-a", "beta": "audit-b"},
        dependency_hashes={"config": "config-a", "schema": "schema-b", "taxonomy": "taxonomy-a"},
    )

    assert unchanged == ()
    assert invalidated == ("alpha", "beta")


def test_runtime_state_symlink_cannot_redirect_last_good_read(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.state_root.mkdir()
    external = tmp_path / "external-state.json"
    external.write_text('{"last_good_manifest":{"version":"outside"}}', encoding="utf-8")
    state.state_path.symlink_to(external)

    with pytest.raises((OSError, ValueError)):
        state.load_success()


def test_success_state_is_atomic_and_preserves_last_good_on_failed_write(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    state.save_success(
        source_hashes={"alpha": "source-a"},
        audit_hashes={"alpha": "audit-a"},
        manifest={"version": "first", "projects": ["alpha"]},
    )
    before = state.state_path.read_bytes()

    def fail_replace(source, target, **kwargs):
        raise OSError("injected replace failure")

    monkeypatch.setattr("atlas_worker.runtime_state.os.replace", fail_replace)
    with pytest.raises(OSError):
        state.save_success(
            source_hashes={"alpha": "source-b"},
            audit_hashes={"alpha": "audit-b"},
            manifest={"version": "second", "projects": ["alpha"]},
        )

    assert state.state_path.read_bytes() == before
    assert json.loads(before)["last_good_manifest"]["version"] == "first"
    assert not tuple(state.state_root.glob(".runtime-state.*.tmp"))


def test_state_root_swap_during_lock_does_not_redirect_state_write(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")
    external = tmp_path / "external-state"
    external.mkdir()

    with state.lock():
        detached = tmp_path / "detached-state"
        os.rename(state.state_root, detached)
        state.state_root.symlink_to(external, target_is_directory=True)
        with pytest.raises((OSError, ValueError)):
            state.save_success(
                source_hashes={"alpha": "source-a"},
                audit_hashes={"alpha": "audit-a"},
                manifest={"version": "candidate", "projects": ["alpha"]},
            )

    assert not (external / "runtime-state.json").exists()
