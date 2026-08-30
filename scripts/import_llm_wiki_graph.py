#!/usr/bin/env python3
"""Audit the legacy LLM Wiki graph without writing migration artifacts."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from atlas_worker.kg import KnowledgeTaxonomy
from atlas_worker.taxonomy import normalize_tag_label


APPROVED_NODE_TYPES = (
    "Artifact",
    "KnowledgeDomain",
    "KnowledgeFocus",
    "KnowledgeTag",
    "Project",
    "Technology",
)
APPROVED_EDGE_TYPES = (
    "ARTIFACT_HAS_TAG",
    "FOCUS_HAS_TAG",
    "HAS_FOCUS",
    "HAS_SUBTAG",
    "HAS_TAG",
    "PRODUCES_ARTIFACT",
    "USES_TECH",
)
NAME_DERIVED_EDGE_TYPES = frozenset({"SHARES_FOCUS", "SHARES_TAG"})


def _type_identity(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


NODE_TYPE_ALIASES = {_type_identity(value): value for value in APPROVED_NODE_TYPES}
EDGE_TYPE_ALIASES = {_type_identity(value): value for value in APPROVED_EDGE_TYPES}
EDGE_TYPE_ALIASES.update({_type_identity(value): value for value in NAME_DERIVED_EDGE_TYPES})


@dataclass(frozen=True)
class AuditReport:
    accepted_node_types: frozenset[str]
    rejected_edge_types: frozenset[str]
    output_edge_types: frozenset[str]
    accepted_node_count: int
    rejected_node_count: int
    unmapped_node_count: int
    accepted_edge_count: int
    rejected_edge_count: int
    unmapped_edge_count: int
    node_type_counts: Mapping[str, int]
    edge_type_counts: Mapping[str, int]
    rejected_relation_counts: Mapping[str, int]
    rejection_counts: Mapping[str, int]
    suggested_taxonomy_aliases: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_node_types": sorted(self.accepted_node_types),
            "counts": {
                "accepted_edges": self.accepted_edge_count,
                "accepted_nodes": self.accepted_node_count,
                "rejected_edges": self.rejected_edge_count,
                "rejected_nodes": self.rejected_node_count,
                "unmapped_edges": self.unmapped_edge_count,
                "unmapped_nodes": self.unmapped_node_count,
            },
            "edge_type_counts": dict(sorted(self.edge_type_counts.items())),
            "mode": "audit-only",
            "node_type_counts": dict(sorted(self.node_type_counts.items())),
            "output_edge_types": sorted(self.output_edge_types),
            "rejected_edge_types": sorted(self.rejected_edge_types),
            "rejected_relation_counts": dict(sorted(self.rejected_relation_counts.items())),
            "rejection_counts": dict(sorted(self.rejection_counts.items())),
            "suggested_taxonomy_aliases": list(self.suggested_taxonomy_aliases),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _graph_directory(source: str | Path) -> Path:
    path = Path(source)
    nested = path / "knowledge-graph"
    return nested if nested.is_dir() else path


def _read_csv(path: Path, required_fields: frozenset[str]) -> tuple[dict[str, str], ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)) or not required_fields <= set(fieldnames):
            raise ValueError(f"legacy-graph-csv-shape: {path.name}")
        return tuple(
            {key: value or "" for key, value in row.items() if key is not None}
            for row in reader
        )


def _reviewed_taxonomy(value: KnowledgeTaxonomy | Mapping[str, object] | str | Path) -> KnowledgeTaxonomy:
    if isinstance(value, KnowledgeTaxonomy):
        return value
    if isinstance(value, (str, Path)):
        return KnowledgeTaxonomy.from_file(value)
    return KnowledgeTaxonomy.from_mapping(value)


def _taxonomy_aliases(taxonomy: KnowledgeTaxonomy) -> dict[str, frozenset[str]]:
    return {
        "KnowledgeFocus": frozenset(
            normalize_tag_label(value)
            for item in taxonomy.focuses
            for value in (item.label, *item.aliases)
        ),
        "KnowledgeDomain": frozenset(
            normalize_tag_label(value)
            for item in taxonomy.domains
            for value in (item.label, *item.aliases)
        ),
        "KnowledgeTag": frozenset(
            normalize_tag_label(value)
            for item in taxonomy.tags
            for value in (item.label, *item.aliases)
        ),
    }


def _contains_raw_locator(row: Mapping[str, str]) -> bool:
    for key, value in row.items():
        identity = key.strip().lower()
        if not value.strip():
            continue
        if "locator" in identity or "path" in identity:
            return True
    return False


def _normalized_type(value: str, aliases: Mapping[str, str]) -> str | None:
    return aliases.get(_type_identity(value.strip()))


def audit_llm_wiki_graph(
    source: str | Path,
    taxonomy: KnowledgeTaxonomy | Mapping[str, object] | str | Path,
) -> AuditReport:
    """Return deterministic migration counts without creating or modifying files."""
    graph_directory = _graph_directory(source)
    node_rows = _read_csv(
        graph_directory / "nodes.csv",
        frozenset({"id", "type", "name"}),
    )
    edge_rows = _read_csv(
        graph_directory / "edges.csv",
        frozenset({"source", "target", "type"}),
    )
    taxonomy_aliases = _taxonomy_aliases(_reviewed_taxonomy(taxonomy))

    accepted_node_types: set[str] = set()
    accepted_node_ids: set[str] = set()
    node_type_counts: dict[str, int] = {}
    rejection_counts: dict[str, int] = {}
    suggested_aliases: set[tuple[str, str]] = set()
    accepted_node_count = 0
    rejected_node_count = 0
    unmapped_node_count = 0

    for row in node_rows:
        node_type = _normalized_type(row["type"], NODE_TYPE_ALIASES)
        if node_type is None:
            unmapped_node_count += 1
            continue
        _increment(node_type_counts, node_type)
        if _contains_raw_locator(row):
            rejected_node_count += 1
            _increment(rejection_counts, "raw_locator")
            continue
        node_id = row["id"].strip()
        if not node_id or node_id in accepted_node_ids:
            rejected_node_count += 1
            _increment(rejection_counts, "duplicate_or_missing_node_id")
            continue
        if node_type in taxonomy_aliases:
            label = row["name"].strip()
            if normalize_tag_label(label) not in taxonomy_aliases[node_type]:
                unmapped_node_count += 1
                suggested_aliases.add((node_type, label))
                continue
        accepted_node_ids.add(node_id)
        accepted_node_types.add(node_type)
        accepted_node_count += 1

    accepted_edge_types: set[str] = set()
    rejected_edge_types: set[str] = set()
    edge_type_counts: dict[str, int] = {}
    rejected_relation_counts: dict[str, int] = {}
    accepted_edge_count = 0
    rejected_edge_count = 0
    unmapped_edge_count = 0

    for row in edge_rows:
        raw_edge_type = row["type"].strip()
        edge_type = _normalized_type(raw_edge_type, EDGE_TYPE_ALIASES)
        if edge_type is None:
            unmapped_edge_count += 1
            continue
        _increment(edge_type_counts, edge_type)
        if edge_type in NAME_DERIVED_EDGE_TYPES:
            rejected_edge_count += 1
            rejected_edge_types.add(edge_type)
            _increment(rejected_relation_counts, edge_type)
            _increment(rejection_counts, "name_derived_relation")
            continue
        if _contains_raw_locator(row):
            rejected_edge_count += 1
            _increment(rejection_counts, "raw_locator")
            continue
        source_id = row["source"].strip()
        target_id = row["target"].strip()
        endpoints = (source_id, target_id)
        if any(value.startswith("project:") and value not in accepted_node_ids for value in endpoints):
            rejected_edge_count += 1
            _increment(rejection_counts, "unknown_project_id")
            continue
        if any(not value or value not in accepted_node_ids for value in endpoints):
            rejected_edge_count += 1
            _increment(rejection_counts, "missing_endpoint")
            continue
        accepted_edge_types.add(edge_type)
        accepted_edge_count += 1

    return AuditReport(
        accepted_node_types=frozenset(accepted_node_types),
        rejected_edge_types=frozenset(rejected_edge_types),
        output_edge_types=frozenset(accepted_edge_types),
        accepted_node_count=accepted_node_count,
        rejected_node_count=rejected_node_count,
        unmapped_node_count=unmapped_node_count,
        accepted_edge_count=accepted_edge_count,
        rejected_edge_count=rejected_edge_count,
        unmapped_edge_count=unmapped_edge_count,
        node_type_counts=dict(sorted(node_type_counts.items())),
        edge_type_counts=dict(sorted(edge_type_counts.items())),
        rejected_relation_counts=dict(sorted(rejected_relation_counts.items())),
        rejection_counts=dict(sorted(rejection_counts.items())),
        suggested_taxonomy_aliases=tuple(
            {"kind": kind, "label": label}
            for kind, label in sorted(suggested_aliases)
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Legacy llm_wiki root or knowledge-graph directory")
    parser.add_argument("--taxonomy", required=True, help="Reviewed taxonomy YAML")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        report = audit_llm_wiki_graph(args.source, args.taxonomy)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(report.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
