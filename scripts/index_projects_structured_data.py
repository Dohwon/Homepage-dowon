#!/usr/bin/env python3
"""Read CSV, JSONL and notebooks and emit private Graphify schema relations.

Graphify 0.9.x does not classify these suffixes as semantic documents. This
adapter reads every record, records table shape and links identical distinctive
field names across files. It does not send or publish row values.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_projects_graphify_full import PROJECTS, SITE, SKIP_DIRS

OUTPUT = SITE / ".local-graphify" / "full" / "structured-data.json"
STATUS = SITE / ".local-graphify" / "full" / "structured-data-status.json"
EXTENSIONS = {".csv", ".jsonl", ".ipynb"}
COMMON_FIELDS = {"id", "name", "date", "time", "value", "text", "type", "status", "index", "count", "created_at", "updated_at"}


def node_id(relative: str, concept: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", str(Path(relative).with_suffix("")).lower()).strip("_")
    name = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
    # The hash keeps long paths and non-ASCII names collision resistant.
    return f"data_{stem[:100]}_{name[:45]}_{hashlib.sha256((relative + ':' + concept).encode()).hexdigest()[:10]}"


def project_of(relative: str) -> str:
    parts = relative.split("/")
    return "/".join(parts[:2]) if parts[0] == "finish" and len(parts) > 1 else parts[0]


def encoding_of(file: Path) -> str:
    with file.open("rb") as stream:
        sample = stream.read(65536)
    for encoding in ("utf-8-sig", "cp949"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    return "utf-8"


def read_csv(file: Path) -> tuple[int, list[str], int, list[str]]:
    csv.field_size_limit(16 * 1024 * 1024)
    with file.open("r", encoding=encoding_of(file), errors="replace", newline="") as stream:
        sample = stream.read(4096)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(stream, dialect)
        header = next(reader, [])
        fields = [str(value).strip() for value in header if str(value).strip()]
        rows = 0
        malformed = 0
        for row in reader:
            rows += 1
            if len(row) != len(header):
                malformed += 1
    return rows, fields, malformed, []


def read_jsonl(file: Path) -> tuple[int, list[str], int, list[str]]:
    fields = Counter()
    rows = invalid = 0
    with file.open("r", encoding=encoding_of(file), errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            rows += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if isinstance(item, dict):
                fields.update(str(key) for key in item)
    return rows, sorted(fields), invalid, []


def read_notebook(file: Path) -> tuple[int, list[str], int, list[str]]:
    data = json.loads(file.read_text(encoding="utf-8-sig"))
    cells = data.get("cells", [])
    headings = []
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue
        for line in "".join(cell.get("source", [])).splitlines():
            if re.match(r"^#{1,3}\s+", line):
                headings.append(re.sub(r"^#{1,3}\s+", "", line).strip())
    return len(cells), [], 0, list(dict.fromkeys(headings))[:30]


def sources():
    for base, dirs, names in os.walk(PROJECTS, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in names:
            file = Path(base) / name
            if file.suffix.lower() in EXTENSIONS and file.is_file() and not file.is_symlink():
                yield file


def main() -> None:
    nodes, edges = [], []
    by_field = defaultdict(list)
    failures = {}
    counts = Counter()
    for file in sources():
        relative = file.relative_to(PROJECTS).as_posix()
        try:
            rows, fields, invalid, headings = {".csv": read_csv, ".jsonl": read_jsonl, ".ipynb": read_notebook}[file.suffix.lower()](file)
        except (OSError, ValueError, csv.Error, UnicodeError, json.JSONDecodeError) as error:
            failures[relative] = type(error).__name__
            continue
        counts[file.suffix.lower()] += 1
        if sum(counts.values()) % 100 == 0:
            print(f"Indexed {sum(counts.values())} structured files", flush=True)
        dataset = node_id(relative, "dataset")
        nodes.append({"id": dataset, "label": file.name, "file_type": "document", "source_file": relative,
                      "source_location": f"{rows} {'cells' if file.suffix.lower() == '.ipynb' else 'rows'}; {invalid} invalid records",
                      "data_rows": rows, "data_invalid_rows": invalid, "data_format": file.suffix.lower()})
        for field in dict.fromkeys(fields + headings):
            field_id = node_id(relative, field)
            nodes.append({"id": field_id, "label": field, "file_type": "concept", "source_file": relative,
                          "source_location": "header" if field in fields else "markdown heading"})
            edges.append({"source": dataset, "target": field_id, "relation": "has_field" if field in fields else "contains_section",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": relative,
                          "source_location": "header" if field in fields else "markdown heading", "weight": 1.0})
            if field in fields and field.lower() not in COMMON_FIELDS:
                by_field[field.casefold()].append((relative, field_id))
    cross_edges = 0
    for matches in by_field.values():
        projects = {project_of(relative) for relative, _ in matches}
        if len(projects) < 2 or len(matches) > 12:
            continue
        for index, (relative, field_id) in enumerate(matches):
            other = next(((p, n) for p, n in matches[index + 1:] if project_of(p) != project_of(relative)), None)
            if other is None:
                continue
            edges.append({"source": field_id, "target": other[1], "relation": "shares_field_name",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": relative,
                          "source_location": "header", "weight": 1.0})
            cross_edges += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"nodes": nodes, "edges": edges, "hyperedges": [], "input_tokens": 0, "output_tokens": 0}, ensure_ascii=False), encoding="utf8")
    STATUS.write_text(json.dumps({"files_indexed": dict(counts), "failed_files": failures,
                                  "nodes": len(nodes), "edges": len(edges), "cross_project_field_edges": cross_edges,
                                  "scope": "all records parsed for row counts and field names; row values not semantically analyzed"}, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"indexed": dict(counts), "failed": len(failures), "nodes": len(nodes), "edges": len(edges), "cross_project_field_edges": cross_edges}, ensure_ascii=False))


if __name__ == "__main__":
    main()
