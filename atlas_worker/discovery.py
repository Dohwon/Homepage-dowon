"""Deterministic discovery of local active and finished projects."""

from __future__ import annotations

import os
import posixpath
from pathlib import Path
import re
import stat
from typing import Any, Iterable

import yaml

from .config import DiscoveryConfig
from .fs_safety import read_confined_text, require_confined_directory
from .models import DiscoveryReport, ProjectRef
from .privacy import PrivacyGate


def discover_projects(
    config: DiscoveryConfig, source_gate: PrivacyGate | None = None
) -> DiscoveryReport:
    """Return known projects without traversing finished-project descendants."""
    candidates = list(_direct_candidates(config, source_gate))
    candidates.extend(_registered_assets(config, source_gate))

    refs: list[tuple[ProjectRef, bool]] = []
    for root, lifecycle, profile, preserve_root, profile_path in candidates:
        ref = _classify_candidate(
            config.workspace_root,
            root,
            lifecycle,
            profile,
            preserve_root=preserve_root,
            profile_path=profile_path,
            standalone_asset=profile_path == standalone_profile_path(root),
        )
        refs.append((ref, profile is None))
        if lifecycle == "active" and not preserve_root and root.is_dir():
            refs.extend(
                _nested_profile_refs(
                    config.workspace_root,
                    root,
                    ref.project_id,
                    source_gate,
                )
            )

    projects = tuple(sorted((ref for ref, _ in refs), key=lambda ref: ref.project_id))
    _require_unique_project_ids(projects)
    ambiguous = tuple(
        sorted(
            (ref for ref, is_unprofiled in refs if is_unprofiled and ref.publication == "private"),
            key=lambda ref: ref.project_id,
        )
    )
    return DiscoveryReport(projects=projects, ambiguous=ambiguous)


def _direct_candidates(
    config: DiscoveryConfig,
    source_gate: PrivacyGate | None,
) -> Iterable[tuple[Path, str, dict[str, Any] | None, bool, Path]]:
    if not config.projects_root.is_dir():
        return ()

    candidates: list[tuple[Path, str, dict[str, Any] | None, bool, Path]] = []
    for root in sorted(config.projects_root.iterdir(), key=_path_sort_key):
        if root.name == "finish" or not _is_eligible_directory(root, config, source_gate):
            continue
        candidates.append(_direct_candidate(root, "active", config, source_gate))

    finish = config.projects_root / "finish"
    if finish.is_dir():
        for root in sorted(finish.iterdir(), key=_path_sort_key):
            if _is_eligible_directory(root, config, source_gate):
                candidates.append(_direct_candidate(root, "finished", config, source_gate))
    return candidates


def _registered_assets(
    config: DiscoveryConfig,
    source_gate: PrivacyGate | None,
) -> Iterable[tuple[Path, str, dict[str, Any] | None, bool, Path]]:
    for asset in config.registered_assets:
        read_confined_text(asset, config.workspace_root, source_gate)
        profile_path = standalone_profile_path(asset)
        try:
            profile_path.lstat()
        except FileNotFoundError:
            profile = None
        else:
            profile = _load_profile(profile_path, config.workspace_root, source_gate)
        yield asset, "active", profile, False, profile_path


def _direct_candidate(
    root: Path,
    lifecycle: str,
    config: DiscoveryConfig,
    source_gate: PrivacyGate | None,
) -> tuple[Path, str, dict[str, Any] | None, bool, Path]:
    profile_path = root / "project_memory" / "project-profile.yaml"
    if root.is_symlink():
        if profile_path.exists() or profile_path.is_symlink():
            raise ValueError("profiled project root cannot be a symlink")
        return Path(os.path.abspath(root)), lifecycle, None, True, profile_path
    return (
        root.resolve(),
        lifecycle,
        _load_optional_profile(root, config.workspace_root, source_gate),
        False,
        profile_path,
    )


def _nested_profile_refs(
    workspace_root: Path,
    parent_root: Path,
    parent_project_id: str,
    source_gate: PrivacyGate | None,
) -> Iterable[tuple[ProjectRef, bool]]:
    profiles = sorted(parent_root.rglob("project_memory/project-profile.yaml"), key=_path_sort_key)
    for profile_path in profiles:
        nested_root = profile_path.parent.parent.resolve()
        if nested_root == parent_root:
            continue
        profile = _load_profile(profile_path, parent_root, source_gate)
        profile_id = _project_id(profile.get("id"), nested_root)
        if profile_id == parent_project_id:
            continue
        yield _classify_candidate(
            workspace_root,
            nested_root,
            "active",
            profile,
            profile_path=profile_path,
        ), False


def _is_eligible_directory(
    root: Path, config: DiscoveryConfig, source_gate: PrivacyGate | None
) -> bool:
    if root.name.startswith(".") or root.name in config.excluded_names:
        return False
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode):
        return root.is_dir()
    if not stat.S_ISDIR(mode):
        return False
    require_confined_directory(root, config.workspace_root, source_gate)
    return True


def _load_optional_profile(
    root: Path, workspace_root: Path, source_gate: PrivacyGate | None
) -> dict[str, Any] | None:
    profile_path = root / "project_memory" / "project-profile.yaml"
    try:
        profile_path.lstat()
    except FileNotFoundError:
        return None
    return _load_profile(profile_path, workspace_root, source_gate)


def _load_profile(
    profile_path: Path, root: Path, source_gate: PrivacyGate | None
) -> dict[str, Any]:
    data = yaml.safe_load(read_confined_text(profile_path, root, source_gate))
    if not isinstance(data, dict):
        raise ValueError(f"Project profile must be a mapping: {profile_path}")
    return data


def _classify_candidate(
    workspace_root: Path,
    root: Path,
    lifecycle: str,
    profile: dict[str, Any] | None,
    *,
    preserve_root: bool = False,
    profile_path: Path | None = None,
    standalone_asset: bool = False,
) -> ProjectRef:
    profile = profile or {}
    root = Path(os.path.abspath(root)) if preserve_root else root.resolve()
    project_id = _project_id(profile.get("id"), root)
    profile_lifecycle = lifecycle if lifecycle == "finished" else profile.get("lifecycle", lifecycle)
    publication = profile.get("publication", "private")
    if profile_lifecycle not in {"active", "finished"}:
        raise ValueError(f"Invalid lifecycle for {root}: {profile_lifecycle}")
    if publication not in {"public", "private", "excluded"}:
        raise ValueError(f"Invalid publication for {root}: {publication}")

    name = profile.get("name", root.stem)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid display name for {root}")
    return ProjectRef(
        project_id=project_id,
        display_name=name.strip(),
        root=root,
        relative_path=_relative_path(workspace_root, root),
        lifecycle=profile_lifecycle,
        publication=publication,
        aliases=_normalized_aliases(profile.get("aliases", ())),
        profile_path=profile_path,
        standalone_asset=standalone_asset,
    )


def standalone_profile_path(asset: Path) -> Path:
    """Return the confined adjacent profile sidecar for a registered asset."""
    return asset.with_name(f"{asset.name}.project-profile.yaml")


def _project_id(value: object, root: Path) -> str:
    source = root.stem if value is None else value
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"Invalid project ID for {root}")
    slug = re.sub(r"[^a-zA-Z0-9가-힣]+", "-", source.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError(f"Invalid project ID for {root}")
    return slug


def _relative_path(workspace_root: Path, root: Path) -> str:
    try:
        return root.relative_to(workspace_root).as_posix()
    except ValueError as error:
        raise ValueError(f"Project is outside workspace: {root}") from error


def _normalized_aliases(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError("Project aliases must be a sequence of strings")
    normalized = {_normalize_alias(item) for item in value}
    return tuple(sorted(normalized))


def _normalize_alias(alias: str) -> str:
    normalized = posixpath.normpath(alias.strip().replace("\\", "/"))
    if (
        not normalized
        or normalized == "."
        or normalized.startswith("/")
        or normalized.startswith("../")
        or re.match(r"^[a-zA-Z]:", normalized)
    ):
        raise ValueError(f"Invalid project alias: {alias}")
    return normalized


def _require_unique_project_ids(projects: tuple[ProjectRef, ...]) -> None:
    seen: dict[str, ProjectRef] = {}
    for project in projects:
        existing = seen.get(project.project_id)
        if existing is not None:
            paths = sorted((existing.relative_path, project.relative_path))
            raise ValueError(f"Project ID collision: {project.project_id} ({paths[0]}, {paths[1]})")
        seen[project.project_id] = project


def _path_sort_key(path: Path) -> tuple[str, str]:
    return path.name.casefold(), path.as_posix()
