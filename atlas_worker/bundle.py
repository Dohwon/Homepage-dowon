"""Build and atomically promote the only local-to-public Atlas boundary."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Mapping
from urllib.parse import quote
import xml.etree.ElementTree as ET

from .manifest import (
    bundle_file_hashes,
    canonical_hash,
    canonical_json_bytes,
    content_version,
    iter_tree_files,
    project_hashes_from_files,
    require_no_symlink_path,
    tree_hash,
)
from .models import (
    GRAPH_EDGE_KINDS,
    GRAPH_NODE_KINDS,
    BundleManifest,
    EvidenceRecord,
    GraphData,
    ProjectEvent,
    ProjectArticle,
    ProjectMemory,
    ProjectRef,
    PromotionResult,
    PublicProject,
    validate_schema,
)
from .privacy import PrivacyGate
from .graph import TAG_WEIGHTS
from .taxonomy import display_tag_label, normalize_tag_label


_V1_OPTIONAL_PROJECT_FILES = (
    "build-story.md",
    "decisions.md",
    "rollbacks.md",
    "visuals/problem-solving.svg",
)
_V2_OPTIONAL_PROJECT_FILES = (
    "article.json",
    "evidence.json",
    "timeline.json",
    "system-map.svg",
)
_MANDATORY_FILES = frozenset(
    {
        "manifest.json",
        "graph/nodes.json",
        "graph/edges.json",
        "topics.json",
        "changelog.json",
        "search-index.json",
    }
)
_MANAGED_COMMENT = re.compile(r"<!-- /?atlas:event:[A-Za-z0-9][A-Za-z0-9._-]* -->")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SVG_TAG = "{http://www.w3.org/2000/svg}svg"


class BundleRecoveryError(OSError):
    """Raised when last-good recovery cannot be completed automatically."""


@dataclass(frozen=True)
class SearchDocument:
    document_id: str
    project_id: str
    title: str
    body: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.document_id,
            "project_id": self.project_id,
            "title": self.title,
            "body": self.body,
            "url": self.url,
        }


@dataclass(frozen=True)
class BundleContext:
    projects: tuple[PublicProject, ...]
    project_memories: Mapping[str, ProjectMemory]
    project_events: Mapping[str, tuple[ProjectEvent, ...]]
    graph: GraphData
    search_documents: tuple[SearchDocument, ...]
    source_hashes: Mapping[str, str]
    previous_manifest: BundleManifest | None
    privacy_gate: PrivacyGate
    project_articles: Mapping[str, ProjectArticle] = field(default_factory=dict)
    project_evidence: Mapping[str, tuple[EvidenceRecord, ...]] = field(default_factory=dict)
    project_system_maps: Mapping[str, str] = field(default_factory=dict)


def build_candidate_bundle(context: BundleContext, staging_dir: Path) -> BundleManifest:
    """Render a deterministic candidate into a newly empty staging directory."""
    staging_dir = Path(staging_dir)
    _prepare_staging(staging_dir)
    projects = tuple(sorted(context.projects, key=lambda project: project.project_id))
    project_ids = tuple(project.project_id for project in projects)
    _validate_context(context, projects, project_ids)

    for project in projects:
        project_dir = staging_dir / "projects" / project.project_id
        project_payload = project.to_dict()
        validate_schema(project_payload, "public-project")
        _write_json(project_dir / "project.json", project_payload, context.privacy_gate)

        article = (context.project_articles or {}).get(project.project_id)
        if article is not None:
            _write_v2_project_content(
                project_dir,
                project.project_id,
                article,
                (context.project_evidence or {}).get(project.project_id, ()),
                context.project_events.get(project.project_id, ()),
                (context.project_system_maps or {}).get(project.project_id),
                context.privacy_gate,
            )

    nodes = _graph_nodes(context.graph)
    edges = _graph_edges(context.graph)
    topics = _topics(projects)
    changelog = _changelog(context.project_events, project_ids)
    search_index = _search_index(context.search_documents, project_ids)
    _validate_graph(
        nodes,
        edges,
        {project.project_id: project.to_dict() for project in projects},
    )
    _validate_topics(topics, set(project_ids))
    _validate_changelog(changelog, set(project_ids))
    _validate_search_index(search_index, set(project_ids))
    _write_json(staging_dir / "graph" / "nodes.json", nodes, context.privacy_gate)
    _write_json(staging_dir / "graph" / "edges.json", edges, context.privacy_gate)
    _write_json(staging_dir / "topics.json", topics, context.privacy_gate)
    _write_json(staging_dir / "changelog.json", changelog, context.privacy_gate)
    _write_json(staging_dir / "search-index.json", search_index, context.privacy_gate)

    files = bundle_file_hashes(staging_dir)
    project_hashes = project_hashes_from_files(project_ids, files)
    changed_projects = _changed_hash_ids(
        context.previous_manifest.project_hashes if context.previous_manifest is not None else {},
        project_hashes,
    )
    version = content_version(files, project_hashes)
    manifest = BundleManifest(
        version=version,
        projects=project_ids,
        files=files,
        project_hashes=project_hashes,
        changed_projects=changed_projects,
        format_version=2,
    )
    manifest_payload = manifest.to_dict()
    validate_schema(manifest_payload, "public-manifest")
    _write_json(staging_dir / "manifest.json", manifest_payload, context.privacy_gate)

    tree = _load_text_tree(staging_dir)
    context.privacy_gate.require_safe(_privacy_tree(tree))
    _validate_bundle(staging_dir, tree)
    return manifest


def promote_bundle(staging_dir: Path, public_dir: Path, gate: PrivacyGate) -> PromotionResult:
    """Validate a candidate completely, then promote it with rename rollback."""
    staging_dir = Path(staging_dir)
    public_dir = Path(public_dir)
    require_no_symlink_path(staging_dir)
    require_no_symlink_path(public_dir)
    backup = public_dir.parent / ".public-bundle.previous"
    require_no_symlink_path(backup)
    if backup.exists() or backup.is_symlink():
        raise FileExistsError(f"stale backup requires recovery: {backup}")
    candidate = _load_text_tree(staging_dir)
    gate.require_safe(_privacy_tree(candidate))
    candidate_manifest = _validate_bundle(staging_dir, candidate)

    previous_hash = tree_hash(public_dir) if public_dir.exists() else None
    candidate_hash = tree_hash(staging_dir)
    if previous_hash == candidate_hash:
        return PromotionResult(changed=False, changed_projects=())

    _require_safe_destination(public_dir)
    _require_same_filesystem(staging_dir, public_dir.parent)
    changed_projects = _changed_project_ids(staging_dir, public_dir, candidate_manifest)
    recovery = public_dir.parent / ".public-bundle.recovery"
    require_no_symlink_path(recovery)
    if recovery.exists() or recovery.is_symlink():
        raise FileExistsError(f"stale recovery tree requires cleanup: {recovery}")

    if not public_dir.exists():
        _rename(staging_dir, public_dir)
        return PromotionResult(changed=True, changed_projects=changed_projects)

    _rename(public_dir, backup)
    try:
        _rename(staging_dir, public_dir)
    except (OSError, ValueError):
        _restore_backup(backup, public_dir, recovery, gate, previous_hash)
        raise
    try:
        _cleanup_tree(backup)
    except (OSError, ValueError):
        # The promoted public tree is already complete. A retained backup is
        # detected and refused deterministically on the next promotion.
        pass
    return PromotionResult(changed=True, changed_projects=changed_projects)


def validate_bundle(bundle_dir: Path, gate: PrivacyGate) -> BundleManifest:
    """Validate an existing public bundle without promotion or mutation."""
    bundle_dir = Path(bundle_dir)
    require_no_symlink_path(bundle_dir)
    tree = _load_text_tree(bundle_dir)
    gate.require_safe(_privacy_tree(tree))
    return _validate_bundle(bundle_dir, tree)


def _prepare_staging(staging_dir: Path) -> None:
    absolute = staging_dir.absolute()
    require_no_symlink_path(absolute)
    resolved = staging_dir.resolve(strict=False)
    protected = {
        Path("/").resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
        Path(__file__).parent.parent.resolve(),
    }
    if resolved in protected:
        raise ValueError(f"unsafe staging root: {staging_dir}")
    if staging_dir.exists() or staging_dir.is_symlink():
        mode = staging_dir.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"unsafe staging root symlink: {staging_dir}")
        if not stat.S_ISDIR(mode):
            raise ValueError(f"unsafe staging root is not a directory: {staging_dir}")
        tuple(iter_tree_files(staging_dir))
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    (staging_dir / "projects").mkdir()


def _validate_context(
    context: BundleContext,
    projects: tuple[PublicProject, ...],
    project_ids: tuple[str, ...],
) -> None:
    if len(project_ids) != len(set(project_ids)):
        raise ValueError("bundle projects require unique project IDs")
    for project in projects:
        _require_project_id(project.project_id)
        if project.publication != "public":
            raise ValueError(f"bundle project is not public: {project.project_id}")
    known = set(project_ids)
    for mapping_name, mapping in (
        ("project_memories", context.project_memories),
        ("project_events", context.project_events),
        ("project_articles", context.project_articles or {}),
        ("project_evidence", context.project_evidence or {}),
        ("project_system_maps", context.project_system_maps or {}),
    ):
        unknown = sorted(set(mapping) - known)
        if unknown:
            raise ValueError(f"{mapping_name} contains unknown project: {unknown[0]}")
    for key, digest in context.source_hashes.items():
        if not isinstance(key, str) or not key or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError("source_hashes must map non-empty strings to SHA-256 hashes")
    if context.previous_manifest is not None:
        _validate_previous_manifest(context.previous_manifest)


def _write_v2_project_content(
    project_dir: Path,
    project_id: str,
    article: ProjectArticle,
    evidence: tuple[EvidenceRecord, ...],
    events: tuple[ProjectEvent, ...],
    system_map: str | None,
    gate: PrivacyGate,
) -> None:
    if article.project_id != project_id:
        raise ValueError("article project does not match bundle project")
    article_payload = article.to_public_dict()
    validate_schema(article_payload, "public-article")
    _write_json(project_dir / "article.json", article_payload, gate)

    diagrams: dict[str, str] = {}
    for section in article.sections:
        for diagram in section.diagrams:
            if diagram.diagram_id in diagrams:
                raise ValueError("article diagram IDs must be unique")
            _validate_svg(diagram.svg)
            diagrams[diagram.diagram_id] = diagram.svg
    for diagram_id, svg in sorted(diagrams.items()):
        _write_text(project_dir / "visuals" / f"{diagram_id}.svg", svg, gate)

    public_evidence = []
    for record in evidence:
        if record.project_id != project_id:
            raise ValueError("evidence project does not match bundle project")
        public_evidence.append(record.to_public_dict())
    if public_evidence:
        validate_schema(public_evidence, "public-evidence")
        _write_json(project_dir / "evidence.json", public_evidence, gate)

    timeline = [_event_to_public(event) for event in events]
    if timeline:
        validate_schema(timeline, "public-timeline")
        _write_json(project_dir / "timeline.json", timeline, gate)

    if system_map is not None:
        _validate_svg(system_map)
        _write_text(project_dir / "system-map.svg", system_map, gate)


def _event_to_public(event: ProjectEvent) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "date": event.date,
        "title": event.title,
        "context": event.context,
        "decision": event.decision,
        "outcome": event.outcome,
        "stage": event.stage,
    }


def _render_markdown(title: str, entries: tuple[str, ...]) -> str | None:
    rendered_entries = []
    for entry in entries:
        cleaned = _strip_managed_comments(str(entry)).strip()
        if cleaned:
            rendered_entries.append("- " + cleaned.replace("\n", "\n  "))
    if not rendered_entries:
        return None
    return f"# {title}\n\n" + "\n".join(rendered_entries) + "\n"


def _strip_managed_comments(value: str) -> str:
    kept = []
    for line in value.splitlines(keepends=True):
        marker = line.rstrip("\r\n")
        if _MANAGED_COMMENT.fullmatch(marker):
            continue
        kept.append(line)
    return "".join(kept)


def _project_ref(project: PublicProject) -> ProjectRef:
    return ProjectRef(
        project_id=project.project_id,
        display_name=project.display_name,
        root=Path("."),
        relative_path=f"projects/{project.project_id}",
        lifecycle=project.lifecycle,
        publication="public",
        aliases=project.aliases,
    )


def _graph_nodes(graph: GraphData) -> list[dict[str, str]]:
    return [
        {"id": node.node_id, "label": node.label, "kind": node.kind}
        for node in sorted(graph.nodes, key=lambda item: (item.kind, item.node_id, item.label))
    ]


def _graph_edges(graph: GraphData) -> list[dict[str, object]]:
    return [
        {
            "source": edge.source_id,
            "target": edge.target_id,
            "kind": edge.kind,
            "weight": edge.weight,
            "reasons": list(edge.reasons),
        }
        for edge in sorted(
            graph.edges,
            key=lambda item: (item.kind, item.source_id, item.target_id, -item.weight, item.reasons),
        )
    ]


def _topics(projects: tuple[PublicProject, ...]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for project in projects:
        for kind in ("domain", "problem", "pattern", "technology", "outcome"):
            for raw_label in getattr(project.tags, kind):
                key = (kind, normalize_tag_label(raw_label))
                topic = grouped.setdefault(
                    key,
                    {"kind": kind, "label": display_tag_label(raw_label), "project_ids": []},
                )
                topic["project_ids"].append(project.project_id)
                topic["label"] = min(str(topic["label"]), display_tag_label(raw_label))
    return [
        {
            "kind": topic["kind"],
            "label": topic["label"],
            "project_ids": sorted(set(topic["project_ids"])),
        }
        for _, topic in sorted(grouped.items())
    ]


def _changelog(
    events_by_project: Mapping[str, tuple[ProjectEvent, ...]],
    project_ids: tuple[str, ...],
) -> list[dict[str, str]]:
    entries = []
    for project_id in project_ids:
        for event in events_by_project.get(project_id, ()):
            entry = {
                "project_id": project_id,
                "event_id": event.event_id,
                "title": event.title,
                "stage": event.stage,
                "context": event.context,
                "decision": event.decision,
                "outcome": event.outcome,
            }
            if event.date:
                entry["date"] = event.date
            entries.append(entry)
    return sorted(
        entries,
        key=lambda item: (
            item.get("date", ""),
            item["project_id"],
            item["event_id"],
            item["title"],
        ),
    )


def _search_index(documents: tuple[SearchDocument, ...], project_ids: tuple[str, ...]) -> list[dict[str, str]]:
    known = set(project_ids)
    if any(document.project_id not in known for document in documents):
        raise ValueError("search document references unknown project")
    return [
        document.to_dict()
        for document in sorted(
            documents,
            key=lambda item: (item.project_id, item.document_id, item.title, item.url, item.body),
        )
    ]


def _write_json(path: Path, value: object, gate: PrivacyGate) -> None:
    gate.require_safe(value)
    _write_bytes(path, canonical_json_bytes(value))


def _write_text(path: Path, value: str, gate: PrivacyGate) -> None:
    gate.require_safe(value)
    payload = value if value.endswith("\n") else value + "\n"
    _write_bytes(path, payload.encode("utf-8"))


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _load_text_tree(root: Path) -> dict[str, str]:
    tree = {}
    for relative_path, path in iter_tree_files(root):
        try:
            tree[relative_path] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"bundle artifact is not UTF-8: {relative_path}") from None
    return tree


def _privacy_tree(tree: Mapping[str, str]) -> dict[str, object]:
    rendered: dict[str, object] = {}
    for path, value in tree.items():
        if path.endswith(".json"):
            try:
                rendered[path] = json.loads(value, object_pairs_hook=lambda pairs: pairs)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON in {path}: {error.msg}") from None
        else:
            rendered[path] = value
    return rendered


def _validate_bundle(root: Path, tree: Mapping[str, str]) -> BundleManifest:
    manifest_payload = _parse_json(tree, "manifest.json")
    validate_schema(manifest_payload, "public-manifest")
    format_version = manifest_payload["format_version"]
    projects = tuple(manifest_payload["projects"])
    if projects != tuple(sorted(projects)):
        raise ValueError("manifest projects must use stable ordering")
    for project_id in projects:
        _require_project_id(project_id)

    project_artifacts = _project_artifacts(tree, projects, format_version)
    required_files, allowed_files = _public_file_sets(
        projects,
        format_version=format_version,
        artifacts=project_artifacts,
        include_manifest=True,
    )
    actual_files = set(tree)
    missing = sorted(required_files - actual_files)
    if missing:
        raise ValueError(f"bundle is missing required file: {missing[0]}")
    unexpected = sorted(actual_files - allowed_files)
    if unexpected:
        raise ValueError(f"bundle contains unexpected file: {unexpected[0]}")

    expected_hashes = dict(manifest_payload["files"])
    actual_hashes = bundle_file_hashes(root)
    if set(expected_hashes) != set(actual_hashes):
        raise ValueError("manifest files do not match the complete bundle tree")
    for path, digest in expected_hashes.items():
        if not isinstance(path, str) or not _safe_relative_path(path):
            raise ValueError(f"manifest contains unsafe file path: {path}")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError(f"manifest contains invalid SHA-256: {path}")
        if digest != actual_hashes[path]:
            raise ValueError(f"manifest file hash mismatch: {path}")

    _validate_exact_directories(root, projects, format_version, project_artifacts)
    project_hashes = {}
    project_payloads: dict[str, dict[str, object]] = {}
    for project_id in projects:
        payload = _parse_json(tree, f"projects/{project_id}/project.json")
        validate_schema(payload, "public-project")
        if payload["id"] != project_id:
            raise ValueError(f"project ID does not match bundle path: {project_id}")
        project_payloads[project_id] = payload
        project_hashes[project_id] = canonical_hash(
            {
                path: digest
                for path, digest in actual_hashes.items()
                if path.startswith(f"projects/{project_id}/")
            }
        )

    _validate_graph(
        _parse_json(tree, "graph/nodes.json"),
        _parse_json(tree, "graph/edges.json"),
        project_payloads,
    )
    project_set = set(projects)
    _validate_topics(_parse_json(tree, "topics.json"), project_set)
    _validate_changelog(_parse_json(tree, "changelog.json"), project_set)
    _validate_search_index(_parse_json(tree, "search-index.json"), project_set)
    expected_version = content_version(actual_hashes, project_hashes)
    if manifest_payload["version"] != expected_version:
        raise ValueError("manifest version is not content-derived from staged public bytes")
    return BundleManifest(
        version=manifest_payload["version"],
        projects=projects,
        files=expected_hashes,
        project_hashes=project_hashes,
        format_version=format_version,
    )


def _validate_previous_manifest(manifest: BundleManifest) -> None:
    try:
        validate_schema(manifest.to_dict(), "public-manifest")
        if manifest.projects != tuple(sorted(manifest.projects)):
            raise ValueError("projects are not sorted")
        for project_id in manifest.projects:
            _require_project_id(project_id)
        if set(manifest.project_hashes) != set(manifest.projects):
            raise ValueError("project hash keys do not match projects")
        for path, digest in manifest.files.items():
            if not _safe_relative_path(path) or path == "manifest.json":
                raise ValueError("file path is not a safe bundle-relative path")
            if _SHA256.fullmatch(digest) is None:
                raise ValueError("file hash is not SHA-256")
        if manifest.projects or manifest.files or manifest.project_hashes:
            required_files, allowed_files = _public_file_sets(
                manifest.projects,
                format_version=manifest.format_version,
                artifacts=None,
                include_manifest=False,
            )
            paths_are_allowed = (
                set(manifest.files).issubset(allowed_files)
                if manifest.format_version == 1
                else all(_is_v2_manifest_path(path, manifest.projects) for path in manifest.files)
            )
            if not paths_are_allowed:
                raise ValueError("file hashes contain an unexpected public path")
            if not required_files.issubset(manifest.files):
                raise ValueError("file hashes omit a required public path")
        expected_project_hashes = project_hashes_from_files(manifest.projects, manifest.files)
        for project_id in manifest.projects:
            if f"projects/{project_id}/project.json" not in manifest.files:
                raise ValueError("project file hash is missing")
            if manifest.project_hashes[project_id] != expected_project_hashes[project_id]:
                raise ValueError("project hash does not match file hashes")
        if manifest.version != content_version(manifest.files, manifest.project_hashes):
            raise ValueError("version does not match manifest hashes")
    except (TypeError, ValueError) as error:
        raise ValueError("previous manifest is inconsistent or stale") from error


def _changed_hash_ids(
    previous: Mapping[str, str],
    current: Mapping[str, str],
) -> tuple[str, ...]:
    return tuple(
        project_id
        for project_id in sorted(set(previous) | set(current))
        if previous.get(project_id) != current.get(project_id)
    )


def _public_file_sets(
    projects: tuple[str, ...],
    *,
    format_version: int,
    artifacts: Mapping[str, dict[str, object] | None] | None,
    include_manifest: bool,
) -> tuple[set[str], set[str]]:
    required = set(_MANDATORY_FILES)
    allowed = set(_MANDATORY_FILES)
    if not include_manifest:
        required.remove("manifest.json")
        allowed.remove("manifest.json")
    for project_id in projects:
        project_path = f"projects/{project_id}/project.json"
        required.add(project_path)
        allowed.add(project_path)
        if format_version == 1:
            allowed.update(
                f"projects/{project_id}/{path}" for path in _V1_OPTIONAL_PROJECT_FILES
            )
        elif format_version == 2:
            artifact = artifacts.get(project_id) if artifacts is not None else None
            if artifact is not None:
                allowed.add(f"projects/{project_id}/article.json")
                allowed.update(
                    f"projects/{project_id}/{path}" for path in _V2_OPTIONAL_PROJECT_FILES[1:]
                )
                allowed.update(
                    f"projects/{project_id}/visuals/{diagram_id}.svg"
                    for diagram_id in artifact["diagram_ids"]
                )
        else:
            raise ValueError("unsupported bundle format version")
    return required, allowed


def _project_artifacts(
    tree: Mapping[str, str],
    projects: tuple[str, ...],
    format_version: int,
) -> dict[str, dict[str, object] | None]:
    artifacts: dict[str, dict[str, object] | None] = {}
    for project_id in projects:
        if format_version == 1:
            for markdown_name in ("build-story.md", "decisions.md", "rollbacks.md"):
                markdown_path = f"projects/{project_id}/{markdown_name}"
                if markdown_path in tree and not tree[markdown_path].strip():
                    raise ValueError(f"optional project artifact must be non-empty: {markdown_path}")
            svg_path = f"projects/{project_id}/visuals/problem-solving.svg"
            if svg_path in tree:
                _validate_svg(tree[svg_path])
            artifacts[project_id] = None
            continue

        article_path = f"projects/{project_id}/article.json"
        has_article = article_path in tree
        content_paths = tuple(
            f"projects/{project_id}/{name}" for name in _V2_OPTIONAL_PROJECT_FILES[1:]
        )
        if not has_article:
            if any(path in tree for path in content_paths) or any(
                path.startswith(f"projects/{project_id}/visuals/") for path in tree
            ):
                raise ValueError("v2 project content requires article.json")
            artifacts[project_id] = None
            continue
        article = _parse_json(tree, article_path)
        validate_schema(article, "public-article")
        if article["project_id"] != project_id:
            raise ValueError("article project ID does not match bundle path")
        diagram_ids = tuple(
            diagram["id"]
            for section in article["sections"]
            for diagram in section.get("diagrams", [])
        )
        if len(diagram_ids) != len(set(diagram_ids)):
            raise ValueError("article diagram IDs must be unique")
        evidence_path = f"projects/{project_id}/evidence.json"
        evidence_ids: set[str] = set()
        if evidence_path in tree:
            evidence = _parse_json(tree, evidence_path)
            validate_schema(evidence, "public-evidence")
            evidence_ids = {item["id"] for item in evidence}
            if len(evidence_ids) != len(evidence):
                raise ValueError("public evidence IDs must be unique")
        referenced_evidence = {
            evidence_id
            for section in article["sections"]
            for evidence_id in section["evidence_ids"]
        } | {
            evidence_id
            for decision in article.get("decision_index", [])
            for evidence_id in decision["evidence_ids"]
        }
        if referenced_evidence - evidence_ids:
            raise ValueError("article references missing public evidence")
        timeline_path = f"projects/{project_id}/timeline.json"
        if timeline_path in tree:
            validate_schema(_parse_json(tree, timeline_path), "public-timeline")
        system_map_path = f"projects/{project_id}/system-map.svg"
        if system_map_path in tree:
            _validate_svg(tree[system_map_path])
        for diagram_id in diagram_ids:
            _validate_svg(_require_text(tree, f"projects/{project_id}/visuals/{diagram_id}.svg"))
        artifacts[project_id] = {"diagram_ids": diagram_ids}
    return artifacts


def _validate_exact_directories(
    root: Path,
    projects: tuple[str, ...],
    format_version: int,
    artifacts: Mapping[str, dict[str, object] | None],
) -> None:
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"bundle tree contains symlink: {path.relative_to(root).as_posix()}")
        if path.is_dir():
            actual.add(path.relative_to(root).as_posix())
    expected = {"projects", "graph"}
    for project_id in projects:
        expected.add(f"projects/{project_id}")
        if format_version == 1:
            if (root / "projects" / project_id / "visuals" / "problem-solving.svg").is_file():
                expected.add(f"projects/{project_id}/visuals")
            continue
        artifact = artifacts[project_id]
        if artifact is not None and artifact["diagram_ids"]:
            expected.add(f"projects/{project_id}/visuals")
    unexpected = sorted(actual - expected)
    if unexpected:
        raise ValueError(f"bundle contains unexpected directory: {unexpected[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"bundle is missing required directory: {missing[0]}")


def _require_text(tree: Mapping[str, str], path: str) -> str:
    value = tree.get(path)
    if value is None:
        raise ValueError(f"bundle is missing required file: {path}")
    return value


def _is_v2_manifest_path(path: str, projects: tuple[str, ...]) -> bool:
    if path in _MANDATORY_FILES - {"manifest.json"}:
        return True
    for project_id in projects:
        prefix = f"projects/{project_id}/"
        if path == prefix + "project.json" or path in {
            prefix + name for name in _V2_OPTIONAL_PROJECT_FILES
        }:
            return True
        visual = path.removeprefix(prefix + "visuals/")
        if visual != path and re.fullmatch(r"[a-z0-9][a-z0-9-]*\.svg", visual):
            return True
    return False


def _parse_json(tree: Mapping[str, str], path: str) -> object:
    if path not in tree:
        raise ValueError(f"bundle is missing required file: {path}")
    try:
        return json.loads(tree[path])
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error.msg}") from None


def _validate_graph_nodes(value: object) -> list[dict[str, object]]:
    records = _require_record_list(value, "graph nodes")
    seen = set()
    for record in records:
        _require_exact_keys(record, {"id", "label", "kind"}, "graph node")
        _require_non_empty_strings(record, ("id", "label", "kind"), "graph node")
        if record["kind"] not in GRAPH_NODE_KINDS:
            raise ValueError("graph node has unknown kind")
        if record["id"] in seen:
            raise ValueError("graph nodes require unique IDs")
        seen.add(record["id"])
    return records


def _validate_graph_edges(value: object) -> list[dict[str, object]]:
    records = _require_record_list(value, "graph edges")
    for record in records:
        _require_exact_keys(record, {"source", "target", "kind", "weight", "reasons"}, "graph edge")
        _require_non_empty_strings(record, ("source", "target", "kind"), "graph edge")
        if record["kind"] not in GRAPH_EDGE_KINDS:
            raise ValueError("graph edge has unknown kind")
        if not isinstance(record["weight"], int) or isinstance(record["weight"], bool) or record["weight"] <= 0:
            raise ValueError("graph edge weight must be a positive integer")
        if not _is_string_list(record["reasons"]):
            raise ValueError("graph edge reasons must be strings")
    return records


def _validate_graph(
    nodes_value: object,
    edges_value: object,
    projects: Mapping[str, dict[str, object]],
) -> None:
    nodes = _validate_graph_nodes(nodes_value)
    edges = _validate_graph_edges(edges_value)
    expected_nodes, expected_memberships, project_tags = _expected_graph(projects)
    actual_nodes = {str(node["id"]): node for node in nodes}
    if set(actual_nodes) != set(expected_nodes):
        raise ValueError("graph nodes do not match canonical project and tag IDs")
    for node_id, (kind, label) in expected_nodes.items():
        node = actual_nodes[node_id]
        if node["kind"] != kind or node["label"] != label:
            raise ValueError("graph node kind or label is not canonical")

    memberships: set[tuple[str, str]] = set()
    similarity_pairs: set[tuple[str, str]] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    degrees: dict[str, int] = defaultdict(int)
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        kind = str(edge["kind"])
        identity = (kind, source, target)
        if identity in seen_edges:
            raise ValueError("graph edges require unique directed pairs")
        seen_edges.add(identity)
        if source == target:
            raise ValueError("graph edges cannot be self edges")
        if source not in actual_nodes or target not in actual_nodes:
            raise ValueError("graph edge has a dangling endpoint")

        source_kind = str(actual_nodes[source]["kind"])
        target_kind = str(actual_nodes[target]["kind"])
        reasons = tuple(edge["reasons"])
        if kind == "tag-membership":
            if source_kind != "project" or target_kind == "project":
                raise ValueError("graph membership direction or tag kind is invalid")
            if edge["weight"] != 1 or reasons:
                raise ValueError("graph membership weight and reasons must be canonical")
            pair = (source, target)
            if pair in memberships:
                raise ValueError("graph membership pairs must be unique")
            memberships.add(pair)
            continue

        if source_kind != "project" or target_kind != "project":
            raise ValueError("graph similarity endpoints must both be projects")
        pair = tuple(sorted((source, target)))
        if (source, target) != pair:
            raise ValueError("graph similarity endpoints must use canonical ordering")
        if pair in similarity_pairs:
            raise ValueError("graph similarity pairs must be unique")
        similarity_pairs.add(pair)
        expected_reasons, expected_weight = _similarity_contract(
            source,
            target,
            project_tags,
            expected_nodes,
        )
        if reasons != expected_reasons or edge["weight"] != expected_weight:
            raise ValueError("graph similarity reasons or weight are not stable")
        degrees[source] += 1
        degrees[target] += 1
        if degrees[source] > 5 or degrees[target] > 5:
            raise ValueError("graph project similarity degree exceeds five")

    if memberships != expected_memberships:
        raise ValueError("graph membership edges do not match project tags")
    if similarity_pairs != _expected_similarity_pairs(project_tags, expected_nodes):
        raise ValueError("graph similarity edges do not match deterministic selection")


def _expected_graph(
    projects: Mapping[str, dict[str, object]],
) -> tuple[
    dict[str, tuple[str, str]],
    set[tuple[str, str]],
    dict[str, dict[str, set[str]]],
]:
    tag_labels: dict[tuple[str, str], list[str]] = defaultdict(list)
    project_tags: dict[str, dict[str, set[str]]] = {}
    for project_id, payload in projects.items():
        tags = payload["tags"]
        normalized_by_kind: dict[str, set[str]] = {}
        for kind in TAG_WEIGHTS:
            normalized_by_kind[kind] = {
                normalize_tag_label(label) for label in tags[kind]
            }
            for label in tags[kind]:
                tag_labels[(kind, normalize_tag_label(label))].append(
                    display_tag_label(label)
                )
        project_tags[_project_node_id(project_id)] = normalized_by_kind

    canonical_tag_labels = {
        key: min(values, key=lambda value: (normalize_tag_label(value), value))
        for key, values in tag_labels.items()
    }
    expected_nodes = {
        _project_node_id(project_id): ("project", str(payload["name"]))
        for project_id, payload in projects.items()
    }
    expected_nodes.update(
        {
            _tag_node_id(kind, identity): (kind, label)
            for (kind, identity), label in canonical_tag_labels.items()
        }
    )
    memberships = {
        (project_node_id, _tag_node_id(kind, identity))
        for project_node_id, by_kind in project_tags.items()
        for kind, identities in by_kind.items()
        for identity in identities
    }
    return expected_nodes, memberships, project_tags


def _similarity_contract(
    source: str,
    target: str,
    project_tags: Mapping[str, Mapping[str, set[str]]],
    expected_nodes: Mapping[str, tuple[str, str]],
) -> tuple[tuple[str, ...], int]:
    reasons = []
    weight = 0
    for kind, tag_weight in TAG_WEIGHTS.items():
        for identity in sorted(project_tags[source][kind] & project_tags[target][kind]):
            tag_id = _tag_node_id(kind, identity)
            reasons.append(f"{kind}:{expected_nodes[tag_id][1]}")
            weight += tag_weight
    if not reasons or weight <= 0:
        raise ValueError("graph similarity requires shared project tags")
    return tuple(reasons), weight


def _expected_similarity_pairs(
    project_tags: Mapping[str, Mapping[str, set[str]]],
    expected_nodes: Mapping[str, tuple[str, str]],
) -> set[tuple[str, str]]:
    project_ids = tuple(sorted(project_tags))
    candidates: list[tuple[int, str, str, tuple[str, ...]]] = []
    for index, source in enumerate(project_ids):
        for target in project_ids[index + 1 :]:
            try:
                reasons, weight = _similarity_contract(
                    source,
                    target,
                    project_tags,
                    expected_nodes,
                )
            except ValueError:
                continue
            candidates.append((weight, source, target, reasons))

    degrees: dict[str, int] = defaultdict(int)
    selected: set[tuple[str, str]] = set()
    for _, source, target, _ in sorted(
        candidates,
        key=lambda item: (-item[0], item[1], item[2], item[3]),
    ):
        if degrees[source] >= 5 or degrees[target] >= 5:
            continue
        degrees[source] += 1
        degrees[target] += 1
        selected.add((source, target))
    return selected


def _project_node_id(project_id: str) -> str:
    return f"project:{quote(project_id, safe='')}"


def _tag_node_id(kind: str, identity: str) -> str:
    return f"{kind}:{quote(identity, safe='')}"


def _validate_topics(value: object, project_ids: set[str]) -> None:
    records = _require_record_list(value, "topics")
    for record in records:
        _require_exact_keys(record, {"kind", "label", "project_ids"}, "topic")
        _require_non_empty_strings(record, ("kind", "label"), "topic")
        if record["kind"] not in GRAPH_NODE_KINDS - {"project"}:
            raise ValueError("topic has unknown kind")
        if not _is_string_list(record["project_ids"], non_empty=True):
            raise ValueError("topic project_ids must be non-empty strings")
        if tuple(record["project_ids"]) != tuple(sorted(set(record["project_ids"]))):
            raise ValueError("topic project_ids must be unique and sorted")
        if not set(record["project_ids"]) <= project_ids:
            raise ValueError("topic references unknown project")


def _validate_changelog(value: object, project_ids: set[str]) -> None:
    records = _require_record_list(value, "changelog")
    required = {"project_id", "event_id", "title", "stage", "context", "decision", "outcome"}
    for record in records:
        if set(record) not in (required, required | {"date"}):
            raise ValueError("changelog entry has unexpected or missing fields")
        _require_non_empty_strings(record, ("project_id", "event_id", "title", "stage"), "changelog entry")
        for field in ("context", "decision", "outcome"):
            if not isinstance(record[field], str):
                raise ValueError(f"changelog entry {field} must be a string")
        if record["project_id"] not in project_ids:
            raise ValueError("changelog references unknown project")
        if "date" in record and (not isinstance(record["date"], str) or _DATE.fullmatch(record["date"]) is None):
            raise ValueError("changelog date must be source-supplied YYYY-MM-DD")


def _validate_search_index(value: object, project_ids: set[str]) -> None:
    records = _require_record_list(value, "search index")
    for record in records:
        _require_exact_keys(record, {"id", "project_id", "title", "body", "url"}, "search document")
        _require_non_empty_strings(record, ("id", "project_id", "title", "url"), "search document")
        if not isinstance(record["body"], str):
            raise ValueError("search document body must be a string")
        if record["project_id"] not in project_ids:
            raise ValueError("search document references unknown project")
        if not record["url"].startswith("/projects/"):
            raise ValueError("search document URL must be a project-relative route")


def _validate_svg(svg: str) -> None:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise ValueError(f"invalid SVG XML: {error}") from None
    if root.tag != _SVG_TAG:
        raise ValueError("SVG artifact requires an SVG namespace root")
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1].casefold()
        if local_name in {"script", "foreignobject"}:
            raise ValueError(f"SVG artifact contains forbidden element: {local_name}")
        for attribute in element.attrib:
            attribute_name = attribute.rsplit("}", 1)[-1].casefold()
            if attribute_name == "href" or attribute_name.startswith("on"):
                raise ValueError(f"SVG artifact contains active attribute: {attribute_name}")


def _require_record_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _require_exact_keys(record: dict[str, object], keys: set[str], label: str) -> None:
    if set(record) != keys:
        raise ValueError(f"{label} has unexpected or missing fields")


def _require_non_empty_strings(record: dict[str, object], fields: tuple[str, ...], label: str) -> None:
    if any(not isinstance(record[field], str) or not record[field] for field in fields):
        raise ValueError(f"{label} fields must be non-empty strings")


def _is_string_list(value: object, *, non_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not non_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
    )


def _require_project_id(project_id: str) -> None:
    if not _safe_project_id(project_id):
        raise ValueError(f"unsafe project ID: {project_id}")


def _safe_project_id(project_id: str) -> bool:
    return (
        isinstance(project_id, str)
        and bool(project_id)
        and project_id not in {".", ".."}
        and "/" not in project_id
        and "\\" not in project_id
        and "\x00" not in project_id
    )


def _safe_relative_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return not candidate.is_absolute() and ".." not in candidate.parts and path == candidate.as_posix()


def _changed_project_ids(
    staging_dir: Path,
    public_dir: Path,
    candidate_manifest: BundleManifest,
) -> tuple[str, ...]:
    current_projects: tuple[str, ...] = ()
    if public_dir.exists():
        current_tree = _load_text_tree(public_dir)
        current_payload = _parse_json(current_tree, "manifest.json")
        validate_schema(current_payload, "public-manifest")
        current_projects = tuple(current_payload["projects"])
    changed = []
    for project_id in sorted(set(candidate_manifest.projects) | set(current_projects)):
        candidate_path = staging_dir / "projects" / project_id
        current_path = public_dir / "projects" / project_id
        candidate_hash = tree_hash(candidate_path) if candidate_path.exists() else None
        current_hash = tree_hash(current_path) if current_path.exists() else None
        if candidate_hash != current_hash:
            changed.append(project_id)
    return tuple(changed)


def _require_safe_destination(public_dir: Path) -> None:
    require_no_symlink_path(public_dir)
    if public_dir.is_symlink():
        raise ValueError(f"public bundle root is a symlink: {public_dir}")
    if public_dir.exists() and not public_dir.is_dir():
        raise ValueError(f"public bundle root is not a directory: {public_dir}")
    public_dir.parent.mkdir(parents=True, exist_ok=True)


def _require_same_filesystem(staging_dir: Path, destination_parent: Path) -> None:
    destination_parent.mkdir(parents=True, exist_ok=True)
    if staging_dir.stat().st_dev != destination_parent.stat().st_dev:
        raise OSError("bundle promotion requires staging and public directory on the same filesystem")


def _restore_backup(
    backup: Path,
    public_dir: Path,
    recovery: Path,
    gate: PrivacyGate,
    last_good_hash: str | None,
) -> None:
    try:
        _rename(backup, public_dir)
        return
    except (OSError, ValueError):
        pass

    try:
        _copytree(backup, recovery)
    except (OSError, ValueError) as copy_error:
        _best_effort_cleanup(recovery)
        raise BundleRecoveryError("recovery copy failed; intact backup retained") from copy_error

    try:
        recovery_tree = _load_text_tree(recovery)
        gate.require_safe(_privacy_tree(recovery_tree))
        _validate_bundle(recovery, recovery_tree)
        if last_good_hash is None or tree_hash(recovery) != last_good_hash:
            raise ValueError("recovery tree does not match last-good bytes")
    except (OSError, ValueError) as validation_error:
        _best_effort_cleanup(recovery)
        raise BundleRecoveryError("recovery validation failed; intact backup retained") from validation_error

    try:
        _rename(recovery, public_dir)
    except (OSError, ValueError) as rename_error:
        _best_effort_cleanup(recovery)
        raise BundleRecoveryError("recovery rename failed; intact backup retained") from rename_error

    try:
        _cleanup_tree(backup)
    except (OSError, ValueError):
        pass


def _copytree(source: Path, target: Path) -> None:
    require_no_symlink_path(source)
    require_no_symlink_path(target)
    shutil.copytree(source, target, symlinks=True)


def _cleanup_tree(path: Path) -> None:
    require_no_symlink_path(path)
    shutil.rmtree(path)


def _best_effort_cleanup(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    try:
        _cleanup_tree(path)
    except (OSError, ValueError):
        pass


def _rename(source: Path, target: Path) -> None:
    require_no_symlink_path(source)
    require_no_symlink_path(target)
    os.replace(source, target)
