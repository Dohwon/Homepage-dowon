import importlib.util
import json
import subprocess
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


def test_registered_asset_uses_only_its_confined_adjacent_sidecar_profile(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    registered = projects / "analysis_notebook.ipynb"
    registered.write_text("{}\n", encoding="utf-8")
    sidecar = projects / "analysis_notebook.ipynb.project-profile.yaml"
    sidecar.write_text(
        yaml.safe_dump(
            {
                "id": "analysis-notebook",
                "name": "Analysis Notebook",
                "lifecycle": "active",
                "publication": "public",
                "summary": "Registered analysis",
                "tags": {
                    "domain": ["AI"],
                    "problem": ["Routing"],
                    "pattern": ["Evaluation"],
                    "technology": ["Python"],
                    "outcome": ["Tool"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    unregistered = projects / "ignored.ipynb"
    unregistered.write_text("{}\n", encoding="utf-8")
    (projects / "ignored.ipynb.project-profile.yaml").write_text(
        sidecar.read_text(encoding="utf-8"), encoding="utf-8"
    )

    report = discover_projects(
        DiscoveryConfig.for_workspace(tmp_path, registered_assets=(registered,))
    )

    assert [ref.project_id for ref in report.projects] == ["analysis-notebook"]
    assert report.projects[0].publication == "public"
    assert report.projects[0].root == registered
    assert report.projects[0].profile_path == sidecar
    assert report.projects[0].standalone_asset
    assert report.ambiguous == ()


@pytest.mark.parametrize("link_kind", ("asset", "sidecar"))
def test_registered_asset_and_sidecar_preserve_symlinks_for_secure_preflight(
    tmp_path, link_kind
):
    projects = tmp_path / "projects"
    projects.mkdir()
    target = projects / "target.ipynb"
    target.write_text("{}\n", encoding="utf-8")
    asset = projects / "linked.ipynb"
    if link_kind == "asset":
        asset.symlink_to(target)
    else:
        asset.write_text("{}\n", encoding="utf-8")
        sidecar_target = projects / "target-profile.yaml"
        sidecar_target.write_text("{}\n", encoding="utf-8")
        (projects / "linked.ipynb.project-profile.yaml").symlink_to(sidecar_target)

    config = DiscoveryConfig.for_workspace(tmp_path, registered_assets=(asset,))

    with pytest.raises(ValueError, match="symlink"):
        discover_projects(config)


def test_registered_asset_configuration_rejects_lexical_workspace_escape(tmp_path):
    outside = tmp_path.parent / "outside.ipynb"

    with pytest.raises(ValueError, match="outside workspace"):
        DiscoveryConfig.for_workspace(tmp_path, registered_assets=(outside,))


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
        assert module._workspace_root(
            Path("/workspace/codex/portfolio-homepage")
        ) == Path("/workspace/codex")
        assert module._workspace_root(
            Path("/workspace/codex/portfolio-homepage/.worktrees/project-atlas")
        ) == Path("/workspace/codex")
        expected_workspace = module._workspace_root(script.parents[1])
        assert calls == [["discover", "--workspace", str(expected_workspace)]]
    finally:
        sys.modules.pop(module_name, None)
        sys.modules.pop("atlas_worker.cli", None)


def test_scan_projects_subprocess_passes_workspace_when_started_from_service_root(
    tmp_path,
):
    source = Path(__file__).parents[2] / "scripts" / "scan_projects.py"
    workspace = tmp_path / "codex"
    service = workspace / "portfolio-homepage"
    script = service / "scripts" / "scan_projects.py"
    script.parent.mkdir(parents=True)
    script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    package = service / "atlas_worker"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import json\n"
        "def main(arguments):\n"
        "    print(json.dumps(arguments))\n"
        "    return 0\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=service,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == [
        "discover",
        "--workspace",
        str(workspace),
    ]
