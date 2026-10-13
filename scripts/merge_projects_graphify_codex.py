#!/usr/bin/env python3
"""Merge reviewed Codex semantic fragments into the private Graphify source graph.

Fragments follow .agents/skills/graphify/references/extraction-spec.md. The
existing priority graph supplies Graphify AST and earlier semantic extraction;
the full scan manifest supplies the denominator for an honest coverage report.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / ".local-graphify"
FULL = PRIVATE / "full"
STAGE = FULL / "source"
FRAGMENTS = FULL / "codex-batches"
BASE = PRIVATE / "priority" / "source" / "graphify-out" / "graph.json"
OUTPUT = STAGE / "graphify-out" / "graph.json"
STRUCTURED = FULL / "structured-data.json"
OCR_FRAGMENT = FRAGMENTS / "0006.json"
OCR_STATUS = FULL / "ocr-index-status.json"
DOCUMENT_FRAGMENT = FRAGMENTS / "0008.json"
DOCUMENT_STATUS = FULL / "document-index-status.json"
DETERMINISTIC_FRAGMENTS = {OCR_FRAGMENT, DOCUMENT_FRAGMENT}
SEMANTIC_KINDS = {"document", "office", "paper", "image"}
CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


def load_fragment(file: Path, known_ids: set[str]) -> tuple[dict, set[str]]:
    data = json.loads(file.read_text(encoding="utf8"))
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in ("nodes", "edges", "hyperedges")):
        raise ValueError(f"invalid Graphify fragment: {file}")
    source_files = set()
    def staged_source(value: str) -> Path:
        source = Path(value)
        return (source if source.is_absolute() else STAGE / source).resolve()
    for node in data["nodes"]:
        source = staged_source(node["source_file"])
        if not source.is_file() or not source.is_relative_to(STAGE):
            raise ValueError(f"fragment source outside staged corpus: {source}")
        if not node.get("id") or not node.get("label"):
            raise ValueError(f"fragment node missing identity: {file}")
        source_files.add(source.relative_to(STAGE).as_posix())
        known_ids.add(node["id"])
    for edge in data["edges"]:
        if edge.get("source") not in known_ids or edge.get("target") not in known_ids:
            raise ValueError(f"fragment edge has missing endpoint: {file}")
        if edge.get("confidence") not in CONFIDENCE or not isinstance(edge.get("confidence_score"), (float, int)):
            raise ValueError(f"fragment edge has invalid confidence: {file}")
        source = staged_source(edge["source_file"])
        if not source.is_file() or not source.is_relative_to(STAGE):
            raise ValueError(f"fragment edge source outside staged corpus: {file}")
    for hyperedge in data["hyperedges"]:
        if any(node not in known_ids for node in hyperedge.get("nodes", [])):
            raise ValueError(f"fragment hyperedge has missing endpoint: {file}")
    return data, source_files


def main() -> None:
    manifest = json.loads((FULL / "scan-manifest.json").read_text(encoding="utf8"))
    base = json.loads(BASE.read_text(encoding="utf8"))
    merged = {"nodes": list(base["nodes"]), "edges": list(base["links"]), "hyperedges": list(base.get("hyperedges", []))}
    known_ids = {node["id"] for node in merged["nodes"]}
    files_with_codex_nodes = set()
    fragment_files = sorted(FRAGMENTS.glob("[0-9][0-9][0-9][0-9].json"))
    for file in fragment_files:
        fragment, files = load_fragment(file, known_ids)
        if file not in DETERMINISTIC_FRAGMENTS:
            files_with_codex_nodes.update(files)
        merged["nodes"].extend(fragment["nodes"])
        merged["edges"].extend(fragment["edges"])
        merged["hyperedges"].extend(fragment["hyperedges"])
    structured_status = None
    ocr_status = json.loads(OCR_STATUS.read_text(encoding="utf8")) if OCR_FRAGMENT.is_file() and OCR_STATUS.is_file() else None
    document_status = json.loads(DOCUMENT_STATUS.read_text(encoding="utf8")) if DOCUMENT_FRAGMENT.is_file() and DOCUMENT_STATUS.is_file() else None
    if STRUCTURED.is_file():
        structured = json.loads(STRUCTURED.read_text(encoding="utf8"))
        if any(not isinstance(structured.get(key), list) for key in ("nodes", "edges", "hyperedges")):
            raise ValueError("invalid structured data Graphify fragment")
        merged["nodes"].extend(structured["nodes"])
        merged["edges"].extend(structured["edges"])
        merged["hyperedges"].extend(structured["hyperedges"])
        structured_status = json.loads((FULL / "structured-data-status.json").read_text(encoding="utf8"))
    if not fragment_files:
        raise SystemExit("No reviewed Codex fragments; preserving the current graph")
    graph = build_from_json(merged, root=STAGE)
    if graph.number_of_nodes() < len(base["nodes"]):
        raise RuntimeError("merged graph unexpectedly lost base nodes")
    communities = cluster(graph)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not to_json(graph, communities, str(OUTPUT), force=True):
        raise RuntimeError("Graphify refused to write the merged graph")
    semantic_total = sum(manifest["staged_files"].get(kind, 0) for kind in SEMANTIC_KINDS)
    status = {
        "mode": "codex_incremental",
        "complete": False,
        "semantic_files_staged": semantic_total,
        "codex_files_with_nodes": len(files_with_codex_nodes),
        "codex_fragment_files": len(fragment_files) - sum(file.is_file() for file in DETERMINISTIC_FRAGMENTS),
        "ocr_pdf_files_indexed": ocr_status["pdf_files"] if ocr_status else 0,
        "ocr_pages_indexed": ocr_status["pages"] if ocr_status else 0,
        "ocr_terms_unreviewed": ocr_status["unique_terms"] if ocr_status else 0,
        "document_files_indexed": document_status["files_indexed"].get("document", 0) if document_status else 0,
        "office_files_indexed": document_status["files_indexed"].get("office", 0) if document_status else 0,
        "office_metadata_only_files": document_status["large_workbooks_metadata_only"] if document_status else 0,
        "document_index_failures": len(document_status["failed_files"]) if document_status else 0,
        "structured_files_indexed": sum(structured_status["files_indexed"].values()) if structured_status else 0,
        "structured_failed_files": len(structured_status["failed_files"]) if structured_status else 0,
        "previous_priority_extraction": json.loads((PRIVATE / "priority" / "extraction-status.json").read_text(encoding="utf8")),
    }
    (FULL / "extraction-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"graph_nodes": graph.number_of_nodes(), "graph_edges": graph.number_of_edges(), **{k: status[k] for k in ("semantic_files_staged", "codex_files_with_nodes", "codex_fragment_files")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
