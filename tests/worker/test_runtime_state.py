import json
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


def test_second_worker_cannot_take_lock(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = RuntimeState.open(workspace, config_home=tmp_path / ".config")

    with state.lock():
        with pytest.raises(WorkerAlreadyRunning, match="already running"):
            with state.lock(blocking=False):
                pass


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

    def fail_replace(source, target):
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
