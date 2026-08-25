import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml

from atlas_worker.config import DiscoveryConfig
from atlas_worker.discovery import discover_projects


def write_profile(root: Path, **overrides: object) -> None:
    profile = {
        "id": "nested-project",
        "name": "Nested Project",
        "lifecycle": "active",
        "publication": "public",
        "summary": "Nested project",
        "tags": {
            "domain": ["AI"],
            "problem": ["Routing"],
            "pattern": ["Evaluation"],
            "technology": ["Python"],
            "outcome": ["Tool"],
        },
    }
    profile.update(overrides)
    profile_path = root / "project_memory" / "project-profile.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")


def test_finish_children_are_projects_but_finish_is_not(tmp_path):
    projects = tmp_path / "projects"
    (projects / "alpha").mkdir(parents=True)
    (projects / "finish" / "beta").mkdir(parents=True)
    (projects / "finish" / "gamma").mkdir(parents=True)
    (projects / "finish" / "beta" / "nested").mkdir()
    (projects / "scripts").mkdir()

    report = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert [item.project_id for item in report.projects] == ["alpha", "beta", "gamma"]
    assert [item.lifecycle for item in report.projects] == ["active", "finished", "finished"]
    assert "finish" not in [item.project_id for item in report.projects]
    assert "scripts" not in [item.project_id for item in report.projects]
    assert all(item.publication == "private" for item in report.ambiguous)


def test_finish_child_profile_cannot_override_container_lifecycle(tmp_path):
    beta = tmp_path / "projects" / "finish" / "beta"
    beta.mkdir(parents=True)
    write_profile(beta, id="beta", lifecycle="active", publication="public")

    report = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert report.projects[0].lifecycle == "finished"
    assert report.projects[0].publication == "public"


def test_nested_repository_is_part_of_parent_until_profile_declares_distinct_id(tmp_path):
    alpha = tmp_path / "projects" / "alpha"
    nested = alpha / "nested"
    (nested / ".git").mkdir(parents=True)

    initial = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert [item.project_id for item in initial.projects] == ["alpha"]

    write_profile(nested, id="nested-project", aliases=["projects\\old_nested", "./projects/old_nested"])
    report = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert [item.project_id for item in report.projects] == ["alpha", "nested-project"]
    nested_ref = report.projects[1]
    assert nested_ref.root == nested.resolve()
    assert nested_ref.relative_path == "projects/alpha/nested"
    assert nested_ref.aliases == ("projects/old_nested",)
    assert nested_ref.publication == "public"


def test_unprofiled_directories_are_private_and_ambiguous(tmp_path):
    (tmp_path / "projects" / "alpha").mkdir(parents=True)

    report = discover_projects(DiscoveryConfig.for_workspace(tmp_path))

    assert report.projects[0].publication == "private"
    assert report.ambiguous == report.projects


def test_registered_assets_are_discovered_but_unregistered_files_are_ignored(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    registered = projects / "analysis_notebook.ipynb"
    registered.touch()
    (projects / "ignored_notebook.ipynb").touch()

    config = DiscoveryConfig.for_workspace(tmp_path, registered_assets=(registered,))
    report = discover_projects(config)

    assert [item.project_id for item in report.projects] == ["analysis-notebook"]
    assert report.projects[0].relative_path == "projects/analysis_notebook.ipynb"
    assert report.ambiguous == report.projects


def test_profile_overrides_are_normalized_and_collisions_fail_deterministically(tmp_path):
    alpha = tmp_path / "projects" / "alpha_beta"
    beta = tmp_path / "projects" / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir()
    write_profile(alpha, id="alpha-beta", name="Alpha Beta", aliases=["projects\\old", "./projects/old"])
    write_profile(beta, id="alpha-beta", name="Other")

    with pytest.raises(ValueError, match="Project ID collision: alpha-beta"):
        discover_projects(DiscoveryConfig.for_workspace(tmp_path))


@pytest.mark.parametrize(
    "absolute_alias",
    ["/absolute/local/alias", r"C:\\absolute\\local\\alias", r"\\server\\share\\alias"],
)
def test_profile_rejects_platform_absolute_aliases(tmp_path, absolute_alias):
    alpha = tmp_path / "projects" / "alpha"
    alpha.mkdir(parents=True)
    write_profile(alpha, aliases=[absolute_alias])

    with pytest.raises(ValueError, match="Invalid project alias"):
        discover_projects(DiscoveryConfig.for_workspace(tmp_path))


def test_scan_projects_import_defers_future_cli_import(tmp_path):
    script = Path(__file__).parents[2] / "scripts" / "scan_projects.py"
    module_name = "scan_projects_discovery_test"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        calls: list[list[str]] = []
        cli = types.ModuleType("atlas_worker.cli")
        cli.main = lambda arguments: calls.append(arguments) or 7
        sys.modules["atlas_worker.cli"] = cli

        assert module.main() == 7
        assert calls == [["discover"]]
    finally:
        sys.modules.pop(module_name, None)
        sys.modules.pop("atlas_worker.cli", None)
