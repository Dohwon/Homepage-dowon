#!/usr/bin/env python3
"""Resume private, source-grounded Graphify document extraction with Codex CLI.

Each successful batch is validated before it is added to codex-batches/. The
runner never publishes source content. Run with --max-batches 0 to drain the
plain-text document queue; other formats retain their separate coverage gates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / ".local-graphify" / "full"
STAGE = FULL / "source"
FRAGMENTS = FULL / "codex-batches"
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


def completed_paths() -> set[str]:
    done = set()
    for path in FRAGMENTS.glob("*.meta.json"):
        meta = json.loads(path.read_text(encoding="utf8"))
        if (FRAGMENTS / (path.name.removesuffix(".meta.json") + ".json")).is_file():
            done.update(meta.get("source_paths", []))
    for path in FRAGMENTS.glob("[0-9][0-9][0-9][0-9].json"):
        if path.stem in {"0006", "0008"}:
            continue
        fragment = json.loads(path.read_text(encoding="utf8"))
        for node in fragment.get("nodes", []):
            source = Path(node.get("source_file", ""))
            if source.is_relative_to(STAGE):
                done.add(source.relative_to(STAGE).as_posix())
    return done


def queue() -> list[tuple[str, Path]]:
    manifest = json.loads((FULL / "scan-manifest.json").read_text(encoding="utf8"))
    done = completed_paths()
    selected = []
    for relative in manifest["staged_paths"]:
        path = STAGE / relative
        if relative in done or path.suffix.lower() not in TEXT_EXTENSIONS or not path.is_file():
            continue
        if path.stat().st_size > 48_000:
            continue  # A later chunked pass must read larger files, not silently truncate them.
        selected.append((relative, path))
    return selected


def validate(fragment: dict, paths: set[str]) -> None:
    if not isinstance(fragment, dict) or any(not isinstance(fragment.get(k), list) for k in ("nodes", "edges", "hyperedges")):
        raise ValueError("Codex output is not a Graphify fragment")
    if fragment.get("error") or not fragment["nodes"]:
        raise ValueError(f"Codex returned no grounded concepts: {fragment.get('error', 'empty output')}")
    ids = set()
    for node in fragment["nodes"]:
        if not re.fullmatch(r"[a-z0-9_]+", str(node.get("id", ""))) or not node.get("label"):
            raise ValueError("invalid node identity")
        if node.get("source_file") not in paths:
            raise ValueError("node source not in this batch")
        ids.add(node["id"])
    for edge in fragment["edges"]:
        if edge.get("source") not in ids or edge.get("target") not in ids:
            raise ValueError("edge endpoint missing in batch")
        if edge.get("source_file") not in paths or edge.get("confidence") not in CONFIDENCE:
            raise ValueError("invalid edge provenance or confidence")
        score = edge.get("confidence_score")
        if not isinstance(score, (float, int)) or not 0 <= score <= 1:
            raise ValueError("invalid edge score")
    for hyperedge in fragment["hyperedges"]:
        if hyperedge.get("source_file") not in paths or not set(hyperedge.get("nodes", [])) <= ids:
            raise ValueError("invalid hyperedge")


def normalize_ids(fragment: dict) -> None:
    """Accept Codex's path/entity separator while retaining Graphify IDs."""
    replacements = {}
    for node in fragment.get("nodes", []):
        old = node.get("id")
        if isinstance(old, str) and re.fullmatch(r"[a-z0-9_]+/[a-z0-9_]+", old):
            replacements[old] = old.replace("/", "_")
            node["id"] = replacements[old]
    for edge in fragment.get("edges", []):
        edge["source"] = replacements.get(edge.get("source"), edge.get("source"))
        edge["target"] = replacements.get(edge.get("target"), edge.get("target"))
    for hyperedge in fragment.get("hyperedges", []):
        hyperedge["nodes"] = [replacements.get(node, node) for node in hyperedge.get("nodes", [])]


def limited() -> None:
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS, (2_147_483_648, 2_147_483_648))
    resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))


def run_batch(items: list[tuple[str, Path]], number: int) -> None:
    FRAGMENTS.mkdir(parents=True, exist_ok=True)
    target = FRAGMENTS / f"{number:04d}.json"
    if target.exists():
        raise FileExistsError(target)
    with tempfile.TemporaryDirectory(prefix="atlas-codex-graphify-") as work:
        result = Path(work) / "result.json"
        paths = [str(path) for _, path in items]
        sources = "\n\n".join(
            f"<source path={json.dumps(str(path), ensure_ascii=False)}>\n"
            f"{path.read_text(encoding='utf8', errors='replace')}\n</source>"
            for _, path in items
        )
        prompt = (
            "You are a Graphify extraction agent. All source text is supplied below; do not call tools. "
            "Return ONLY a JSON object with nodes, edges, hyperedges. "
            "Extract named concepts and explicit relationships, including decision rationale. "
            "Add cross-file semantically_similar_to edges only when specific source text supports them. "
            "Use EXTRACTED for explicit claims, INFERRED for clear interpretation, AMBIGUOUS for uncertainty. "
            "Every node needs id (lowercase path-based snake_case), label, file_type=document, "
            "source_file (verbatim absolute path from list), source_location (section or line), and rationale when relevant. "
            "Every edge needs source, target, relation, confidence, confidence_score, source_file, source_location, weight. "
            "All edge endpoints must be nodes in this output. Return empty arrays when no grounded concepts exist. "
            "Do not include private values, secrets, personal names, or raw excerpts as labels. Sources:\n"
            + sources
        )
        env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        command = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                   "--disable", "code_mode_host",
                   "-C", work, "-s", "read-only", "-o", str(result), prompt]
        log = Path(work) / "codex.log"
        with log.open("w", encoding="utf8") as stream:
            process = subprocess.run(command, env=env, text=True, stdout=stream, stderr=subprocess.STDOUT,
                                     timeout=600, preexec_fn=limited)
        diagnostic = log.read_text(encoding="utf8", errors="replace")[-1200:]
        if process.returncode:
            raise RuntimeError(f"Codex batch {number} failed: {diagnostic}")
        if not result.is_file():
            raise RuntimeError(f"Codex batch {number} produced no result: {diagnostic}")
        fragment = json.loads(result.read_text(encoding="utf8"))
        normalize_ids(fragment)
        try:
            validate(fragment, set(paths))
        except ValueError:
            (FRAGMENTS / f"{number:04d}.failed.json").write_text(
                json.dumps(fragment, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
            raise
        target.write_text(json.dumps(fragment, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        meta = {"source_paths": [relative for relative, _ in items], "nodes": len(fragment["nodes"]),
                "edges": len(fragment["edges"]), "tokens_log": diagnostic[-500:]}
        (FRAGMENTS / f"{number:04d}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(json.dumps({"batch": number, "files": len(items), "nodes": len(fragment["nodes"]),
                          "edges": len(fragment["edges"])}, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-batches", type=int, default=1, help="0 drains queue")
    parser.add_argument("--batch-files", type=int, default=6)
    args = parser.parse_args()
    pending = queue()
    print(f"Eligible plain-text documents pending: {len(pending)}", flush=True)
    number = max((int(path.stem) for path in FRAGMENTS.glob("[0-9][0-9][0-9][0-9].json")), default=0) + 1
    count = 0
    while pending and (args.max_batches == 0 or count < args.max_batches):
        available = int(Path("/proc/meminfo").read_text().split("MemAvailable:")[1].split()[0])
        if available < 2_000_000:
            raise RuntimeError("MemAvailable below 2 GiB; stopping before next batch")
        batch = []
        size = 0
        while pending and len(batch) < args.batch_files:
            item = pending[0]
            bytes_now = item[1].stat().st_size
            if batch and size + bytes_now > 64_000:
                break
            batch.append(pending.pop(0))
            size += bytes_now
        run_batch(batch, number)
        number += 1
        count += 1


if __name__ == "__main__":
    main()
