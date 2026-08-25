"""Shared immutable records and JSON Schema validation for Project Atlas."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Literal
from urllib.parse import quote

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

Lifecycle = Literal["active", "finished"]
Publication = Literal["public", "private", "excluded"]
TagKind = Literal["domain", "problem", "pattern", "technology", "outcome"]
GraphNodeKind = Literal["project", "domain", "problem", "pattern", "technology", "outcome"]
GraphEdgeKind = Literal["tag-membership", "project-similarity"]

GRAPH_NODE_KINDS = frozenset({"project", "domain", "problem", "pattern", "technology", "outcome"})
GRAPH_EDGE_KINDS = frozenset({"tag-membership", "project-similarity"})

TAG_LIMITS = {
    "domain": (1, 2),
    "problem": (1, 3),
    "pattern": (1, 3),
    "technology": (0, 12),
    "outcome": (1, 2),
}


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    display_name: str
    root: Path
    relative_path: str
    lifecycle: Lifecycle
    publication: Publication
    aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["root"] = str(self.root)
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


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    kind: GraphEdgeKind
    weight: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphData:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def __post_init__(self) -> None:
        for node in self.nodes:
            if node.kind not in GRAPH_NODE_KINDS:
                raise ValueError(f"Unknown graph node kind: {node.kind}")
        for edge in self.edges:
            if edge.kind not in GRAPH_EDGE_KINDS:
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


@dataclass(frozen=True)
class BundleManifest:
    version: str
    project_hashes: dict[str, str]
    files: dict[str, str] = field(default_factory=dict)


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
    validator = Draft202012Validator(schema)
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
