import os
import re
from dataclasses import asdict
from pathlib import Path

import pytest

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
