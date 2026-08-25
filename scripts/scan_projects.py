#!/usr/bin/env python3
"""Deprecated compatibility entry point for Project Atlas discovery."""

from pathlib import Path
import sys


def main() -> int:
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from atlas_worker.cli import main as atlas_main

    return atlas_main(["discover"])


if __name__ == "__main__":
    raise SystemExit(main())
