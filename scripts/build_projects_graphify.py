#!/usr/bin/env python3
"""Build a private, local Graphify AST graph from projects/ source files."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from graphify.detect import CODE_EXTENSIONS

SITE = Path(__file__).resolve().parent.parent
PROJECTS = SITE.parent / "projects"
OUTPUT = SITE / ".local-graphify"
SKIP_DIRS = {
    ".git", ".worktrees", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "target",
    "site-packages", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".eggs",
    "graphify-out", ".next", ".nuxt", ".turbo", ".angular", ".idea", ".cache", ".parcel-cache",
    ".svelte-kit", ".terraform", ".serverless", ".graphify", ".obsidian", ".smart-env", "coverage",
    "visual-tests", "visual-test", "__snapshots__", "storybook-static", "tmp", "temp", "data", "datasets",
    "downloads", "outputs", "output", "results", "artifacts", "archive", "archives", "backup", "backups",
    "logs", "raw", "public-bundle", "project_memory", "manager_memory", "global_memory", "central_memory",
    ".claude", ".agents", ".codex",
}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
MAX_FILE_BYTES = 4_000_000


def source_files(skipped):
    for base, dirs, names in os.walk(PROJECTS, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.endswith(".egg-info")]
        for name in names:
            source = Path(base) / name
            if source.suffix not in CODE_EXTENSIONS or name in SKIP_FILES:
                continue
            try:
                if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
                    skipped["oversize_or_nonfile"] += 1
                    continue
            except OSError:
                skipped["stat_error"] += 1
                continue
            yield source.relative_to(PROJECTS)


def main():
    if not PROJECTS.is_dir():
        raise SystemExit(f"projects directory missing: {PROJECTS}")
    counts = Counter()
    with tempfile.TemporaryDirectory(prefix="atlas-projects-graphify-") as temporary:
        stage = Path(temporary)
        skipped = Counter()
        for relative in source_files(skipped):
            source = PROJECTS / relative
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            counts[relative.parts[0]] += 1
        print(f"Staged {sum(counts.values())} code files from {len(counts)} top-level folders", flush=True)
        command = ["graphify", "extract", str(stage), "--force", "--code-only", "--max-workers", "2", "--out", str(OUTPUT), "--timing"]
        if shutil.which("prlimit"):
            command = ["prlimit", "--as=2147483648", "--cpu=1800", *command]
        if shutil.which("nice"):
            command = ["nice", "-n", "10", *command]
        environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        subprocess.run(command, check=True, env=environment)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    all_folders = sorted(item.name for item in PROJECTS.iterdir() if item.is_dir())
    manifest = {"code_files_staged": sum(counts.values()), "top_level_folders": {name: counts.get(name, 0) for name in all_folders}, "skipped": dict(skipped), "scope": "Graphify supported code files; excludes generated, dependency, data, and project memory directories"}
    (OUTPUT / "scan-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"Private graph: {OUTPUT / 'graphify-out' / 'graph.json'}")


if __name__ == "__main__":
    main()
