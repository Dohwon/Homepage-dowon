import os
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

import pytest

import atlas_worker.privacy as privacy_module
from atlas_worker.privacy import (
    PrivacyGate,
    PrivacyViolation,
    _contains_denied_source_part,
    hmac_alias,
)


def test_public_bundle_rejects_local_paths_and_secrets():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": "read /home/dowon/private", "token": "sk-test-secret-value"})

    assert {finding.category for finding in report.findings} == {"absolute_path", "secret"}


@pytest.mark.parametrize(
    "local_path",
    (
        "/",
        "/tmp/atlas-private",
        "/root/atlas-private",
        "/Users/private/atlas",
        "root:/home/dowon/private",
        r"D:\atlas\private",
        "E:/atlas/private",
        r"\\server\share\atlas",
        "//server/share/atlas",
    ),
)
def test_absolute_local_path_families_are_blocked_without_value_leak(local_path):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": local_path})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": local_path})
    assert "absolute_path" in str(error.value)
    assert local_path not in str(error.value)


@pytest.mark.parametrize(
    "url",
    (
        "https://example.com/private/path",
        "http://localhost:8080/projects/alpha",
        "See https://example.com/a/b?next=/projects/alpha for details",
    ),
)
def test_http_urls_are_not_classified_as_local_paths(url):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    assert "absolute_path" not in {finding.category for finding in gate.scan(url).findings}


def test_http_url_does_not_mask_a_later_local_path():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan("See https://example.com/public then /tmp/private")

    assert {finding.category for finding in report.findings} == {"absolute_path"}


@pytest.mark.parametrize(
    "value",
    (
        "https://example.com,/tmp/private",
        "https://example.com);/root/private",
        "prefix</Users/private/atlas",
        r"https://example.com,C:\private\atlas",
        r"https://example.com);\\server\share\atlas",
    ),
)
def test_url_delimiters_do_not_mask_adjacent_local_paths(value):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": value})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": value})
    assert str(error.value) == "public bundle blocked: absolute_path"
    assert value not in str(error.value)


@pytest.mark.parametrize(
    "url",
    (
        "https://example.com/docs/v1/getting-started",
        "https://example.com/search?q=/tmp/example&mode=exact",
        "https://example.com/projects/alpha?view=full#decisions",
        "http://localhost:8080/a/b?next=/projects/alpha#top",
        "See (https://example.com/a/b?q=one,two#part).",
    ),
)
def test_http_url_paths_queries_and_fragments_remain_safe(url):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    assert "absolute_path" not in {finding.category for finding in gate.scan(url).findings}


@pytest.mark.parametrize(
    "markup",
    (
        '<a href="/tmp/private">link</a>',
        r"<div data-path='C:\private\x'>content</div>",
        r"<img src=\\server\share\x>",
        '<div style="background:url(/root/private)">content</div>',
    ),
)
def test_markup_attribute_local_paths_are_blocked_without_value_leak(markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": markup})
    assert str(error.value) == "public bundle blocked: absolute_path"
    assert markup not in str(error.value)


@pytest.mark.parametrize(
    "malformed_markup",
    (
        "<div /tmp/private>",
        r"<div C:\private\x>",
        r"<div \\server\share\x>",
        "<DiV \t /tmp/private \n>",
        "<DIV\tC:\\private\\x \n>",
        "<dIv\n\\\\server\\share\\x\t>",
    ),
)
def test_name_only_markup_paths_are_blocked_without_value_leak(malformed_markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": malformed_markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": malformed_markup})
    assert str(error.value) == "public bundle blocked: absolute_path"
    assert malformed_markup not in str(error.value)


@pytest.mark.parametrize(
    "markup",
    (
        '<a href="https://example.com/docs/path?q=/tmp/example#top">Docs</a>',
        "<img src='https://cdn.example.com/assets/image.png?size=2x'>",
        "Visible https://example.com/docs/path?q=/tmp/example#top",
        "<a href=https://example.com/docs/path>https://example.com/public/path</a>",
        "Closing tag </a> remains ordinary text",
    ),
)
def test_public_urls_in_markup_attributes_and_visible_text_remain_safe(markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    assert "absolute_path" not in {finding.category for finding in gate.scan(markup).findings}


@pytest.mark.parametrize(
    "markup",
    (
        "<img />",
        '<div class="summary" data-state=ready>content</div>',
    ),
)
def test_ordinary_start_and_self_closing_tags_remain_safe(markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    assert "absolute_path" not in {finding.category for finding in gate.scan(markup).findings}


@pytest.mark.parametrize(
    ("attribute", "route", "quoted"),
    (
        ("href", "/", True),
        ("href", "/?from=atlas#top", True),
        ("href", "/projects", True),
        ("href", "/projects/alpha", True),
        ("href", "/projects/alpha", False),
        ("href", "/projects/alpha%2Ebeta?tab=decisions#evidence", True),
        ("href", "/topics", True),
        ("href", "/topics/ai?sort=recent#projects", True),
        ("href", "/graph?mode=full#canvas", True),
        ("href", "/changelog#latest", True),
        ("action", "/search?q=/tmp/example#results", True),
        ("src", "/assets/images/atlas.png?v=2#preview", True),
    ),
)
def test_allowlisted_public_routes_are_safe_in_url_bearing_attributes(attribute, route, quoted):
    gate = PrivacyGate(alias_key=b"unit-test-key")
    attribute_value = f'"{route}"' if quoted else route
    markup = f"<a {attribute}={attribute_value}>Atlas</a>"

    assert not gate.scan({"summary": markup}).findings


@pytest.mark.parametrize(
    "markup",
    (
        '<a href="/tmp/private">Atlas</a>',
        '<a href="/root/private">Atlas</a>',
        '<a href="/home/dowon/private">Atlas</a>',
        '<a href="/Users/private/atlas">Atlas</a>',
        '<a href="/etc/passwd">Atlas</a>',
        '<a href="/project/alpha">Atlas</a>',
        '<a href="/projects-archive/alpha">Atlas</a>',
        '<a href="/graph/private">Atlas</a>',
        '<a href="/changelog/2026">Atlas</a>',
        '<a href="/search/advanced">Atlas</a>',
        '<img src="/assets">',
        '<a href="/projects/./alpha">Atlas</a>',
        '<a href="/projects/../tmp">Atlas</a>',
        '<a href="//example.com/projects/alpha">Atlas</a>',
        '<a href="///projects/alpha">Atlas</a>',
        '<a href="/projects\\alpha">Atlas</a>',
        '<a href="/projects/alpha\x1fprivate">Atlas</a>',
        '<a href="/projects%2Falpha">Atlas</a>',
        '<a href="/projects%5Calpha">Atlas</a>',
        '<a href="/projects/%2e%2e/tmp">Atlas</a>',
        '<a href="/projects/%252e%252e/tmp">Atlas</a>',
        '<a href="/projects/%252Ftmp">Atlas</a>',
        '<a href="/%2574mp">Atlas</a>',
        '<a href="%2Ftmp/private">Atlas</a>',
        '<a href="%252Ftmp/private">Atlas</a>',
        '<a href="%5Ctmp%5Cprivate">Atlas</a>',
        '<a href="%255Ctmp%255Cprivate">Atlas</a>',
        '<a href="%2E%2E%2Ftmp">Atlas</a>',
        '<a href="%252E%252E%252Ftmp">Atlas</a>',
        '<a href="%2F%2Fexample.com/projects/alpha">Atlas</a>',
        '<a href="%252F%252Fexample.com/projects/alpha">Atlas</a>',
        '<a href="/%2Fexample.com/projects/alpha">Atlas</a>',
        '<a href="%2F/projects/alpha">Atlas</a>',
        '<a href="docs/%2E%2E/tmp">Atlas</a>',
        '<a href="docs%2500private">Atlas</a>',
        '<a href="docs\x1fprivate">Atlas</a>',
        '<div data-route="/projects/alpha">Atlas</div>',
        '<div title="/topics/ai">Atlas</div>',
        '<p>/projects/alpha</p>',
        "/projects/alpha",
    ),
)
def test_hostile_or_out_of_context_public_route_lookalikes_are_blocked(markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": markup})
    assert str(error.value) == "public bundle blocked: absolute_path"
    assert markup not in str(error.value)


def test_url_attribute_decode_limit_exhaustion_fails_closed():
    encoded = "%41tlas"
    for _ in range(32):
        encoded = quote(encoded, safe="")
    markup = f'<a href="{encoded}">Atlas</a>'
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": markup})
    assert str(error.value) == "public bundle blocked: absolute_path"
    assert encoded not in str(error.value)


def test_url_attribute_decode_non_convergence_fails_closed(monkeypatch):
    original_unquote = privacy_module.unquote

    def cycle_unquote(value, *args, **kwargs):
        if value == "cycle-a":
            return "cycle-b"
        if value == "cycle-b":
            return "cycle-a"
        return original_unquote(value, *args, **kwargs)

    monkeypatch.setattr(privacy_module, "unquote", cycle_unquote)
    markup = '<a href="cycle-a">Atlas</a>'
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]


@pytest.mark.parametrize(
    "malformed_markup",
    (
        '<a href="/tmp/private>',
        r"<div data-path='C:\private\x>",
        '<div style="background:url(/root/private)>',
    ),
)
def test_malformed_markup_with_plausible_local_path_fails_closed(malformed_markup):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"summary": malformed_markup})

    assert str(error.value) == "public bundle blocked: absolute_path"
    assert malformed_markup not in str(error.value)


def test_markup_parser_failure_falls_back_to_path_scan(monkeypatch):
    markup = '<a href="/tmp/private">link</a>'
    gate = PrivacyGate(alias_key=b"unit-test-key")

    def fail_parser(parser, value):
        raise RuntimeError("injected parser failure")

    monkeypatch.setattr(privacy_module._SingleStartTagParser, "feed", fail_parser)

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]


def test_raw_start_tag_isolation_failure_falls_back_to_path_scan(monkeypatch):
    markup = "<div /tmp/private>"
    gate = PrivacyGate(alias_key=b"unit-test-key")

    monkeypatch.setattr(privacy_module._SingleStartTagParser, "get_starttag_text", lambda parser: "<div>")

    report = gate.scan({"summary": markup})

    assert [(finding.category, finding.json_pointer) for finding in report.findings] == [
        ("absolute_path", "/summary")
    ]


def test_alias_is_deterministic_and_does_not_embed_source():
    first = hmac_alias("Private Client", b"local-key", "CLIENT")
    second = hmac_alias("Private Client", b"local-key", "CLIENT")

    assert first == second
    assert re.fullmatch(r"CLIENT_[A-F0-9]{8}", first)
    assert "Private" not in first


def test_html_comments_and_source_maps_are_blocked():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan("<!-- internal -->\n//# sourceMappingURL=app.js.map")

    assert {item.category for item in report.findings} == {"html_comment", "source_map"}


def test_standalone_source_map_file_references_are_blocked():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({"asset": "static/app.js.map"})

    assert {item.category for item in report.findings} == {"source_map"}


def test_source_denylist_blocks_environment_sessions_and_raw_logs(tmp_path):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    for relative in [".env", ".codex/sessions/session.jsonl", "logs/raw.log"]:
        with pytest.raises(PrivacyViolation):
            gate.require_allowed_source(tmp_path / relative)


def test_explicit_public_contact_is_allowlisted_but_other_email_is_blocked():
    gate = PrivacyGate(alias_key=b"unit-test-key", approved_public_values={"public@example.com"})

    assert not gate.scan({"publicEmail": "public@example.com"}).findings
    assert {item.category for item in gate.scan({"notes": "private@example.com"}).findings} == {"email"}


def test_recursive_scan_checks_mapping_keys_values_and_sequences():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan(
        {
            "metadata": {"sk-test-secret-value": "safe"},
            "items": [{"contact": "010-1234-5678"}, {"network": "192.168.1.8"}],
        }
    )

    assert {item.category for item in report.findings} == {"secret", "phone", "private_ip"}
    assert {item.json_pointer for item in report.findings} == {"/metadata", "/items/0/contact", "/items/1/network"}


def test_non_string_mapping_keys_still_scan_nested_values():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    report = gate.scan({7: {"token": "sk-test-secret-value"}})

    assert {item.category for item in report.findings} == {"unsupported_value", "secret"}
    assert {item.json_pointer for item in report.findings} == {"", "/<non-string-key>/token"}


def test_reports_and_exceptions_do_not_leak_matching_content():
    gate = PrivacyGate(alias_key=b"unit-test-key")
    secret = "sk-test-secret-value"
    path = "/home/dowon/private"

    report = gate.scan({"payload": f"{secret} {path}"})
    serialized_report = str(asdict(report))

    assert secret not in serialized_report
    assert path not in serialized_report
    with pytest.raises(PrivacyViolation) as error:
        gate.require_safe({"payload": f"{secret} {path}"})
    assert secret not in str(error.value)
    assert path not in str(error.value)
    assert "secret" in str(error.value)
    assert "absolute_path" in str(error.value)


def test_allowlist_does_not_allow_embedded_public_contact():
    gate = PrivacyGate(alias_key=b"unit-test-key", approved_public_values={"public@example.com"})

    report = gate.scan({"note": "Contact public@example.com for details."})

    assert {item.category for item in report.findings} == {"email"}


def test_empty_and_null_values_remain_safe():
    gate = PrivacyGate(alias_key=b"unit-test-key")

    assert not gate.scan({"empty": "", "null": None, "items": [False, 0, 1.5]}).findings


def test_source_normalization_blocks_dot_segments_mixed_separators_and_symlinks(tmp_path):
    gate = PrivacyGate(alias_key=b"unit-test-key")
    denied_target = tmp_path / "private-data"
    denied_target.mkdir()
    source_link = tmp_path / "published"
    source_link.symlink_to(denied_target, target_is_directory=True)
    mixed_separator_path = Path(f"{tmp_path}\\safe\\..\\logs\\raw.log")

    for path in [tmp_path / "safe" / ".." / "logs" / "raw.log", mixed_separator_path, source_link / "entry.md"]:
        with pytest.raises(PrivacyViolation) as error:
            gate.require_allowed_source(path)
        assert str(path) not in str(error.value)


@pytest.mark.parametrize("resolution_error", [OSError("filesystem failure"), RuntimeError("symlink loop")])
def test_source_resolution_failures_block_without_leaking_path_or_error(tmp_path, monkeypatch, resolution_error):
    gate = PrivacyGate(alias_key=b"unit-test-key")
    source_path = tmp_path / "private-source"

    def fail_resolve(self, strict=False):
        raise resolution_error

    monkeypatch.setattr(type(source_path), "resolve", fail_resolve)

    with pytest.raises(PrivacyViolation) as error:
        gate.require_allowed_source(source_path)

    assert "source_resolution" in str(error.value)
    assert str(source_path) not in str(error.value)
    assert str(resolution_error) not in str(error.value)


def test_source_normalization_supports_explicit_case_modes():
    source = ".CODEX/SESSIONS/session.jsonl"

    assert not _contains_denied_source_part(source, case_sensitive=True)
    assert _contains_denied_source_part(source, case_sensitive=False)
    assert _contains_denied_source_part("LOGS/raw.log", case_sensitive=False)


@pytest.mark.skipif(os.name != "nt", reason="case-sensitive source paths are valid on this platform")
def test_source_denylist_respects_case_insensitive_platform_semantics(tmp_path):
    gate = PrivacyGate(alias_key=b"unit-test-key")

    with pytest.raises(PrivacyViolation):
        gate.require_allowed_source(tmp_path / "LOGS" / "raw.log")


def test_alias_rejects_empty_keys_and_unsafe_prefixes_without_echoing_inputs():
    with pytest.raises(ValueError) as empty_key:
        hmac_alias("Private Client", b"", "CLIENT")
    with pytest.raises(ValueError) as unsafe_prefix:
        hmac_alias("Private Client", b"local-key", "private client")

    assert "Private Client" not in str(empty_key.value)
    assert "private client" not in str(unsafe_prefix.value)
