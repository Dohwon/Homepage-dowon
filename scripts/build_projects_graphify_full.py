#!/usr/bin/env python3
"""Stage Graphify-supported project inputs and run its complete extractor locally."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from graphify.detect import (
    CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS,
    IMAGE_EXTENSIONS, OFFICE_EXTENSIONS, VIDEO_EXTENSIONS, _is_noise_dir,
)

SITE = Path(__file__).resolve().parent.parent
PROJECTS = SITE.parent / "projects"
STAGE = SITE / ".local-graphify" / "full" / "source"
KINDS = {
    "code": CODE_EXTENSIONS,
    "document": DOC_EXTENSIONS,
    "paper": PAPER_EXTENSIONS,
    "office": OFFICE_EXTENSIONS,
    "image": IMAGE_EXTENSIONS,
    "video": VIDEO_EXTENSIONS,
}
CAPS = {
    "code": 4_000_000,
    "document": 4_000_000,
    "paper": 25_000_000,
    "office": 25_000_000,
    "image": 8_000_000,
    "video": 50_000_000,
}
# Keep project outputs, data, memories and finished-project folders in scope.
# Only omit dependency trees, generated Graphify state and agent runtime files.
SKIP_DIRS = {
    ".git", ".worktrees", "node_modules", "graphify-out", ".local-graphify",
    ".claude", ".agents", ".codex", ".knowledge-worker", ".atlas-staging",
    ".atlas-test-data", "__pycache__", ".pytest_cache", ".venv", "venv",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "poetry.lock",
}


def source_files():
    counts = Counter()
    skipped = Counter()
    for base, dirs, names in os.walk(PROJECTS, followlinks=False):
        parent = Path(base)
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not _is_noise_dir(name, parent)]
        for name in names:
            source = parent / name
            if name in SKIP_FILES or source.is_symlink():
                continue
            kind = next((key for key, extensions in KINDS.items() if source.suffix.lower() in extensions), None)
            if kind is None:
                continue
            try:
                size = source.stat().st_size
            except OSError:
                skipped["stat_error"] += 1
                continue
            if size > CAPS[kind]:
                skipped[f"oversize_{kind}"] += 1
                continue
            counts[kind] += 1
            yield source, kind, counts, skipped


def main():
    if not PROJECTS.is_dir():
        raise SystemExit(f"projects directory missing: {PROJECTS}")
    STAGE.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    skipped = Counter()
    staged = []
    converted_source_map = {}
    for source, kind, counts, skipped in source_files():
        relative = source.relative_to(PROJECTS)
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or (target.stat().st_size, target.stat().st_mtime_ns) != (source.stat().st_size, source.stat().st_mtime_ns):
            shutil.copy2(source, target)
        staged.append(relative.as_posix())
        if kind == "office":
            # Graphify names converted Office sidecars with this relative-path hash.
            # Retain the original project so their concept nodes stay navigable.
            digest = hashlib.sha256(relative.as_posix().encode()).hexdigest()[:8]
            converted_source_map[f"graphify-out/converted/{source.stem}_{digest}.md"] = relative.as_posix()
    manifest = {
        "source_root": "projects/",
        "mode": "full",
        "staged_files": dict(counts),
        "staged_paths": staged,
        "skipped_files": dict(skipped),
        "excluded_directories": sorted(SKIP_DIRS),
        "size_caps_bytes": CAPS,
        "converted_source_map": converted_source_map,
        "top_level_folders": sorted(item.name for item in PROJECTS.iterdir() if item.is_dir()),
    }
    (STAGE.parent / "scan-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"Staged {len(staged)} Graphify-supported files: {dict(counts)}", flush=True)
    backend = next((arg.partition("=")[2] for arg in sys.argv[1:] if arg.startswith("--backend=")), None)
    if "--stage-only" in sys.argv[1:] or backend is None:
        if backend is None and "--stage-only" not in sys.argv[1:]:
            print("Corpus staged. Use the Codex Graphify skill for semantic extraction; headless extraction requires explicit --backend=NAME.")
        return
    if backend == "codex":
        raise SystemExit("Codex is a Graphify agent skill, not a headless --backend value")
    command = [
        "graphify", "extract", str(STAGE), "--backend", backend,
        "--max-workers", "2", "--max-concurrency", "1",
        "--token-budget", "60000", "--timing",
    ]
    if shutil.which("prlimit"):
        command = ["prlimit", "--as=2147483648", "--cpu=1800", *command]
    if shutil.which("nice"):
        command = ["nice", "-n", "10", *command]
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "GRAPHIFY_CLAUDE_CLI_MODEL": os.environ.get("GRAPHIFY_CLAUDE_CLI_MODEL", "sonnet")}
    subprocess.run(command, env=environment, check=True)
    print(f"Full graph: {STAGE / 'graphify-out' / 'graph.json'}")


if __name__ == "__main__":
    main()
