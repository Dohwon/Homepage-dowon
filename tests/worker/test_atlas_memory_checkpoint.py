from pathlib import Path

from scripts.audit_atlas_memory_checkpoint import (
    VALID_ADAPTER_POINTER,
    VALID_GLOBAL_CHECKPOINT,
    VALID_WORKSPACE_POINTER,
    audit_checkpoint,
)


def _files(tmp_path: Path, global_text: str, workspace_text: str, adapter_text: str):
    global_path = tmp_path / "global.md"
    workspace_path = tmp_path / "workspace.md"
    adapter_path = tmp_path / "adapter.md"
    global_path.write_text(global_text, encoding="utf-8")
    workspace_path.write_text(workspace_text, encoding="utf-8")
    adapter_path.write_text(adapter_text, encoding="utf-8")
    return global_path, workspace_path, adapter_path


def test_missing_atlas_checkpoint_is_reported(tmp_path):
    files = _files(tmp_path, "", "", "")

    codes = {item.code for item in audit_checkpoint(*files)}

    assert "missing-project-atlas-checkpoint" in codes
    assert "missing-workspace-checkpoint-pointer" in codes
    assert "missing-adapter-checkpoint-pointer" in codes


def test_workspace_copy_is_reported(tmp_path):
    files = _files(
        tmp_path,
        VALID_GLOBAL_CHECKPOINT,
        VALID_GLOBAL_CHECKPOINT,
        VALID_ADAPTER_POINTER,
    )

    assert "duplicated-global-checkpoint" in {
        item.code for item in audit_checkpoint(*files)
    }


def test_canonical_checkpoint_and_two_short_pointers_pass(tmp_path):
    files = _files(
        tmp_path,
        VALID_GLOBAL_CHECKPOINT,
        VALID_WORKSPACE_POINTER,
        VALID_ADAPTER_POINTER,
    )

    assert audit_checkpoint(*files) == ()


def test_checkpoint_missing_fail_closed_audit_rule_is_incomplete(tmp_path):
    incomplete = VALID_GLOBAL_CHECKPOINT.replace(
        "Audit the changed project.",
        "Publish the changed project.",
    )
    files = _files(
        tmp_path,
        incomplete,
        VALID_WORKSPACE_POINTER,
        VALID_ADAPTER_POINTER,
    )

    assert "incomplete-project-atlas-checkpoint" in {
        item.code for item in audit_checkpoint(*files)
    }
