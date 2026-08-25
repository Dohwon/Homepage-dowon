#!/usr/bin/env python3
"""Repository-local entry point for the Project Atlas worker."""

from pathlib import Path
import sys


def main() -> int:
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    from atlas_worker.cli import main as atlas_main

    return atlas_main()


if __name__ == "__main__":
    raise SystemExit(main())
