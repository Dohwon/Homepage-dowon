from __future__ import annotations

from pathlib import Path

import pytest

from atlas_worker.captures import load_project_captures
from atlas_worker.models import ProjectRef
from atlas_worker.privacy import PrivacyGate


PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def _ref(root: Path) -> ProjectRef:
    return ProjectRef("todack", "Todack", root, "projects/todack", "active", "public", ())


def test_load_project_captures_only_reads_registered_files(tmp_path):
    root = tmp_path / "todack"
    atlas = root / "project_memory/project-atlas"
    (atlas / "captures").mkdir(parents=True)
    (atlas / "captures/home.png").write_bytes(PNG_BYTES)
    (atlas / "unregistered.png").write_bytes(PNG_BYTES)
    (atlas / "captures.yaml").write_text(
        "captures:\n  - id: home\n    path: captures/home.png\n    alt: Todack 홈 화면\n    caption: 감정 기록 홈\n    role: overview\n",
        encoding="utf-8",
    )

    captures = load_project_captures(_ref(root), PrivacyGate(alias_key=b"capture-test-key-32-bytes-long"))

    assert [item.capture_id for item in captures] == ["home"]
    assert captures[0].content == PNG_BYTES


def test_legacy_cover_is_available_as_one_capture(tmp_path):
    root = tmp_path / "todack"
    atlas = root / "project_memory/project-atlas"
    atlas.mkdir(parents=True)
    (atlas / "cover.png").write_bytes(PNG_BYTES)

    captures = load_project_captures(_ref(root), PrivacyGate(alias_key=b"capture-test-key-32-bytes-long"))

    assert [(item.capture_id, item.role) for item in captures] == [("cover", "overview")]


def test_capture_path_cannot_escape_project(tmp_path):
    root = tmp_path / "todack"
    atlas = root / "project_memory/project-atlas"
    atlas.mkdir(parents=True)
    (atlas / "captures.yaml").write_text(
        "captures:\n  - id: secret\n    path: ../../secret.png\n    alt: secret\n    caption: secret\n    role: overview\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stay inside"):
        load_project_captures(_ref(root), PrivacyGate(alias_key=b"capture-test-key-32-bytes-long"))
