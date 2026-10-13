#!/usr/bin/env python3
"""Run Graphify's full AST and semantic passes on every project's key sources.

The unabridged corpus is prepared by build_projects_graphify_full.py. This
bounded run gives each project document coverage while that much larger run
remains available for systems with enough LLM capacity.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from build_projects_graphify_full import PROJECTS, SITE, source_files

STAGE = SITE / ".local-graphify" / "priority" / "source"


def project_id(relative: Path) -> str:
    parts = relative.parts
    return "/".join(parts[:2]) if parts[0] in {"finish", "legacy"} and len(parts) > 2 else parts[0]


def score_doc(relative: Path) -> tuple:
    path = relative.as_posix().lower()
    name = relative.name.lower()
    priority = (
        0 if "project-atlas/article" in path else
        1 if name.startswith("readme") else
        2 if "project_memory" in path else
        3 if any(term in path for term in ("spec", "architecture", "기획", "설계", "overview")) else
        4
    )
    return priority, len(relative.parts), len(path), path


def main() -> None:
    discovered = defaultdict(lambda: defaultdict(list))
    for source, kind, *_ in source_files():
        relative = source.relative_to(PROJECTS)
        discovered[project_id(relative)][kind].append((relative, source))
    chosen = []
    for project, kinds in sorted(discovered.items()):
        chosen.extend(kinds["code"])
        chosen.extend(kinds["paper"])
        chosen.extend(kinds["video"])
        chosen.extend(sorted(kinds["document"], key=lambda pair: score_doc(pair[0]))[:3])
        chosen.extend(sorted(kinds["office"], key=lambda pair: score_doc(pair[0]))[:1])
        chosen.extend(sorted(kinds["image"], key=lambda pair: score_doc(pair[0]))[:1])
    counts = Counter()
    mapping = {}
    STAGE.mkdir(parents=True, exist_ok=True)
    for relative, source in chosen:
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or (target.stat().st_size, target.stat().st_mtime_ns) != (source.stat().st_size, source.stat().st_mtime_ns):
            shutil.copy2(source, target)
        kind = next(kind for kind, pairs in discovered[project_id(relative)].items() if (relative, source) in pairs)
        counts[kind] += 1
        if kind == "office":
            digest = hashlib.sha256(relative.as_posix().encode()).hexdigest()[:8]
            mapping[f"graphify-out/converted/{source.stem}_{digest}.md"] = relative.as_posix()
    (STAGE.parent / "scan-manifest.json").write_text(json.dumps({
        "source_root": "projects/", "mode": "priority", "staged_files": dict(counts),
        "staged_paths": [relative.as_posix() for relative, _ in chosen],
        "project_groups": len(discovered), "converted_source_map": mapping,
        "selection": "all supported code/PDF/media; up to 3 documents, 1 Office file and 1 image per project",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"Graphify priority corpus: {sum(counts.values())} files, {len(discovered)} project groups, {dict(counts)}", flush=True)
    backend = next((arg.partition("=")[2] for arg in os.sys.argv[1:] if arg.startswith("--backend=")), None)
    if "--stage-only" in os.sys.argv[1:] or backend is None:
        if backend is None and "--stage-only" not in os.sys.argv[1:]:
            print("Corpus staged. Use the Codex Graphify skill for semantic extraction; headless extraction requires explicit --backend=NAME.")
        return
    if backend == "codex":
        raise SystemExit("Codex is a Graphify agent skill, not a headless --backend value")
    command = ["graphify", "extract", str(STAGE), "--backend", backend,
               "--max-workers", "2", "--max-concurrency", "1", "--token-budget", "60000", "--timing"]
    if shutil.which("prlimit"):
        command = ["prlimit", "--as=2147483648", "--cpu=1800", *command]
    if shutil.which("nice"):
        command = ["nice", "-n", "10", *command]
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
           "GRAPHIFY_CLAUDE_CLI_MODEL": os.environ.get("GRAPHIFY_CLAUDE_CLI_MODEL", "sonnet")}
    status = {"total_chunks": 0, "succeeded_chunks": 0, "failed_chunks": 0}
    with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
        for line in process.stdout:
            print(line, end="", flush=True)
            match = re.search(r"chunk (\d+)/(\d+) (done|failed)", line)
            if match:
                status["total_chunks"] = int(match.group(2))
                status["succeeded_chunks" if match.group(3) == "done" else "failed_chunks"] += 1
        result = process.wait()
    status["complete"] = result == 0 and status["failed_chunks"] == 0 and (status["total_chunks"] == 0 or status["succeeded_chunks"] == status["total_chunks"])
    (STAGE.parent / "extraction-status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf8")
    if result:
        raise subprocess.CalledProcessError(result, command)
    print(f"Graphify graph: {STAGE / 'graphify-out' / 'graph.json'}")


if __name__ == "__main__":
    main()
