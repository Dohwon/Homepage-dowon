#!/usr/bin/env python3
"""Run the allowlisted Project Atlas publication from a local scheduler."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys


PENDING_RAILWAY_DEPLOY = "project-atlas-pending-railway.json"


def resolve_railway_path() -> str | None:
    from_path = shutil.which("railway")
    if from_path:
        return from_path
    nvm_candidates = sorted(
        (Path.home() / ".nvm" / "versions" / "node").glob("*/bin/railway"),
        reverse=True,
    )
    return str(nvm_candidates[0]) if nvm_candidates else None


def deploy_to_railway(
    service_root: Path,
    *,
    railway_path: str | None = None,
    runner=subprocess.run,
) -> None:
    railway = railway_path or resolve_railway_path()
    if not railway:
        raise RuntimeError("Railway CLI is not installed or is not on PATH")
    runner(
        (railway, "up", "--service", "Project Atlas", "--ci"),
        cwd=service_root,
        check=True,
        timeout=1800,
    )


def pending_railway_path(workspace: Path) -> Path:
    return workspace / ".knowledge-worker" / PENDING_RAILWAY_DEPLOY


def write_pending_railway(workspace: Path, bundle_version: str) -> None:
    target = pending_railway_path(workspace)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"bundle_version": bundle_version}, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="ascii",
    )
    temporary.replace(target)


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from atlas_worker.cli import (
        _load_runtime_config,
        _service_root,
        build_parser,
        dispatch,
    )
    from atlas_worker.models import PromotionResult
    from atlas_worker.publish import publish_bundle, run_publication_tests

    workspace = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else repository_root.parent
    discovery_args = build_parser().parse_args(["discover", "--workspace", str(workspace)])
    discovery = dispatch(discovery_args)
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
    pending_deploy = pending_railway_path(workspace)
    railway_deploy_required = publication.committed or pending_deploy.exists()
    railway_deployed = False
    if railway_deploy_required:
        try:
            deploy_to_railway(service_root)
        except Exception:
            write_pending_railway(workspace, str(build["version"]))
            raise
        pending_deploy.unlink(missing_ok=True)
        railway_deployed = True
    result = {
        "build": build,
        "discovery": {
            "ambiguous": discovery["ambiguous"],
            "projects": len(discovery["projects"]),
        },
        "publication": {
            "committed": publication.committed,
            "deferred": publication.deferred,
            "pushed": publication.pushed,
            "staged_paths": list(publication.staged_paths),
        },
        "railway": {
            "deployed": railway_deployed,
            "pending_retry": pending_deploy.exists(),
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
