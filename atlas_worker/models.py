"""Shared immutable records and JSON Schema validation for Project Atlas."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import ipaddress
import json
from pathlib import Path
import re
from typing import Literal
from urllib.parse import quote, unquote, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

Lifecycle = Literal["active", "finished"]
Publication = Literal["public", "private", "excluded"]
TagKind = Literal["domain", "problem", "pattern", "technology", "outcome"]
GraphNodeKind = Literal[
    "KnowledgeFocus",
    "KnowledgeDomain",
    "KnowledgeTag",
    "Project",
    "Technology",
    "Artifact",
]
GraphEdgeKind = Literal[
    "HAS_FOCUS",
    "FOCUS_HAS_TAG",
    "HAS_SUBTAG",
    "HAS_TAG",
    "USES_TECH",
    "PRODUCES_ARTIFACT",
    "ARTIFACT_HAS_TAG",
    "EVOLVED_FROM",
    "VALIDATES",
    "DEPLOYS",
    "REUSES_COMPONENT",
]
ArticleSectionType = Literal["planning", "decision", "implementation", "validation", "result"]
DecisionStatus = Literal["adopted", "revised", "rolled-back", "unresolved"]
EvidenceSourceType = Literal["session", "spec", "code", "test", "git", "project_memory"]
EvidencePrivacy = Literal["public-safe", "private", "secret"]
EvidenceClaimRole = Literal["supports", "contradicts", "context", "supersedes"]
Readiness = Literal["ready", "insufficient-evidence", "review-required"]
SessionMappingReason = Literal[
    "changed-path",
    "git-common-dir",
    "cwd",
    "alias",
    "parent-session",
    "ambiguous",
    "unmapped",
]

GRAPH_NODE_KINDS = frozenset(
    {"KnowledgeFocus", "KnowledgeDomain", "KnowledgeTag", "Project", "Technology", "Artifact"}
)
GRAPH_EDGE_KINDS = frozenset(
    {
        "HAS_FOCUS",
        "FOCUS_HAS_TAG",
        "HAS_SUBTAG",
        "HAS_TAG",
        "USES_TECH",
        "PRODUCES_ARTIFACT",
        "ARTIFACT_HAS_TAG",
        "EVOLVED_FROM",
        "VALIDATES",
        "DEPLOYS",
        "REUSES_COMPONENT",
    }
)
LEGACY_GRAPH_NODE_KINDS = frozenset({"project", "domain", "problem", "pattern", "technology", "outcome"})
LEGACY_GRAPH_EDGE_KINDS = frozenset({"tag-membership", "project-similarity"})

TAG_LIMITS = {
    "domain": (1, 2),
    "problem": (1, 3),
    "pattern": (1, 3),
    "technology": (0, 12),
    "outcome": (1, 2),
}

_SCHEMA_FORMAT_CHECKER = FormatChecker()
_DATE_VALUE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_TIME_VALUE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DNS_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_PUBLIC_PROJECT_TABS = frozenset({"decisions", "system-map", "build-timeline", "evidence"})


@_SCHEMA_FORMAT_CHECKER.checks("date")
def _is_valid_date(value: object) -> bool:
    if not isinstance(value, str) or _DATE_VALUE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@_SCHEMA_FORMAT_CHECKER.checks("date-time")
def _is_valid_date_time(value: object) -> bool:
    if not isinstance(value, str) or _DATE_TIME_VALUE.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    display_name: str
    root: Path
    relative_path: str
    lifecycle: Lifecycle
    publication: Publication
    aliases: tuple[str, ...]
    profile_path: Path | None = None
    standalone_asset: bool = False

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["root"] = str(self.root)
        value.pop("profile_path", None)
        value.pop("standalone_asset", None)
        return value


@dataclass(frozen=True)
class TagSet:
    domain: tuple[str, ...]
    problem: tuple[str, ...]
    pattern: tuple[str, ...]
    technology: tuple[str, ...]
    outcome: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, (minimum, maximum) in TAG_LIMITS.items():
            count = len(getattr(self, field_name))
            if count < minimum or count > maximum:
                raise ValueError(f"{field_name} supports {minimum}..{maximum} values")


@dataclass(frozen=True)
class EvidenceClaim:
    field: str
    value: object
    source_class: str
    confidence: float
    evidence_id: str
    claim_type: str = "fact"
    event_date: str = ""
    source_path: str = ""
    selected: bool = False


@dataclass(frozen=True)
class ProjectKnowledge:
    values: dict[str, object]
    winners: dict[str, EvidenceClaim]


@dataclass(frozen=True)
class ProjectMemory:
    profile: dict[str, object]
    build_story: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    rollbacks: tuple[str, ...] = ()
    events: tuple["ProjectEvent", ...] = ()


@dataclass(frozen=True)
class ProjectEvent:
    event_id: str
    date: str
    title: str
    context: str
    decision: str
    outcome: str
    stage: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    project_id: str
    label: str
    source_type: EvidenceSourceType
    source_locator: str
    observed_at: str
    privacy_class: EvidencePrivacy
    content_hash: str
    claim_role: EvidenceClaimRole = "supports"
    url: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        """Project pre-approved public URL metadata without private provenance."""
        payload: dict[str, object] = {
            "id": self.evidence_id,
            "label": self.label,
            "source_type": self.source_type,
            "observed_at": self.observed_at,
        }
        if self.url is not None:
            payload["url"] = validate_public_evidence_url(self.url)
        return payload


def validate_public_evidence_url(value: str) -> str:
    """Accept only syntactically safe absolute HTTPS evidence URLs.

    Domain approval remains curation policy; this boundary only rejects unsafe
    URL forms before they can become public payload data.
    """
    if not isinstance(value, str):
        raise ValueError("evidence url must be an absolute HTTPS URL")
    _require_safe_url_text(value)
    _require_well_formed_percent_escapes(value)
    decoded = unquote(value)
    _require_safe_url_text(decoded)
    _require_well_formed_percent_escapes(decoded)
    if unquote(decoded) != decoded:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise ValueError("evidence url must be an absolute HTTPS URL") from None
    if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    _validate_public_dns_host(parsed.hostname)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("evidence url must be an absolute HTTPS URL") from None
    _validate_explicit_port(parsed.netloc, port)
    return value


def validate_public_graph_url(value: str, *, allow_empty: bool = False) -> str:
    """Accept only canonical project routes or public HTTPS URLs."""
    if allow_empty and value == "":
        return value
    if not isinstance(value, str):
        raise ValueError("graph URL must be a public project route or HTTPS URL")
    if value.startswith("https://"):
        try:
            return validate_public_evidence_url(value)
        except ValueError:
            raise ValueError("graph URL must be a public project route or HTTPS URL") from None
    try:
        return _validate_public_project_route(value)
    except ValueError:
        raise ValueError("graph URL must be a public project route or HTTPS URL") from None


def _validate_public_project_route(value: str) -> str:
    _require_safe_url_text(value)
    _require_well_formed_percent_escapes(value)
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError("invalid public project route")
    prefix = "/projects/"
    if not parsed.path.startswith(prefix):
        raise ValueError("invalid public project route")
    encoded_id = parsed.path.removeprefix(prefix)
    if not encoded_id or "/" in encoded_id:
        raise ValueError("invalid public project route")
    decoded_id = unquote(encoded_id)
    _require_safe_url_text(decoded_id)
    if (
        quote(decoded_id, safe="") != encoded_id
        or unquote(decoded_id) != decoded_id
        or decoded_id.startswith(("/", "\\"))
        or any(segment in {".", ".."} for segment in decoded_id.split("/"))
    ):
        raise ValueError("invalid public project route")
    if parsed.query:
        key, separator, tab = parsed.query.partition("=")
        if key != "tab" or separator != "=" or tab not in _PUBLIC_PROJECT_TABS:
            raise ValueError("invalid public project route")
    return value


def _require_safe_url_text(value: str) -> None:
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("evidence url must be an absolute HTTPS URL")
    if "\\" in value:
        raise ValueError("evidence url must be an absolute HTTPS URL")


def _require_well_formed_percent_escapes(value: str) -> None:
    if _MALFORMED_PERCENT_ESCAPE.search(value):
        raise ValueError("evidence url must be an absolute HTTPS URL")


def _validate_public_dns_host(host: str | None) -> None:
    if not isinstance(host, str) or not host.isascii() or len(host) > 253:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    if not host or host.startswith(".") or host.endswith(".") or ".." in host or "." not in host:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    labels = tuple(host.split("."))
    if all(label.isdecimal() for label in labels) or not all(_DNS_LABEL.fullmatch(label) for label in labels):
        raise ValueError("evidence url must be an absolute HTTPS URL")


def _validate_explicit_port(netloc: str, port: int | None) -> None:
    if "@" in netloc:
        raise ValueError("evidence url must be an absolute HTTPS URL")
    if ":" not in netloc:
        return
    _, separator, port_text = netloc.rpartition(":")
    if not separator or not port_text or not port_text.isascii() or not port_text.isdecimal():
        raise ValueError("evidence url must be an absolute HTTPS URL")
    if port is None or not 0 < port <= 65535:
        raise ValueError("evidence url must be an absolute HTTPS URL")


@_SCHEMA_FORMAT_CHECKER.checks("atlas-https-url")
def _is_valid_atlas_https_url(value: object) -> bool:
    try:
        validate_public_evidence_url(value)  # type: ignore[arg-type]
    except ValueError:
        return False
    return True


@_SCHEMA_FORMAT_CHECKER.checks("atlas-public-graph-url")
def _is_valid_public_graph_url(value: object) -> bool:
    try:
        validate_public_graph_url(value)  # type: ignore[arg-type]
    except ValueError:
        return False
    return True


@_SCHEMA_FORMAT_CHECKER.checks("atlas-public-graph-node-url")
def _is_valid_public_graph_node_url(value: object) -> bool:
    try:
        validate_public_graph_url(value, allow_empty=True)  # type: ignore[arg-type]
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class DiagramRef:
    diagram_id: str
    source_path: str
    caption: str
    alt: str
    svg: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class ArticleSection:
    section_id: str
    title: str
    section_type: ArticleSectionType
    body: str
    evidence_ids: tuple[str, ...]
    diagrams: tuple[DiagramRef, ...] = ()


@dataclass(frozen=True)
class DecisionIndexEntry:
    decision_id: str
    section_id: str
    status: DecisionStatus
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectArticle:
    project_id: str
    title: str
    summary: str
    sections: tuple[ArticleSection, ...]
    readiness: Readiness
    orientation: str = ""
    orientation_evidence_ids: tuple[str, ...] = ()
    prior_context: str = ""
    decision_index: tuple[DecisionIndexEntry, ...] = ()

    def to_public_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_id": self.project_id,
            "title": self.title,
            "summary": self.summary,
            "readiness": self.readiness,
            "sections": [_public_section(section) for section in self.sections],
        }
        if self.orientation:
            payload["orientation"] = self.orientation
        if self.orientation_evidence_ids:
            payload["orientation_evidence_ids"] = list(self.orientation_evidence_ids)
        if self.prior_context:
            payload["prior_context"] = self.prior_context
        if self.decision_index:
            payload["decision_index"] = [_public_decision(item) for item in self.decision_index]
        return payload


@dataclass(frozen=True)
class SystemMapNode:
    node_id: str
    label: str
    kind: str
    description: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.node_id,
            "label": self.label,
            "kind": self.kind,
            "description": self.description,
        }


@dataclass(frozen=True)
class SystemMapFlow:
    flow_id: str
    source_id: str
    target_id: str
    label: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.flow_id,
            "from": self.source_id,
            "to": self.target_id,
            "label": self.label,
        }


@dataclass(frozen=True)
class SystemMapDecisionLink:
    node_ids: tuple[str, ...]
    section_id: str
    label: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "node_ids": list(self.node_ids),
            "section_id": self.section_id,
            "label": self.label,
        }


@dataclass(frozen=True)
class ProjectSystemMap:
    project_id: str
    title: str
    summary: str
    nodes: tuple[SystemMapNode, ...]
    flows: tuple[SystemMapFlow, ...]
    decision_links: tuple[SystemMapDecisionLink, ...]
    evidence_ids: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "summary": self.summary,
            "nodes": [node.to_public_dict() for node in self.nodes],
            "flows": [flow.to_public_dict() for flow in self.flows],
            "decision_links": [link.to_public_dict() for link in self.decision_links],
        }


@dataclass(frozen=True)
class ContentAudit:
    project_id: str
    readiness: Readiness
    evidence_counts: dict[str, int]
    session_stats: dict[str, int]
    missing_evidence_ids: tuple[str, ...]
    unmapped_session_ids: tuple[str, ...]
    findings: tuple[str, ...]


@dataclass(frozen=True)
class SessionEvent:
    session_id: str
    timestamp: str
    cwd: str
    role: str
    text: str
    source_path: str = ""
    line_number: int = 0
    parse_error: str = ""


@dataclass(frozen=True)
class SessionTrace:
    """Private, one-pass session evidence used only for local ownership mapping."""

    session_id: str
    parent_session_id: str
    cwd: str
    changed_paths: tuple[str, ...]
    git_common_dirs: tuple[str, ...]
    events: tuple[SessionEvent, ...]


@dataclass(frozen=True)
class SessionMapping:
    """Private ownership decision; it must never enter a public bundle or CLI payload."""

    session_id: str
    project_id: str | None
    reason: SessionMappingReason
    child_session_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TagCandidate:
    label: str
    kind: TagKind
    source_class: str
    evidence_id: str
    confidence: float
    decision: Literal["infer", "approve", "reject"] = "infer"


@dataclass(frozen=True)
class PublicProject:
    project_id: str
    display_name: str
    lifecycle: Lifecycle
    summary: str
    tags: TagSet
    publication: Literal["public"] = "public"
    outcome: str = ""
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.project_id,
            "name": self.display_name,
            "lifecycle": self.lifecycle,
            "publication": self.publication,
            "summary": self.summary,
            "tags": {
                kind: list(values)
                for kind, values in asdict(self.tags).items()
            },
            "outcome": self.outcome,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class DiscoveryReport:
    projects: tuple[ProjectRef, ...]
    ambiguous: tuple[ProjectRef, ...]


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    kind: GraphNodeKind
    url: str = ""
    summary: str = ""

    def to_public_dict(self) -> dict[str, object]:
        if self.kind not in GRAPH_NODE_KINDS:
            raise ValueError(f"Unknown public graph node kind: {self.kind}")
        try:
            url = validate_public_graph_url(self.url, allow_empty=True)
        except ValueError:
            raise ValueError("graph-node-url") from None
        return {
            "id": self.node_id,
            "label": self.label,
            "kind": self.kind,
            "url": url,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    kind: GraphEdgeKind
    weight: int = 1
    evidence_links: tuple[dict[str, str], ...] = ()

    @property
    def edge_id(self) -> str:
        return f"{self.kind.lower()}:{quote(self.source_id, safe='')}:{quote(self.target_id, safe='')}"

    @property
    def reasons(self) -> tuple[str, ...]:
        """Expose legacy similarity reasons until the old graph API is retired."""
        if all(isinstance(item, str) for item in self.evidence_links):
            return self.evidence_links  # type: ignore[return-value]
        return ()

    def to_public_dict(self) -> dict[str, object]:
        if self.kind not in GRAPH_EDGE_KINDS:
            raise ValueError(f"Unknown public graph edge kind: {self.kind}")
        evidence_links = []
        for link in self.evidence_links:
            if (
                not isinstance(link, dict)
                or frozenset(link) != frozenset({"label", "url"})
                or not isinstance(link["label"], str)
                or not link["label"].strip()
            ):
                raise ValueError("graph-evidence-link")
            try:
                url = validate_public_graph_url(link["url"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("graph-evidence-link-url") from None
            evidence_links.append({"label": link["label"], "url": url})
        return {
            "id": self.edge_id,
            "source": self.source_id,
            "target": self.target_id,
            "kind": self.kind,
            "weight": self.weight,
            "evidence_links": evidence_links,
        }


@dataclass(frozen=True)
class GraphData:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def __post_init__(self) -> None:
        for node in self.nodes:
            if node.kind not in GRAPH_NODE_KINDS and node.kind not in LEGACY_GRAPH_NODE_KINDS:
                raise ValueError(f"Unknown graph node kind: {node.kind}")
        for edge in self.edges:
            if edge.kind not in GRAPH_EDGE_KINDS and edge.kind not in LEGACY_GRAPH_EDGE_KINDS:
                raise ValueError(f"Unknown graph edge kind: {edge.kind}")

    def project_neighbors(self, project_id: str) -> tuple[GraphEdge, ...]:
        canonical_id = _graph_project_id(project_id)
        neighbors = (
            edge
            for edge in self.edges
            if edge.kind == "project-similarity"
            and canonical_id in (edge.source_id, edge.target_id)
        )
        return tuple(
            sorted(
                neighbors,
                key=lambda edge: (
                    -edge.weight,
                    _neighbor_id(edge, canonical_id),
                    edge.source_id,
                    edge.target_id,
                    edge.reasons,
                ),
            )[:5]
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "nodes": [node.to_public_dict() for node in self.nodes],
            "edges": [edge.to_public_dict() for edge in self.edges],
        }


@dataclass(frozen=True)
class BundleManifest:
    version: str
    projects: tuple[str, ...]
    files: dict[str, str] = field(default_factory=dict)
    project_hashes: dict[str, str] = field(default_factory=dict)
    changed_projects: tuple[str, ...] = ()
    format_version: int = 2

    def to_dict(self) -> dict[str, object]:
        """Serialize only the schema-defined public manifest fields."""
        return {
            "format_version": self.format_version,
            "version": self.version,
            "projects": list(self.projects),
            "files": dict(self.files),
        }


@dataclass(frozen=True)
class MemoryUpdate:
    changed_files: tuple[str, ...]


@dataclass(frozen=True)
class PromotionResult:
    changed: bool
    changed_projects: tuple[str, ...]


def validate_schema(instance: object, schema_name: str) -> None:
    """Validate an instance with a bundled schema and expose useful field paths."""
    schema_path = Path(__file__).parent.parent / "schemas" / f"{schema_name}.schema.json"
    if not schema_path.is_file():
        raise ValueError(f"Unknown schema: {schema_name}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=_SCHEMA_FORMAT_CHECKER)
    error = next(iter(validator.iter_errors(instance)), None)
    if error is not None:
        raise ValueError(_schema_error_message(error, instance)) from error


def _schema_error_message(error: ValidationError, instance: object) -> str:
    path = _schema_error_path(error, instance)
    return f"Schema validation failed at {path}: {error.message}"


def _schema_error_path(error: ValidationError, instance: object) -> str:
    path = [str(part) for part in error.absolute_path]
    current = _instance_at_path(instance, error.absolute_path)
    if error.validator == "additionalProperties" and isinstance(current, dict):
        properties = error.schema.get("properties", {})
        unexpected = sorted(set(current) - set(properties))
        if unexpected:
            path.append(unexpected[0])
    if error.validator == "required":
        missing = re.search(r"'([^']+)' is a required property", error.message)
        if missing:
            path.append(missing.group(1))
    return ".".join(path) or "$"


def _instance_at_path(instance: object, path: object) -> object:
    current = instance
    for part in path:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and isinstance(part, int):
            current = current[part]
        else:
            return None
    return current


def _neighbor_id(edge: GraphEdge, project_id: str) -> str:
    return edge.target_id if edge.source_id == project_id else edge.source_id


def _graph_project_id(project_id: str) -> str:
    return f"project:{quote(project_id, safe='')}"


def _public_section(section: ArticleSection) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": section.section_id,
        "title": section.title,
        "section_type": section.section_type,
        "body": section.body,
        "evidence_ids": list(section.evidence_ids),
    }
    if section.diagrams:
        payload["diagrams"] = [
            {"id": item.diagram_id, "caption": item.caption, "alt": item.alt}
            for item in section.diagrams
        ]
    return payload


def _public_decision(item: DecisionIndexEntry) -> dict[str, object]:
    return {
        "decision_id": item.decision_id,
        "section_id": item.section_id,
        "status": item.status,
        "evidence_ids": list(item.evidence_ids),
    }
