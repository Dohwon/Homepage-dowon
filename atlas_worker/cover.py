"""Load one explicitly reviewed representative implementation image per project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fs_safety import read_confined_bytes
from .models import ProjectRef
from .privacy import PrivacyGate


_COVER_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MAX_COVER_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ProjectCover:
    alt: str
    caption: str
    content_type: str
    content: bytes

    def to_public_dict(self) -> dict[str, str]:
        return {
            "alt": self.alt,
            "caption": self.caption,
            "content_type": self.content_type,
            "content_hex": self.content.hex(),
        }


def load_project_cover(ref: ProjectRef, gate: PrivacyGate) -> ProjectCover | None:
    if ref.standalone_asset:
        return None
    directory = ref.root / "project_memory" / "project-atlas"
    candidates = tuple(path for suffix in _COVER_TYPES for path in (directory / f"cover{suffix}",) if path.exists())
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("project cover must have exactly one image")
    path = candidates[0]
    content = read_confined_bytes(path, ref.root, gate, max_bytes=_MAX_COVER_BYTES)
    content_type = _COVER_TYPES[path.suffix.lower()]
    _validate_signature(content, content_type)
    return ProjectCover(
        alt=f"{ref.display_name} 구현 화면",
        caption="실제 구현 화면",
        content_type=content_type,
        content=content,
    )


def cover_from_public_dict(value: dict[str, object]) -> ProjectCover:
    if set(value) != {"alt", "caption", "content_type", "content_hex"}:
        raise ValueError("invalid public cover")
    alt = value["alt"]
    caption = value["caption"]
    content_type = value["content_type"]
    encoded = value["content_hex"]
    if not all(isinstance(item, str) and item for item in (alt, caption, content_type, encoded)):
        raise ValueError("invalid public cover")
    try:
        content = bytes.fromhex(encoded)
    except ValueError:
        raise ValueError("invalid public cover") from None
    if len(content) > _MAX_COVER_BYTES:
        raise ValueError("invalid public cover")
    _validate_signature(content, content_type)
    return ProjectCover(alt, caption, content_type, content)


def _validate_signature(content: bytes, content_type: str) -> None:
    valid = (
        content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")
        or content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
        or content_type == "image/webp" and len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    )
    if not valid:
        raise ValueError("project cover content does not match its image type")
