#!/usr/bin/env python3
"""Report reviewed covers and likely image candidates without publishing them."""

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
        "output",
        "results",
        "DATA",
        "data",
    }
)
CANDIDATE_WORDS = re.compile(r"capture|screenshot|screen|preview|demo|캡처|화면", re.IGNORECASE)


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
        candidates = _candidate_paths(ref)
        if cover is not None:
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
                "candidate_count": len(candidates),
                "candidate_examples": candidates[:5],
            }
        )
    return {
        "projects": projects,
        "summary": {
            "projects": len(projects),
            "reviewed_covers": sum(item["status"] == "reviewed-cover" for item in projects),
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
        if CANDIDATE_WORDS.search(relative.as_posix()):
            found.append(relative.as_posix())
    return found


if __name__ == "__main__":
    raise SystemExit(main())
