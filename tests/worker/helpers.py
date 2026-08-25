from pathlib import Path

import yaml

from atlas_worker.models import ProjectRef, SessionEvent


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


def make_session_event(
    text: str,
    cwd: str = "/workspace/projects/alpha",
    session_id: str = "s1",
) -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        timestamp="2026-04-01T10:00:00Z",
        cwd=cwd,
        role="user",
        text=text,
        source_path="/local/sessions/s1.jsonl",
        line_number=1,
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
