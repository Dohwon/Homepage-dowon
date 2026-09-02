"""Load explicitly reviewed project implementation captures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from .cover import load_project_cover
from .fs_safety import read_confined_bytes, read_confined_text
from .models import ProjectRef, validate_schema
from .privacy import PrivacyGate


_IMAGE_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ProjectCapture:
    capture_id: str
    alt: str
    caption: str
    role: str
    content_type: str
    content: bytes

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.capture_id,
            "alt": self.alt,
            "caption": self.caption,
            "role": self.role,
            "content_type": self.content_type,
            "content_hex": self.content.hex(),
        }


def load_project_captures(ref: ProjectRef, gate: PrivacyGate) -> tuple[ProjectCapture, ...]:
    """Read only the reviewed manifest, falling back to the legacy cover."""
    if ref.standalone_asset:
        return ()
    atlas_dir = ref.root / "project_memory" / "project-atlas"
    manifest_path = atlas_dir / "captures.yaml"
    try:
        raw = yaml.safe_load(read_confined_text(manifest_path, ref.root, gate, max_bytes=256 * 1024))
    except FileNotFoundError:
        cover = load_project_cover(ref, gate)
        if cover is None:
            return ()
        return (ProjectCapture("cover", cover.alt, cover.caption, "overview", cover.content_type, cover.content),)
    if not isinstance(raw, dict):
        raise ValueError("project captures must be a mapping")
    validate_schema(raw, "project-captures")
    captures: list[ProjectCapture] = []
    seen: set[str] = set()
    for item in raw["captures"]:
        capture_id = item["id"]
        if capture_id in seen:
            raise ValueError("project capture IDs must be unique")
        seen.add(capture_id)
        relative_path = PurePosixPath(item["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("project capture path must stay inside project")
        path = atlas_dir.joinpath(*relative_path.parts)
        content_type = _IMAGE_TYPES.get(path.suffix.lower())
        if content_type is None:
            raise ValueError("project capture must be png, jpeg, or webp")
        content = read_confined_bytes(path, ref.root, gate, max_bytes=_MAX_CAPTURE_BYTES)
        _validate_signature(content, content_type)
        gate.require_safe({"alt": item["alt"], "caption": item["caption"], "role": item["role"]})
        captures.append(ProjectCapture(capture_id, item["alt"], item["caption"], item["role"], content_type, content))
    return tuple(captures)


def captures_from_public_dict(value: object) -> tuple[ProjectCapture, ...]:
    if not isinstance(value, list):
        raise ValueError("invalid public captures")
    validate_schema(value, "public-captures")
    captures: list[ProjectCapture] = []
    seen: set[str] = set()
    for item in value:
        if item["id"] in seen:
            raise ValueError("invalid public captures")
        seen.add(item["id"])
        try:
            content = bytes.fromhex(item["content_hex"])
        except ValueError:
            raise ValueError("invalid public captures") from None
        if len(content) > _MAX_CAPTURE_BYTES:
            raise ValueError("invalid public captures")
        _validate_signature(content, item["content_type"])
        captures.append(ProjectCapture(item["id"], item["alt"], item["caption"], item["role"], item["content_type"], content))
    return tuple(captures)


def _validate_signature(content: bytes, content_type: str) -> None:
    valid = (
        content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")
        or content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
        or content_type == "image/webp" and len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    )
    if not valid:
        raise ValueError("project capture content does not match its image type")
