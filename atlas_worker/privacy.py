"""Fail-closed privacy checks for Project Atlas public bundles."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re


SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
ABSOLUTE_PATH = re.compile(r"(?:/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
PRIVATE_IP = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
SOURCE_MAP = re.compile(r"(?:\bsourceMappingURL\s*=\s*\S+|\b[A-Za-z0-9_./-]+\.map\b)", re.I)
SAFE_ALIAS_PREFIX = re.compile(r"[A-Z][A-Z0-9_]*")
CONTENT_SHA256 = re.compile(r"[0-9a-f]{64}")

DENIED_SOURCE_NAMES = {".env", "credentials.json", "auth.json"}
DENIED_SOURCE_PARTS = {".codex/sessions", "logs", "raw-logs", "private-data"}
NON_STRING_KEY_POINTER = "<non-string-key>"


@dataclass(frozen=True)
class PrivacyFinding:
    category: str
    json_pointer: str


@dataclass(frozen=True)
class PrivacyReport:
    findings: tuple[PrivacyFinding, ...]


class PrivacyViolation(ValueError):
    """Raised when candidate public content violates the privacy boundary."""


def hmac_alias(value: str, key: bytes, prefix: str) -> str:
    """Return a deterministic public alias without retaining the source value."""
    if not isinstance(value, str):
        raise ValueError("alias value must be a string")
    _validate_alias_key(key)
    if not isinstance(prefix, str) or not SAFE_ALIAS_PREFIX.fullmatch(prefix):
        raise ValueError("alias prefix is invalid")

    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:8].upper()
    return f"{prefix}_{digest}"


class PrivacyGate:
    """Reject data that may not cross from local sources into public bundles."""

    def __init__(self, alias_key: bytes, approved_public_values: set[str] | frozenset[str] = frozenset()):
        self._alias_key = _validate_alias_key(alias_key)
        self._approved_public_values = frozenset(approved_public_values)

    def scan(self, record: object) -> PrivacyReport:
        findings: list[PrivacyFinding] = []
        self._scan_value(record, "", findings, allow_approved_value=True)
        return PrivacyReport(findings=tuple(findings))

    def require_safe(self, record: object) -> None:
        report = self.scan(record)
        if report.findings:
            categories = ", ".join(sorted({item.category for item in report.findings}))
            raise PrivacyViolation(f"public bundle blocked: {categories}")

    def require_allowed_source(self, path: Path) -> None:
        if _is_denied_source(path):
            raise PrivacyViolation("public bundle blocked: denied_source")

    def _scan_value(
        self,
        value: object,
        pointer: str,
        findings: list[PrivacyFinding],
        *,
        allow_approved_value: bool,
    ) -> None:
        if isinstance(value, str):
            self._scan_text(value, pointer, findings, allow_approved_value=allow_approved_value)
            return
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                if not isinstance(key, str):
                    findings.append(PrivacyFinding("unsupported_value", pointer))
                    self._scan_value(
                        nested_value,
                        _json_pointer_child(pointer, NON_STRING_KEY_POINTER),
                        findings,
                        allow_approved_value=True,
                    )
                    continue
                sensitive_key = self._scan_text(key, pointer, findings, allow_approved_value=False)
                child_pointer = pointer if sensitive_key else _json_pointer_child(pointer, key)
                self._scan_value(nested_value, child_pointer, findings, allow_approved_value=True)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for index, nested_value in enumerate(value):
                self._scan_value(
                    nested_value,
                    _json_pointer_child(pointer, str(index)),
                    findings,
                    allow_approved_value=True,
                )
            return

        findings.append(PrivacyFinding("unsupported_value", pointer))

    def _scan_text(
        self,
        value: str,
        pointer: str,
        findings: list[PrivacyFinding],
        *,
        allow_approved_value: bool,
    ) -> bool:
        if allow_approved_value and value in self._approved_public_values:
            return False

        categories = _matching_categories(value)
        findings.extend(PrivacyFinding(category, pointer) for category in categories)
        return bool(categories)


def _matching_categories(value: str) -> tuple[str, ...]:
    if CONTENT_SHA256.fullmatch(value):
        return ()
    categories: list[str] = []
    if any(pattern.search(value) for pattern in SECRET_PATTERNS.values()):
        categories.append("secret")
    if ABSOLUTE_PATH.search(value):
        categories.append("absolute_path")
    if EMAIL.search(value):
        categories.append("email")
    if PHONE.search(value):
        categories.append("phone")
    if PRIVATE_IP.search(value):
        categories.append("private_ip")
    if HTML_COMMENT.search(value):
        categories.append("html_comment")
    if SOURCE_MAP.search(value):
        categories.append("source_map")
    return tuple(categories)


def _validate_alias_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or not key:
        raise ValueError("alias key must be non-empty bytes")
    return key


def _json_pointer_child(parent: str, component: str) -> str:
    escaped = component.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _is_denied_source(path: Path) -> bool:
    candidates = [str(path)]
    try:
        candidates.append(str(path.resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        raise PrivacyViolation("public bundle blocked: source_resolution") from None
    return any(_contains_denied_source_part(candidate) for candidate in candidates)


def _contains_denied_source_part(path_text: str, *, case_sensitive: bool | None = None) -> bool:
    parts = _normalize_source_parts(path_text)
    if case_sensitive is None:
        case_sensitive = os.name != "nt"
    if not case_sensitive:
        parts = tuple(part.casefold() for part in parts)
        denied_names = {name.casefold() for name in DENIED_SOURCE_NAMES}
        denied_parts = tuple(
            tuple(part.casefold() for part in denied.split("/"))
            for denied in DENIED_SOURCE_PARTS
        )
    else:
        denied_names = DENIED_SOURCE_NAMES
        denied_parts = tuple(tuple(part for part in denied.split("/")) for denied in DENIED_SOURCE_PARTS)

    if any(part in denied_names for part in parts):
        return True
    return any(_contains_component_sequence(parts, denied) for denied in denied_parts)


def _normalize_source_parts(path_text: str) -> tuple[str, ...]:
    parts: list[str] = []
    for part in path_text.replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append(part)
            continue
        parts.append(part)
    return tuple(parts)


def _contains_component_sequence(parts: tuple[str, ...], denied: tuple[str, ...]) -> bool:
    width = len(denied)
    return any(parts[index : index + width] == denied for index in range(len(parts) - width + 1))
