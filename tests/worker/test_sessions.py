import json
from collections.abc import Iterator

from atlas_worker.models import SessionEvent
from atlas_worker.sessions import iter_session_events, map_session
from tests.worker.helpers import make_project_ref


def test_iter_session_events_streams_a_large_jsonl_fixture(tmp_path, monkeypatch):
    session_path = tmp_path / "session.jsonl"
    with session_path.open("w", encoding="utf-8") as output:
        for index in range(10_000):
            output.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "timestamp": f"2026-04-01T10:00:{index:02d}Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": f"routine {index}"}],
                        },
                    }
                )
                + "\n"
            )

    monkeypatch.setattr(
        type(session_path),
        "read_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must stream")),
    )
    events = iter_session_events(session_path)

    assert isinstance(events, Iterator)
    assert not isinstance(events, list)
    assert next(events).text == "routine 0"
    assert sum(1 for _ in events) == 9_999


def test_malformed_line_yields_sanitized_parse_error(tmp_path):
    session_path = tmp_path / "session.jsonl"
    raw_line = '{"type": "response_item", "secret": "never retain"'
    session_path.write_text(raw_line + "\n", encoding="utf-8")

    event = next(iter_session_events(session_path))

    assert event.parse_error == "invalid_json"
    assert event.source_path == str(session_path)
    assert event.line_number == 1
    assert event.text == ""
    assert raw_line not in repr(event)


def test_iter_session_events_normalizes_retained_codex_record_shapes(tmp_path):
    session_path = tmp_path / "session.jsonl"
    records = [
        {
            "type": "session_meta",
            "timestamp": "2026-04-01T10:00:00Z",
            "payload": {"id": "s1", "cwd": "/workspace/projects/alpha"},
        },
        {
            "type": "turn_context",
            "timestamp": "2026-04-01T10:01:00Z",
            "payload": {"cwd": "/workspace/projects/alpha"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-04-01T10:02:00Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "수정 완료"}],
            },
        },
        {"type": "telemetry", "payload": {"ignored": True}},
    ]
    session_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    events = tuple(iter_session_events(session_path))

    assert [(event.session_id, event.cwd, event.role, event.text) for event in events] == [
        ("s1", "/workspace/projects/alpha", "system", ""),
        ("s1", "/workspace/projects/alpha", "system", ""),
        ("s1", "/workspace/projects/alpha", "assistant", "수정 완료"),
    ]


def test_session_maps_by_historical_cwd_alias(tmp_path):
    projects = (make_project_ref(tmp_path / "current", project_id="tmap-clone"),)
    aliases = {"/old/codex/projects/260329_tmap_clone": "tmap-clone"}
    event = SessionEvent(
        session_id="s1",
        timestamp="2026-04-01T10:00:00Z",
        cwd="/old/codex/projects/260329_tmap_clone",
        role="user",
        text="두 시안 중 첫 번째로 롤백해",
    )

    assert map_session(event, projects, aliases) == "tmap-clone"


def test_session_mapping_uses_longest_component_aware_path(tmp_path):
    projects = (
        make_project_ref(tmp_path / "projects", project_id="parent"),
        make_project_ref(tmp_path / "projects" / "atlas", project_id="atlas"),
    )
    event = SessionEvent(
        session_id="s1",
        timestamp="2026-04-01T10:00:00Z",
        cwd=str(tmp_path / "projects" / "atlas" / "atlas_worker"),
        role="user",
        text="결정",
    )

    assert map_session(event, projects, {}) == "atlas"


def test_session_mapping_does_not_match_path_substrings(tmp_path):
    projects = (make_project_ref(tmp_path / "project", project_id="project"),)
    event = SessionEvent(
        session_id="s1",
        timestamp="2026-04-01T10:00:00Z",
        cwd=str(tmp_path / "project-copy"),
        role="user",
        text="결정",
    )

    assert map_session(event, projects, {}) is None
