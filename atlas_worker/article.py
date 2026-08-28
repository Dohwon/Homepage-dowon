"""Load curated Project Atlas articles from confined local project memory."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

import yaml

from .content_audit import ArticleValidationFinding, ArticleValidationReport
from .fs_safety import read_confined_text, require_confined_directory
from .models import (
    ArticleSection,
    DecisionIndexEntry,
    DiagramRef,
    EvidenceRecord,
    ProjectArticle,
    ProjectRef,
    validate_public_evidence_url,
    validate_schema,
)
from .privacy import PrivacyGate
from .visuals import validate_curated_svg


_SOURCE_DIRECTORY = Path("project_memory") / "project-atlas"
_STABLE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_CONTENT_HASH = re.compile(r"^[a-f0-9]{64}$")
_MAX_CURATED_YAML_BYTES = 128 * 1024
_MAX_CURATED_YAML_NODES = 1024
_MAX_CURATED_YAML_EVENTS = 4096
_MAX_CURATED_YAML_DEPTH = 64
_EVIDENCE_KEYS = frozenset(
    {
        "id",
        "project_id",
        "label",
        "source_type",
        "source_locator",
        "observed_at",
        "privacy_class",
        "content_hash",
        "claim_role",
        "url",
    }
)
_EVIDENCE_REQUIRED = frozenset(
    {
        "id",
        "project_id",
        "label",
        "source_type",
        "source_locator",
        "observed_at",
        "privacy_class",
        "content_hash",
    }
)
_EVIDENCE_SOURCES = frozenset({"session", "spec", "code", "test", "git", "project_memory"})
_EVIDENCE_PRIVACY = frozenset({"public-safe", "private", "secret"})
_EVIDENCE_ROLES = frozenset({"supports", "contradicts", "context", "supersedes"})


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses duplicate or merged mappings."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise ValueError("YAML merge keys are not allowed")
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("YAML mapping keys must be strings")
        if key in values:
            raise ValueError(f"duplicate YAML key: {key}")
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_project_article(ref: ProjectRef, gate: PrivacyGate | None = None) -> ProjectArticle | None:
    """Load one validated article and every SVG referenced by its schema-only IDs."""
    root, source = _curated_source_root(ref, gate)
    try:
        data = _load_yaml_mapping(source / "article.yaml", root, gate, "article")
    except FileNotFoundError:
        return None
    validate_schema(data, "project-article")
    if data["project_id"] != ref.project_id:
        raise ValueError("article project_id does not match project ref")

    evidence = _load_project_evidence(ref, root, source, gate, article_present=True)
    evidence_ids = {record.evidence_id for record in evidence}
    sections = _load_sections(data["sections"], source, root, gate, evidence_ids)
    decisions = _load_decisions(data.get("decision_index", []), sections, evidence_ids)
    return ProjectArticle(
        project_id=data["project_id"],
        title=data["title"],
        summary=data["summary"],
        readiness=data["readiness"],
        sections=sections,
        prior_context=data.get("prior_context", ""),
        decision_index=decisions,
    )


def load_project_evidence(ref: ProjectRef, gate: PrivacyGate | None = None) -> tuple[EvidenceRecord, ...]:
    """Load strict evidence records; an absent article is the only empty-state case."""
    root, source = _curated_source_root(ref, gate)
    try:
        read_confined_text(source / "article.yaml", root, gate)
    except FileNotFoundError:
        return ()
    return _load_project_evidence(ref, root, source, gate, article_present=True)


def load_system_map(ref: ProjectRef, gate: PrivacyGate | None = None) -> str | None:
    """Load the optional project system map through the same structured SVG gate."""
    root, source = _curated_source_root(ref, gate)
    try:
        svg = read_confined_text(source / "system-map.svg", root, gate)
    except FileNotFoundError:
        return None
    validate_curated_svg(svg, label="system-map-svg")
    return svg


def lint_article_title(title: str) -> tuple[str, ...]:
    """Return stable, neutral-copy findings without changing author-provided text."""
    value = title.strip()
    findings: list[str] = []
    if not value:
        findings.append("blank-title")
    if re.search(r"순간.*함께", value, re.I):
        findings.append("dramatic-copy")
    if re.search(r"드디어|마침내|완벽한|혁신적|압도적", value, re.I):
        findings.append("superlative-copy")
    if re.search(r"[!?]{2,}", value):
        findings.append("excessive-punctuation")
    if len(value) > 60:
        findings.append("title-too-long")
    return tuple(findings)


def validate_article_diagrams(article: ProjectArticle) -> tuple[str, ...]:
    """Re-check loaded diagram payloads before the audit grants readiness."""
    findings: list[str] = []
    diagram_ids: set[str] = set()
    for section in article.sections:
        for diagram in section.diagrams:
            if diagram.diagram_id in diagram_ids:
                findings.append("duplicate-diagram-id")
            diagram_ids.add(diagram.diagram_id)
            try:
                validate_curated_svg(diagram.svg, label="article-svg")
            except ValueError:
                findings.append("invalid-diagram-svg")
    return tuple(dict.fromkeys(findings))


class ArticleValidator:
    """Task 4 audit callable for article titles and already-loaded diagram bytes."""

    def __call__(self, article: ProjectArticle) -> ArticleValidationReport:
        findings = [ArticleValidationFinding("title", code) for code in lint_article_title(article.title)]
        findings.extend(
            ArticleValidationFinding("diagram", code)
            for code in validate_article_diagrams(article)
        )
        return ArticleValidationReport(title_checked=True, diagrams_checked=True, findings=tuple(findings))


def _curated_source_root(ref: ProjectRef, gate: PrivacyGate | None) -> tuple[Path, Path]:
    root = ref.root
    require_confined_directory(root, root, gate)
    return root, root / _SOURCE_DIRECTORY


def _load_yaml_mapping(path: Path, root: Path, gate: PrivacyGate | None, label: str) -> dict[str, Any]:
    value = _load_yaml(path, root, gate, label)
    if not isinstance(value, dict):
        raise ValueError(f"{label} YAML must be a mapping")
    return value


def _load_yaml(path: Path, root: Path, gate: PrivacyGate | None, label: str) -> Any:
    try:
        text = read_confined_text(path, root, gate, max_bytes=_MAX_CURATED_YAML_BYTES)
        _validate_yaml_budget(text)
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except ValueError:
        raise
    except yaml.YAMLError as error:
        raise ValueError(f"invalid {label} YAML") from error


def _validate_yaml_budget(text: str) -> None:
    depth = 0
    nodes = 0
    for events, event in enumerate(yaml.parse(text, Loader=_UniqueKeyLoader), start=1):
        if events > _MAX_CURATED_YAML_EVENTS:
            raise ValueError("YAML event limit exceeded")
        if isinstance(event, yaml.events.AliasEvent):
            raise ValueError("YAML aliases are not allowed")
        if getattr(event, "anchor", None) is not None:
            raise ValueError("YAML anchors are not allowed")
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
            depth += 1
            nodes += 1
            if depth > _MAX_CURATED_YAML_DEPTH:
                raise ValueError("YAML nesting limit exceeded")
        elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
            depth -= 1
        elif isinstance(event, yaml.events.ScalarEvent):
            nodes += 1
        if nodes > _MAX_CURATED_YAML_NODES:
            raise ValueError("YAML node limit exceeded")


def _load_project_evidence(
    ref: ProjectRef,
    root: Path,
    source: Path,
    gate: PrivacyGate | None,
    *,
    article_present: bool,
) -> tuple[EvidenceRecord, ...]:
    try:
        data = _load_yaml(source / "evidence.yaml", root, gate, "evidence")
    except FileNotFoundError:
        if article_present:
            raise ValueError("evidence.yaml is required when article.yaml exists") from None
        return ()
    if not isinstance(data, list):
        raise ValueError("evidence YAML must be a list")
    records = tuple(_evidence_record(item, ref.project_id) for item in data)
    _require_unique((record.evidence_id for record in records), "evidence id")
    return records


def _evidence_record(value: Any, project_id: str) -> EvidenceRecord:
    if not isinstance(value, dict):
        raise ValueError("evidence record must be a mapping")
    keys = frozenset(value)
    unexpected = keys - _EVIDENCE_KEYS
    missing = _EVIDENCE_REQUIRED - keys
    if unexpected:
        raise ValueError(f"evidence has unallowed keys: {sorted(unexpected)[0]}")
    if missing:
        raise ValueError(f"evidence is missing required key: {sorted(missing)[0]}")
    if not isinstance(value["id"], str) or not _STABLE_ID.fullmatch(value["id"]):
        raise ValueError("evidence id must be a stable id")
    if not isinstance(value["project_id"], str) or value["project_id"] != project_id:
        raise ValueError("evidence project_id does not match project ref")
    if not isinstance(value["label"], str) or not value["label"].strip():
        raise ValueError("evidence label must be nonempty")
    if not isinstance(value["source_type"], str) or value["source_type"] not in _EVIDENCE_SOURCES:
        raise ValueError("evidence source_type is invalid")
    if not isinstance(value["source_locator"], str) or not value["source_locator"].strip():
        raise ValueError("evidence source_locator must be nonempty")
    if not isinstance(value["observed_at"], str) or not _RFC3339.fullmatch(value["observed_at"]):
        raise ValueError("evidence observed_at must be RFC3339")
    try:
        datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("evidence observed_at must be RFC3339") from None
    if not isinstance(value["privacy_class"], str) or value["privacy_class"] not in _EVIDENCE_PRIVACY:
        raise ValueError("evidence privacy_class is invalid")
    if not isinstance(value["content_hash"], str) or not _CONTENT_HASH.fullmatch(value["content_hash"]):
        raise ValueError("evidence content_hash must be a lowercase SHA-256")
    role = value.get("claim_role", "supports")
    if not isinstance(role, str) or role not in _EVIDENCE_ROLES:
        raise ValueError("evidence claim_role is invalid")
    url = value.get("url")
    if url is not None:
        validate_public_evidence_url(url)
    return EvidenceRecord(
        evidence_id=value["id"],
        project_id=value["project_id"],
        label=value["label"],
        source_type=value["source_type"],
        source_locator=value["source_locator"],
        observed_at=value["observed_at"],
        privacy_class=value["privacy_class"],
        content_hash=value["content_hash"],
        claim_role=role,
        url=url,
    )


def _load_sections(
    values: list[dict[str, Any]],
    source: Path,
    root: Path,
    gate: PrivacyGate | None,
    evidence_ids: set[str],
) -> tuple[ArticleSection, ...]:
    _require_unique((value["id"] for value in values), "section id")
    diagram_ids: set[str] = set()
    sections: list[ArticleSection] = []
    for value in values:
        section_evidence = _validated_references(value["evidence_ids"], evidence_ids, "section evidence")
        diagrams: list[DiagramRef] = []
        for diagram in value.get("diagrams", []):
            diagram_id = diagram["id"]
            if diagram_id in diagram_ids:
                raise ValueError("duplicate diagram id")
            diagram_ids.add(diagram_id)
            path = source / "visuals" / f"{diagram_id}.svg"
            svg = read_confined_text(path, root, gate)
            validate_curated_svg(svg, label="article-svg")
            diagrams.append(
                DiagramRef(
                    diagram_id=diagram_id,
                    source_path=path.relative_to(root).as_posix(),
                    caption=diagram["caption"],
                    alt=diagram["alt"],
                    svg=svg,
                )
            )
        sections.append(
            ArticleSection(
                section_id=value["id"],
                title=value["title"],
                section_type=value["section_type"],
                body=value["body"],
                evidence_ids=section_evidence,
                diagrams=tuple(diagrams),
            )
        )
    return tuple(sections)


def _load_decisions(
    values: list[dict[str, Any]],
    sections: tuple[ArticleSection, ...],
    evidence_ids: set[str],
) -> tuple[DecisionIndexEntry, ...]:
    _require_unique((value["decision_id"] for value in values), "decision id")
    section_ids = {section.section_id for section in sections}
    decisions: list[DecisionIndexEntry] = []
    for value in values:
        if value["section_id"] not in section_ids:
            raise ValueError("decision section_id does not reference an article section")
        decisions.append(
            DecisionIndexEntry(
                decision_id=value["decision_id"],
                section_id=value["section_id"],
                status=value["status"],
                evidence_ids=_validated_references(
                    value["evidence_ids"], evidence_ids, "decision evidence"
                ),
            )
        )
    return tuple(decisions)


def _validated_references(values: list[str], available: set[str], label: str) -> tuple[str, ...]:
    _require_unique(values, f"{label} reference")
    missing = sorted(set(values) - available)
    if missing:
        raise ValueError(f"missing {label} reference: {missing[0]}")
    return tuple(values)


def _require_unique(values: Any, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label}")
        seen.add(value)
