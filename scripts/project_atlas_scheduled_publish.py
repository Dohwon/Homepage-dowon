#!/usr/bin/env python3
"""Run the allowlisted Project Atlas publication from a local scheduler."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from atlas_worker.cli import ConfigError, build_parser, dispatch

    workspace = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else repository_root.parent
    args = build_parser().parse_args(
        [
            "publish",
            "--workspace",
            str(workspace),
            "--changed-only",
            "--push",
        ]
    )
    for attempt in range(3):
        try:
            result = dispatch(args)
            break
        except ConfigError as error:
            if error.pointer != "/catalog-audit" or attempt == 2:
                raise
            time.sleep(10)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
