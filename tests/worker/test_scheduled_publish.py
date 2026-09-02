from pathlib import Path

from scripts.project_atlas_scheduled_publish import (
    deploy_to_railway,
    pending_railway_path,
    write_pending_railway,
)


def test_scheduled_publisher_uses_project_atlas_railway_service(tmp_path: Path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))

    deploy_to_railway(tmp_path, railway_path="/usr/bin/railway", runner=runner)

    assert calls == [
        (
            ("/usr/bin/railway", "up", "--service", "Project Atlas", "--ci"),
            {"cwd": tmp_path, "check": True, "timeout": 1800},
        )
    ]


def test_pending_railway_marker_is_written_under_worker_state(tmp_path: Path):
    write_pending_railway(tmp_path, "bundle-version")

    marker = pending_railway_path(tmp_path)
    assert marker.read_text(encoding="ascii") == '{"bundle_version": "bundle-version"}\n'
