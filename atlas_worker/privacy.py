"""Fail-closed privacy checks for Project Atlas public bundles."""

from collections.abc import Mapping, Sequence
import base64
from dataclasses import dataclass
import hashlib
import hmac
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote


SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
HTTP_URL_START = re.compile(r"https?://", re.I)
URI_SCHEME_START = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HTTP_URL_TERMINATORS = frozenset(" \t\r\n<>\"',;)]}")
POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_/\\])/(?![/>#])(?:[^\s<>\"']*)?")
WINDOWS_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
UNC_PATH = re.compile(r"(?<![A-Za-z0-9])(?:\\\\|//)[^\\/\s]+[\\/][^\\/\s]+")
CLOSING_TAG = re.compile(r"</\s*[A-Za-z][A-Za-z0-9:._-]*\s*>")
START_TAG_NAME = re.compile(r"<([A-Za-z][A-Za-z0-9:._-]*)")
RAW_ATTRIBUTE_ASSIGNMENT = re.compile(
    r"(?<!\S)(?P<name>[A-Za-z_:][A-Za-z0-9:._-]*)\s*=\s*"
    r'(?:"(?P<double>[^\"]*)"|\'(?P<single>[^\']*)\'|(?P<unquoted>[^\s\"\'=<>`]+))'
)
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
ENCODED_PATH_SEPARATOR = re.compile(r"%(?:2f|5c)", re.I)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(
    r"(?<![A-Za-z0-9])(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?![A-Za-z0-9])"
)
PRIVATE_IP = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
SOURCE_MAP = re.compile(r"(?:\bsourceMappingURL\s*=\s*\S+|\b[A-Za-z0-9_./-]+\.map\b)", re.I)
SAFE_ALIAS_PREFIX = re.compile(r"[A-Z][A-Z0-9_]*")

DENIED_SOURCE_NAMES = {".env", "credentials.json", "auth.json"}
DENIED_SOURCE_PARTS = {".codex/sessions", "logs", "raw-logs", "private-data"}
NON_STRING_KEY_POINTER = "<non-string-key>"
URL_BEARING_ATTRIBUTES = frozenset({"href", "src", "action"})
SEARCH_DOCUMENT_KEYS = frozenset({"id", "project_id", "title", "body", "url"})
GRAPH_NODE_KEYS = frozenset({"id", "label", "kind", "url", "summary"})
GRAPH_EVIDENCE_LINK_KEYS = frozenset({"label", "url"})
PUBLIC_ROUTE_EXACT_PATHS = frozenset({"/", "/projects", "/topics", "/graph", "/changelog", "/search"})
PUBLIC_ROUTE_DESCENDANT_PREFIXES = ("/projects/", "/topics/")
PUBLIC_ASSET_PREFIX = "/assets/"
URL_ATTRIBUTE_DECODE_LIMIT = 16
MIN_ALIAS_KEY_BYTES = 32


@dataclass(frozen=True)
class PrivacyFinding:
    category: str
    json_pointer: str


@dataclass(frozen=True)
class PrivacyReport:
    findings: tuple[PrivacyFinding, ...]


@dataclass(frozen=True)
class _ParsedStartTag:
    raw_attribute_fragment: str
    attributes: tuple[tuple[str, str | None], ...]


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
        self._forbidden_alias_key_variants = _alias_key_variants(self._alias_key)
        self._approved_public_values = frozenset(approved_public_values)

    def scan(self, record: object) -> PrivacyReport:
        findings: list[PrivacyFinding] = []
        self._scan_value(
            record,
            "",
            findings,
            allow_approved_value=True,
            allow_public_route=False,
            allow_spaced_slash=False,
        )
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
        allow_public_route: bool,
        allow_spaced_slash: bool,
    ) -> None:
        if isinstance(value, str):
            self._scan_text(
                value,
                pointer,
                findings,
                allow_approved_value=allow_approved_value,
                allow_public_route=allow_public_route,
                allow_spaced_slash=allow_spaced_slash,
            )
            return
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, Mapping):
            self._scan_mapping_items(tuple(value.items()), pointer, findings)
            return
        object_pairs = _json_object_pairs(value)
        if object_pairs is not None:
            self._scan_mapping_items(object_pairs, pointer, findings)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for index, nested_value in enumerate(value):
                self._scan_value(
                    nested_value,
                    _json_pointer_child(pointer, str(index)),
                    findings,
                    allow_approved_value=True,
                    allow_public_route=False,
                    allow_spaced_slash=False,
                )
            return

        findings.append(PrivacyFinding("unsupported_value", pointer))

    def _scan_mapping_items(
        self,
        items: tuple[tuple[object, object], ...],
        pointer: str,
        findings: list[PrivacyFinding],
    ) -> None:
        route_url_allowed = _is_public_url_record(items)
        graph_label_allowed = _is_graph_node(items)
        for key, nested_value in items:
            if not isinstance(key, str):
                findings.append(PrivacyFinding("unsupported_value", pointer))
                self._scan_value(
                    nested_value,
                    _json_pointer_child(pointer, NON_STRING_KEY_POINTER),
                    findings,
                    allow_approved_value=True,
                    allow_public_route=False,
                    allow_spaced_slash=False,
                )
                continue
            sensitive_key = self._scan_text(
                key,
                pointer,
                findings,
                allow_approved_value=False,
                allow_public_route=False,
                allow_spaced_slash=False,
            )
            child_pointer = pointer if sensitive_key else _json_pointer_child(pointer, key)
            self._scan_value(
                nested_value,
                child_pointer,
                findings,
                allow_approved_value=True,
                allow_public_route=route_url_allowed and key == "url",
                allow_spaced_slash=graph_label_allowed and key == "label",
            )

    def _scan_text(
        self,
        value: str,
        pointer: str,
        findings: list[PrivacyFinding],
        *,
        allow_approved_value: bool,
        allow_public_route: bool,
        allow_spaced_slash: bool,
    ) -> bool:
        if any(variant in value for variant in self._forbidden_alias_key_variants):
            findings.append(PrivacyFinding("alias_key", pointer))
            return True
        if allow_approved_value and value in self._approved_public_values:
            return False

        categories = _matching_categories(
            value,
            allow_public_route=allow_public_route,
            allow_spaced_slash=allow_spaced_slash,
        )
        findings.extend(PrivacyFinding(category, pointer) for category in categories)
        return bool(categories)


def _json_object_pairs(value: object) -> tuple[tuple[object, object], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, tuple) and len(item) == 2 for item in value):
        return None
    return tuple((item[0], item[1]) for item in value)


def _is_public_url_record(items: tuple[tuple[object, object], ...]) -> bool:
    if not all(isinstance(key, str) for key, _ in items):
        return False
    keys = frozenset(key for key, _ in items)
    return keys in {SEARCH_DOCUMENT_KEYS, GRAPH_NODE_KEYS, GRAPH_EVIDENCE_LINK_KEYS}


def _is_graph_node(items: tuple[tuple[object, object], ...]) -> bool:
    return (
        all(isinstance(key, str) for key, _ in items)
        and frozenset(key for key, _ in items) == GRAPH_NODE_KEYS
    )


def _matching_categories(
    value: str,
    *,
    allow_public_route: bool = False,
    allow_spaced_slash: bool = False,
) -> tuple[str, ...]:
    categories: list[str] = []
    if any(pattern.search(value) for pattern in SECRET_PATTERNS.values()):
        categories.append("secret")
    contains_path = _contains_absolute_path(value, allow_public_route=allow_public_route)
    if contains_path and allow_spaced_slash:
        without_spaced_slashes = re.sub(r"(?<=\s)/(?=\s)", " ", value)
        contains_path = _contains_absolute_path(
            without_spaced_slashes,
            allow_public_route=allow_public_route,
        )
    if contains_path:
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


def _contains_absolute_path(value: str, *, allow_public_route: bool = False) -> bool:
    if allow_public_route and _is_safe_public_route(value):
        return False
    cursor = 0
    while cursor < len(value):
        tag_start = value.find("<", cursor)
        if tag_start < 0:
            return _plain_text_contains_absolute_path(value[cursor:])
        if _plain_text_contains_absolute_path(value[cursor:tag_start]):
            return True

        tag_end = _find_tag_end(value, tag_start)
        if tag_end is None:
            return _plain_text_contains_absolute_path(value[tag_start:])
        tag = value[tag_start : tag_end + 1]
        if not CLOSING_TAG.fullmatch(tag):
            parsed_tag = _parse_start_tag_attributes(tag)
            if parsed_tag is None:
                if _plain_text_contains_absolute_path(tag):
                    return True
            elif _raw_attribute_fragment_contains_absolute_path(parsed_tag) or any(
                _attribute_contains_absolute_path(name, attribute)
                for name, attribute in parsed_tag.attributes
                if attribute is not None
            ):
                return True
        cursor = tag_end + 1
    return False


def _plain_text_contains_absolute_path(value: str) -> bool:
    without_urls = _mask_http_urls(value)
    return any(
        pattern.search(without_urls)
        for pattern in (WINDOWS_DRIVE_PATH, UNC_PATH, POSIX_ABSOLUTE_PATH)
    )


def _raw_attribute_fragment_contains_absolute_path(parsed_tag: _ParsedStartTag) -> bool:
    confirmed_safe_routes = [
        (name.casefold(), value)
        for name, value in parsed_tag.attributes
        if value is not None
        and name.casefold() in URL_BEARING_ATTRIBUTES
        and _is_safe_public_route(value)
    ]
    masked = list(parsed_tag.raw_attribute_fragment)
    for match in RAW_ATTRIBUTE_ASSIGNMENT.finditer(parsed_tag.raw_attribute_fragment):
        value_group = next(
            group
            for group in ("double", "single", "unquoted")
            if match.group(group) is not None
        )
        route = unescape(match.group(value_group))
        confirmed = (match.group("name").casefold(), route)
        if confirmed not in confirmed_safe_routes:
            continue
        confirmed_safe_routes.remove(confirmed)
        start, end = match.span(value_group)
        masked[start:end] = " " * (end - start)
    return _plain_text_contains_absolute_path("".join(masked))


def _attribute_contains_absolute_path(name: str, value: str) -> bool:
    if name.casefold() in URL_BEARING_ATTRIBUTES:
        normalized = _normalize_url_attribute(value)
        if normalized is None:
            return True
        classified = normalized.strip(" ")
        if HTTP_URL_START.match(classified):
            return _plain_text_contains_absolute_path(classified)
        if URI_SCHEME_START.match(classified):
            return True
        if classified.startswith("//"):
            return True
        if classified.startswith("/"):
            return not value.startswith("/") or not _is_safe_public_route(value)
        if _relative_url_has_dot_traversal(classified):
            return True
        return _plain_text_contains_absolute_path(classified)
    return _plain_text_contains_absolute_path(value)


def _normalize_url_attribute(value: str) -> str | None:
    current = value
    seen: set[str] = set()
    for _ in range(URL_ATTRIBUTE_DECODE_LIMIT):
        if current in seen or INVALID_PERCENT_ESCAPE.search(current):
            return None
        seen.add(current)
        if "\\" in current or any(unicodedata.category(character) == "Cc" for character in current):
            return None
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError:
            return None
        if decoded == current:
            return current
        current = decoded
    return None


def _relative_url_has_dot_traversal(value: str) -> bool:
    path = re.split(r"[?#]", value, maxsplit=1)[0]
    return any(segment in {".", ".."} for segment in path.split("/"))


def _is_safe_public_route(value: str) -> bool:
    if not value.startswith("/") or value.startswith("//"):
        return False
    if _decoded_route_has_control_or_backslash(value):
        return False

    path = re.split(r"[?#]", value, maxsplit=1)[0]
    if INVALID_PERCENT_ESCAPE.search(path):
        return False
    decoded_path = _decode_public_route_path(path)
    if decoded_path is None:
        return False
    if decoded_path in PUBLIC_ROUTE_EXACT_PATHS:
        return True
    if any(decoded_path.startswith(prefix) for prefix in PUBLIC_ROUTE_DESCENDANT_PREFIXES):
        return True
    return decoded_path.startswith(PUBLIC_ASSET_PREFIX) and len(decoded_path) > len(PUBLIC_ASSET_PREFIX)


def _decoded_route_has_control_or_backslash(value: str) -> bool:
    current = value
    for _ in range(len(value) + 1):
        if "\\" in current or any(unicodedata.category(character) == "Cc" for character in current):
            return True
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError:
            return True
        if decoded == current:
            return False
        current = decoded
    return True


def _decode_public_route_path(path: str) -> str | None:
    current = path
    for _ in range(len(path) + 1):
        if (
            current.startswith("//")
            or ENCODED_PATH_SEPARATOR.search(current)
            or any(character.isspace() or character in "<>\"'" for character in current)
            or any(segment in {".", ".."} for segment in current.split("/"))
        ):
            return None
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError:
            return None
        if decoded == current:
            return current
        current = decoded
    return None


def _find_tag_end(value: str, start: int) -> int | None:
    quote: str | None = None
    for index in range(start + 1, len(value)):
        character = value[index]
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == ">":
            return index
    return None


def _parse_start_tag_attributes(tag: str) -> _ParsedStartTag | None:
    parser = _SingleStartTagParser()
    try:
        parser.feed(tag)
        parser.close()
    except Exception:
        return None
    if not parser.valid:
        return None
    if parser.raw_start_tag_text != tag or parser.tag_name is None:
        return None
    raw_attribute_fragment = _isolate_raw_attribute_fragment(
        parser.raw_start_tag_text,
        parser.tag_name,
        self_closing=parser.self_closing,
    )
    if raw_attribute_fragment is None:
        return None
    return _ParsedStartTag(
        raw_attribute_fragment=raw_attribute_fragment,
        attributes=tuple(parser.attributes),
    )


def _isolate_raw_attribute_fragment(
    raw_start_tag_text: str,
    tag_name: str,
    *,
    self_closing: bool,
) -> str | None:
    name_match = START_TAG_NAME.match(raw_start_tag_text)
    if (
        name_match is None
        or name_match.group(1).casefold() != tag_name.casefold()
        or not raw_start_tag_text.endswith(">")
    ):
        return None

    fragment = raw_start_tag_text[name_match.end() : -1]
    if self_closing:
        if not fragment.endswith("/"):
            return None
        fragment = fragment[:-1]
    return fragment


class _SingleStartTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.attributes: list[tuple[str, str | None]] = []
        self.raw_start_tag_text: str | None = None
        self.tag_name: str | None = None
        self.self_closing = False
        self._start_events = 0
        self._invalid = False

    @property
    def valid(self) -> bool:
        return self._start_events == 1 and not self._invalid

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._accept_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._accept_start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        self._invalid = True

    def handle_data(self, data: str) -> None:
        if data:
            self._invalid = True

    def handle_comment(self, data: str) -> None:
        self._invalid = True

    def handle_decl(self, decl: str) -> None:
        self._invalid = True

    def handle_pi(self, data: str) -> None:
        self._invalid = True

    def unknown_decl(self, data: str) -> None:
        self._invalid = True

    def _accept_start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        self_closing: bool,
    ) -> None:
        self._start_events += 1
        if self._start_events == 1:
            self.attributes = attrs
            self.raw_start_tag_text = self.get_starttag_text()
            self.tag_name = tag
            self.self_closing = self_closing
        else:
            self._invalid = True


def _mask_http_urls(value: str) -> str:
    masked = list(value)
    for match in HTTP_URL_START.finditer(value):
        end = match.end()
        while end < len(value) and value[end] not in HTTP_URL_TERMINATORS:
            end += 1
        masked[match.start() : end] = " " * (end - match.start())
    return "".join(masked)


def _validate_alias_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or not key:
        raise ValueError("alias key must be non-empty bytes")
    return key


def _alias_key_variants(key: bytes) -> frozenset[str]:
    """Return comparison-only encodings for production-strength key material."""
    if len(key) < MIN_ALIAS_KEY_BYTES:
        return frozenset()

    variants = {
        key.hex(),
        key.hex().upper(),
        base64.b64encode(key).decode("ascii"),
        base64.urlsafe_b64encode(key).decode("ascii"),
    }
    variants.update(value.rstrip("=") for value in tuple(variants) if value.endswith("="))
    try:
        variants.add(key.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    variants.discard("")
    return frozenset(variants)


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
