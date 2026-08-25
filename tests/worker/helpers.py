import hashlib
import json
from pathlib import Path

import yaml

from atlas_worker.manifest import content_version, project_hashes_from_files
from atlas_worker.models import (
    EvidenceClaim,
    ProjectEvent,
    ProjectKnowledge,
    ProjectRef,
    PublicProject,
    SessionEvent,
    TagSet,
)


def make_project_ref(
    root: Path,
    project_id: str = "alpha",
    lifecycle: str = "active",
    publication: str = "public",
) -> ProjectRef:
    return ProjectRef(
        project_id=project_id,
        display_name=project_id.replace("-", " ").title(),
        root=root,
        relative_path=f"projects/{project_id}",
        lifecycle=lifecycle,
        publication=publication,
        aliases=(),
    )


def make_public_project(project_id: str) -> PublicProject:
    return PublicProject(
        project_id=project_id,
        display_name=project_id.replace("-", " ").title(),
        lifecycle="active",
        summary=f"{project_id} public project",
        tags=TagSet(
            domain=("AI",),
            problem=("Routing",),
            pattern=("Evaluation",),
            technology=("Python",),
            outcome=("Tool",),
        ),
    )


def make_session_event(
    text: str,
    cwd: str = "/workspace/projects/alpha",
    session_id: str = "s1",
    role: str = "user",
    source_path: str = "/local/sessions/s1.jsonl",
    line_number: int = 1,
) -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        timestamp="2026-04-01T10:00:00Z",
        cwd=cwd,
        role=role,
        text=text,
        source_path=source_path,
        line_number=line_number,
    )


def write_project_profile(root: Path, **overrides: object) -> Path:
    profile = {
        "id": "alpha",
        "name": "Alpha",
        "lifecycle": "active",
        "publication": "public",
        "summary": "Alpha project",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
        },
    }
    profile.update(overrides)
    path = root / "project_memory" / "project-profile.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return path


def write_memory_markdown(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_decision_knowledge(
    *,
    value: str = "Use typed contracts for project memory",
    evidence_id: str = "decision-001",
    confidence: float = 0.90,
    selected: bool = False,
) -> ProjectKnowledge:
    claim = EvidenceClaim(
        field="history",
        value=value,
        source_class="source",
        confidence=confidence,
        evidence_id=evidence_id,
        claim_type="decision",
        event_date="2026-08-24",
        selected=selected,
    )
    return ProjectKnowledge(values={"history": value}, winners={"history": claim})


def make_challenge_events() -> tuple[ProjectEvent, ...]:
    return (
        ProjectEvent("constraint-001", "2026-08-20", "Constraint", "Private data stays local", "Limit inputs", "Boundary set", "constraint"),
        ProjectEvent("attempt-001", "2026-08-21", "Attempt", "Need reusable evidence", "Add typed claims", "Claims merged", "attempt"),
        ProjectEvent("revision-001", "2026-08-22", "Revision", "Review rejected broad extraction", "Select high-confidence facts", "Scope narrowed", "revision"),
        ProjectEvent("decision-001", "2026-08-23", "Decision", "Memory needs stable updates", "Use managed blocks", "Reruns are idempotent", "decision"),
        ProjectEvent("result-001", "2026-08-24", "Result", "Evidence is curated", "Render the map", "Story is readable", "result"),
    )


def write_bundle_fixture(
    root: Path,
    version: str | None,
    summary: str,
    project_ids: tuple[str, ...] = ("alpha",),
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for project_id in sorted(project_ids):
        project_dir = root / "projects" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        project = make_public_project(project_id).to_dict()
        project["summary"] = summary
        _write_fixture_json(project_dir / "project.json", project)

    _write_fixture_json(
        root / "graph" / "nodes.json",
        [
            {"id": f"project:{project_id}", "kind": "project", "label": project_id.title()}
            for project_id in sorted(project_ids)
        ],
    )
    _write_fixture_json(root / "graph" / "edges.json", [])
    _write_fixture_json(root / "topics.json", [])
    _write_fixture_json(root / "changelog.json", [])
    _write_fixture_json(
        root / "search-index.json",
        [
            {
                "body": summary,
                "id": f"project:{project_id}",
                "project_id": project_id,
                "title": project_id.title(),
                "url": f"/projects/{project_id}",
            }
            for project_id in sorted(project_ids)
        ],
    )
    refresh_fixture_manifest(root, version=version, project_ids=project_ids)


def refresh_fixture_manifest(root: Path, version: str | None, project_ids: tuple[str, ...]) -> None:
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "manifest.json"
    }
    ordered_projects = tuple(sorted(project_ids))
    derived_version = content_version(
        files,
        project_hashes_from_files(ordered_projects, files),
    )
    _write_fixture_json(
        root / "manifest.json",
        {
            "files": files,
            "projects": list(ordered_projects),
            "version": version if version is not None else derived_version,
        },
    )


def _write_fixture_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
