#!/usr/bin/env python3
"""Create a provenance-preserving Graphify fragment from private PDF OCR pages.

Only literal Japanese vocabulary lines are indexed. OCR is uncertain, so these
nodes are kept separate from reviewed Codex semantic fragments.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / ".local-graphify" / "full"
STAGE = FULL / "source"
OCR = FULL / "ocr"
OUTPUT = FULL / "codex-batches" / "0006.json"
STATUS = FULL / "ocr-index-status.json"
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
TERM = re.compile(r"^[\u3040-\u30ff\u3400-\u9fffー・]+$")


def identity(*parts: str) -> str:
    return "ocr_" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:20]


def term_of(line: str) -> str | None:
    text = unicodedata.normalize("NFKC", line).strip(" ·|.,:;!?()[]{}-ー\t")
    if not text or len(text) > 24 or not JAPANESE.search(text) or not TERM.fullmatch(text):
        return None
    return text


def main() -> None:
    nodes, edges = [], []
    word_files = defaultdict(list)
    file_count = page_count = term_count = 0
    for directory in sorted(OCR.iterdir()):
        status_file = directory / "status.json"
        if not status_file.is_file():
            continue
        status = json.loads(status_file.read_text(encoding="utf8"))
        if not status["complete"]:
            continue
        source = status["source_file"]
        if not (STAGE / source).is_file():
            raise ValueError(f"OCR source missing: {source}")
        file_count += 1
        level = re.search(r"\bN[1-5](?=_|\b)", source)
        label = level.group() if level else Path(source).stem
        file_id = identity(source, "file")
        nodes.append({"id": file_id, "label": f"{label} vocabulary quiz", "file_type": "document",
                      "source_file": source, "source_location": "entire PDF; OCR unreviewed"})
        seen = {}
        for index in range(1, status["pages"] + 1):
            page_file = directory / f"page-{index:04d}.txt"
            if not page_file.is_file():
                raise ValueError(f"OCR page missing: {page_file}")
            page_count += 1
            page_id = identity(source, f"page:{index}")
            location = f"page {index}; OCR unreviewed"
            nodes.append({"id": page_id, "label": f"{label} p{index}", "file_type": "concept",
                          "source_file": source, "source_location": location})
            edges.append({"source": file_id, "target": page_id, "relation": "has_page",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": source, "source_location": location})
            for line in page_file.read_text(encoding="utf8").splitlines():
                term = term_of(line)
                if term is None:
                    continue
                word_id = seen.get(term)
                if word_id is None:
                    word_id = identity(source, term)
                    seen[term] = word_id
                    term_count += 1
                    nodes.append({"id": word_id, "label": term, "file_type": "concept",
                                  "source_file": source, "source_location": location})
                    word_files[term].append((source, word_id))
                edges.append({"source": page_id, "target": word_id, "relation": "contains_ocr_term",
                              "confidence": "AMBIGUOUS", "confidence_score": 0.7,
                              "source_file": source, "source_location": location})
    cross_pdf = 0
    for matches in word_files.values():
        if len(matches) < 2:
            continue
        for first, second in zip(matches, matches[1:]):
            edges.append({"source": first[1], "target": second[1], "relation": "same_ocr_term",
                          "confidence": "AMBIGUOUS", "confidence_score": 0.7,
                          "source_file": first[0], "source_location": "OCR text; review against PDF"})
            cross_pdf += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"nodes": nodes, "edges": edges, "hyperedges": []}, ensure_ascii=False), encoding="utf8")
    STATUS.write_text(json.dumps({"pdf_files": file_count, "pages": page_count, "unique_terms": term_count,
                                  "cross_pdf_exact_terms": cross_pdf, "reviewed": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"pdf_files": file_count, "pages": page_count, "nodes": len(nodes), "edges": len(edges),
                      "cross_pdf_exact_terms": cross_pdf}, ensure_ascii=False))


if __name__ == "__main__":
    main()
