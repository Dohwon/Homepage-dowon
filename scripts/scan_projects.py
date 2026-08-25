#!/usr/bin/env python3
"""Deprecated compatibility entry point for Project Atlas discovery."""

from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    from atlas_worker.cli import main as atlas_main

    return atlas_main(
        ["discover", "--workspace", str(_workspace_root(project_root))]
    )


def _workspace_root(project_root: Path) -> Path:
    if project_root.parent.name == ".worktrees":
        return project_root.parent.parent.parent
    return project_root.parent


if __name__ == "__main__":
    raise SystemExit(main())
