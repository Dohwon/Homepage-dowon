#!/usr/bin/env python3
"""Run the allowlisted Project Atlas publication from a local scheduler."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from atlas_worker.cli import build_parser, dispatch, _load_runtime_config, _service_root
    from atlas_worker.models import PromotionResult
    from atlas_worker.publish import publish_bundle, run_publication_tests

    workspace = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else repository_root.parent
    build_args = build_parser().parse_args(["build", "--workspace", str(workspace)])
    build = dispatch(build_args)
    if not build["validated"]:
        raise RuntimeError("Project Atlas build did not validate")

    service_root = _service_root(workspace, _load_runtime_config(workspace))
    if build["changed"]:
        run_publication_tests(service_root)
    publication = publish_bundle(
        service_root,
        PromotionResult(
            changed=bool(build["changed"]),
            changed_projects=tuple(str(item) for item in build["changed_projects"]),
        ),
        push=True,
    )
    result = {
        "build": build,
        "publication": {
            "committed": publication.committed,
            "deferred": publication.deferred,
            "pushed": publication.pushed,
            "staged_paths": list(publication.staged_paths),
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
