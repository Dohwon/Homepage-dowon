"""Configuration for deterministic local Project Atlas discovery."""

from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXCLUDED = frozenset(
    {
        ".cache",
        ".codex",
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "docs",
        "legacy",
        "llm_wiki",
        "node_modules",
        "scripts",
        "tests",
        "tmp",
    }
)


@dataclass(frozen=True)
class DiscoveryConfig:
    workspace_root: Path
    projects_root: Path
    excluded_names: frozenset[str] = DEFAULT_EXCLUDED
    registered_assets: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        workspace_root = Path(self.workspace_root).resolve()
        projects_root = Path(self.projects_root)
        if not projects_root.is_absolute():
            projects_root = workspace_root / projects_root

        normalized_assets = tuple(
            sorted(
                (_resolve_workspace_path(workspace_root, asset) for asset in self.registered_assets),
                key=lambda path: path.as_posix(),
            )
        )
        object.__setattr__(self, "workspace_root", workspace_root)
        object.__setattr__(self, "projects_root", projects_root.resolve())
        object.__setattr__(self, "excluded_names", frozenset(self.excluded_names))
        object.__setattr__(self, "registered_assets", normalized_assets)

    @classmethod
    def for_workspace(
        cls,
        workspace_root: Path,
        *,
        excluded_names: frozenset[str] = DEFAULT_EXCLUDED,
        registered_assets: tuple[Path, ...] = (),
    ) -> "DiscoveryConfig":
        workspace_root = Path(workspace_root).resolve()
        return cls(
            workspace_root=workspace_root,
            projects_root=workspace_root / "projects",
            excluded_names=excluded_names,
            registered_assets=registered_assets,
        )


def _resolve_workspace_path(workspace_root: Path, path: Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = workspace_root / resolved
    resolved = resolved.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as error:
        raise ValueError(f"Registered asset is outside workspace: {path}") from error
    return resolved
