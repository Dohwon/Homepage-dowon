#!/usr/bin/env python3
"""Audit implementation-screen evidence without publishing unreviewed assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas_worker.cli import _discover, _load_runtime_config
from atlas_worker.models import ProjectRef


IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "results",
        "DATA",
        "data",
    }
)
CANDIDATE_WORDS = re.compile(r"capture|screenshot|screen|preview|demo|캡처|화면", re.IGNORECASE)
REFERENCE_PARTS = frozenset({"ref", "reference", "design-ref", "branding", "resource", "resources", "REFERENCE"})
DEPLOYMENT_NAMES = frozenset({"railway.json", "railway.toml"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT.parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    report = build_report(workspace)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


def build_report(workspace: Path) -> dict[str, object]:
    discovery = _discover(workspace, _load_runtime_config(workspace))
    projects = []
    for ref in discovery.projects:
        cover = next(
            (
                ref.root / "project_memory" / "project-atlas" / f"cover{suffix}"
                for suffix in IMAGE_SUFFIXES
                if (ref.root / "project_memory" / "project-atlas" / f"cover{suffix}").is_file()
            ),
            None,
        )
        manifest = ref.root / "project_memory" / "project-atlas" / "captures.yaml"
        registered = _registered_capture_ids(manifest)
        candidates = _candidate_paths(ref)
        deployment_files = _deployment_files(ref)
        if registered:
            status = "reviewed-captures"
        elif cover is not None:
            status = "reviewed-cover"
        elif candidates:
            status = "candidate-needs-review"
        else:
            status = "no-candidate-found"
        projects.append(
            {
                "id": ref.project_id,
                "name": ref.display_name,
                "publication": ref.publication,
                "status": status,
                "registered_capture_count": len(registered),
                "registered_capture_ids": registered,
                "legacy_cover": cover.relative_to(ref.root).as_posix() if cover else None,
                "deployment_evidence": deployment_files,
                "candidate_count": len(candidates),
                "candidate_examples": candidates[:5],
            }
        )
    return {
        "projects": projects,
        "summary": {
            "projects": len(projects),
            "reviewed_covers": sum(item["status"] == "reviewed-cover" for item in projects),
            "reviewed_capture_manifests": sum(item["status"] == "reviewed-captures" for item in projects),
            "candidate_needs_review": sum(
                item["status"] == "candidate-needs-review" for item in projects
            ),
            "no_candidate_found": sum(
                item["status"] == "no-candidate-found" for item in projects
            ),
        },
    }


def _candidate_paths(ref: ProjectRef) -> list[str]:
    if not ref.root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(ref.root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_SUFFIXES:
            continue
        relative = path.relative_to(ref.root)
        if any(part in SKIPPED_DIRECTORIES for part in relative.parts):
            continue
        if relative.parts[:2] == ("project_memory", "project-atlas"):
            continue
        if CANDIDATE_WORDS.search(relative.as_posix()) or _looks_like_product_screen(relative):
            found.append(relative.as_posix())
    return found


def _registered_capture_ids(manifest: Path) -> list[str]:
    if not manifest.is_file():
        return []
    try:
        import yaml

        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return []
    captures = raw.get("captures") if isinstance(raw, dict) else None
    if not isinstance(captures, list):
        return []
    return [item["id"] for item in captures if isinstance(item, dict) and isinstance(item.get("id"), str)]


def _looks_like_product_screen(relative: Path) -> bool:
    parts = {part.casefold() for part in relative.parts[:-1]}
    if parts & {"reference", "design-ref", "branding", "resource", "resources"}:
        return False
    return bool(parts & {"reports", "screens", "screen", "captures", "output", "outputs", "public"})


def _deployment_files(ref: ProjectRef) -> list[str]:
    found = []
    for path in sorted(ref.root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name not in DEPLOYMENT_NAMES:
            continue
        if any(part in SKIPPED_DIRECTORIES for part in path.relative_to(ref.root).parts):
            continue
        found.append(path.relative_to(ref.root).as_posix())
    return found


if __name__ == "__main__":
    raise SystemExit(main())
