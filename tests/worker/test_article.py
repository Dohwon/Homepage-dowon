from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atlas_worker.article import (
    ArticleValidator,
    lint_article_title,
    load_project_article,
    load_project_evidence,
    load_system_map,
)
from atlas_worker.content_audit import audit_project_content
from atlas_worker.privacy import PrivacyGate
from atlas_worker.source_manifest import SourceManifest
from tests.worker.helpers import make_project_ref


SAFE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<title>Lifecycle</title><desc>Data lifecycle</desc><path id="line" d="M0 0"/>'
    '</svg>'
)


def _gate() -> PrivacyGate:
    return PrivacyGate(alias_key=b"article-test-key")


def _atlas_dir(root: Path) -> Path:
    directory = root / "project_memory" / "project-atlas"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _evidence(evidence_id: str = "ev-spec") -> dict[str, object]:
    return {
        "id": evidence_id,
        "project_id": "alpha",
        "label": "Curated specification",
        "source_type": "spec",
        "source_locator": "/private/atlas/spec.md:12",
        "observed_at": "2026-08-27T10:00:00Z",
        "privacy_class": "private",
        "content_hash": "a" * 64,
        "claim_role": "supports",
    }


def _article(*, diagrams: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "project_id": "alpha",
        "title": "경로 주행 기록 개선",
        "summary": "주행 경로를 영구 도로 기록으로 변환했다.",
        "readiness": "ready",
        "sections": [
            {
                "id": "retention",
                "title": "저장 수명 분리",
                "section_type": "decision",
                "body": "TMAP 경로는 세션 입력으로만 사용한다.\n\nVWorld Feature와 geometry snapshot을 영구 저장한다.",
                "evidence_ids": ["ev-spec"],
                "diagrams": diagrams or [],
            }
        ],
    }


def _write_article(root: Path, article: dict[str, object]) -> Path:
    path = _atlas_dir(root) / "article.yaml"
    path.write_text(yaml.safe_dump(article, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _write_evidence(root: Path, records: list[dict[str, object]]) -> Path:
    path = _atlas_dir(root) / "evidence.yaml"
    path.write_text(yaml.safe_dump(records, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _write_svg(root: Path, diagram_id: str, svg: str) -> Path:
    path = _atlas_dir(root) / "visuals" / f"{diagram_id}.svg"
    path.parent.mkdir(exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return path


def _manifest() -> SourceManifest:
    return SourceManifest("alpha", (), (), "head", "common")


def test_missing_article_returns_none_and_only_then_allows_empty_evidence(tmp_path):
    ref = make_project_ref(tmp_path)

    assert load_project_article(ref, _gate()) is None
    assert load_project_evidence(ref, _gate()) == ()
    assert load_system_map(ref, _gate()) is None


def test_article_loader_preserves_long_markdown_section_order_and_private_projection(tmp_path):
    ref = make_project_ref(tmp_path)
    diagrams = [{"id": "tmap-vworld-lifecycle", "caption": "수명", "alt": "데이터 수명 흐름"}]
    data = _article(diagrams=diagrams)
    data["sections"].append(
        {
            "id": "validation",
            "title": "검증",
            "section_type": "validation",
            "body": "첫 문단\n\n둘째 문단\n\n셋째 문단",
            "evidence_ids": ["ev-spec"],
        }
    )
    _write_article(tmp_path, data)
    _write_evidence(tmp_path, [_evidence()])
    _write_svg(tmp_path, "tmap-vworld-lifecycle", SAFE_SVG)

    article = load_project_article(ref, _gate())

    assert article is not None
    assert [section.section_id for section in article.sections] == ["retention", "validation"]
    assert article.sections[0].body.count("\n\n") == 1
    assert article.sections[1].body.count("\n\n") == 2
    diagram = article.sections[0].diagrams[0]
    assert diagram.diagram_id == "tmap-vworld-lifecycle"
    public = article.to_public_dict()
    assert public["sections"][0]["diagrams"] == diagrams
    assert "source_path" not in str(public)
    assert "svg" not in str(public)
    assert "source_locator" not in str(public)
    assert "content_hash" not in str(public)


@pytest.mark.parametrize(
    ("title", "code"),
    (
        ("", "blank-title"),
        ("웹 앱이 멈추는 순간, 기록도 함께 멈췄다", "dramatic-copy"),
        ("드디어 완벽한 경로 기록을 만들었다", "superlative-copy"),
        ("정말 중요한 변경!!", "excessive-punctuation"),
        ("a" * 61, "title-too-long"),
    ),
)
def test_title_lint_uses_stable_neutral_finding_codes(title, code):
    assert code in lint_article_title(title)


def test_article_requires_evidence_for_references_and_resolves_decisions(tmp_path):
    ref = make_project_ref(tmp_path)
    data = _article()
    data["decision_index"] = [
        {"decision_id": "keep-vworld", "section_id": "retention", "status": "adopted", "evidence_ids": ["ev-spec"]}
    ]
    _write_article(tmp_path, data)

    with pytest.raises(ValueError, match="evidence.yaml"):
        load_project_article(ref, _gate())

    _write_evidence(tmp_path, [_evidence()])
    assert load_project_article(ref, _gate()) is not None


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data["sections"].append({**data["sections"][0], "title": "duplicate"}),
        lambda data: data.update({"decision_index": [
            {"decision_id": "same", "section_id": "retention", "status": "adopted", "evidence_ids": ["ev-spec"]},
            {"decision_id": "same", "section_id": "retention", "status": "revised", "evidence_ids": ["ev-spec"]},
        ]}),
        lambda data: data["sections"][0].update({"diagrams": [
            {"id": "same-diagram", "caption": "a", "alt": "a"},
            {"id": "same-diagram", "caption": "b", "alt": "b"},
        ]}),
        lambda data: data["sections"][0].update({"evidence_ids": ["ev-spec", "ev-spec"]}),
        lambda data: data.update({"decision_index": [
            {"decision_id": "bad-section", "section_id": "missing", "status": "adopted", "evidence_ids": ["ev-spec"]}
        ]}),
    ),
)
def test_article_rejects_duplicate_ids_references_and_unknown_decision_sections(tmp_path, mutation):
    ref = make_project_ref(tmp_path)
    data = _article()
    mutation(data)
    _write_article(tmp_path, data)
    _write_evidence(tmp_path, [_evidence()])
    _write_svg(tmp_path, "same-diagram", SAFE_SVG)

    with pytest.raises(ValueError, match="duplicate|section"):
        load_project_article(ref, _gate())


def test_article_rejects_duplicate_yaml_keys_and_unapproved_yaml_diagram_paths(tmp_path):
    ref = make_project_ref(tmp_path)
    article_path = _atlas_dir(tmp_path) / "article.yaml"
    article_path.write_text("project_id: alpha\ntitle: one\ntitle: two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate YAML key"):
        load_project_article(ref, _gate())

    data = _article(diagrams=[{"id": "safe", "caption": "safe", "alt": "safe", "path": "../outside.svg"}])
    _write_article(tmp_path, data)
    _write_evidence(tmp_path, [_evidence()])
    with pytest.raises(ValueError, match="path"):
        load_project_article(ref, _gate())


@pytest.mark.parametrize(
    "unsafe_svg",
    (
        "<!DOCTYPE svg><svg viewBox='0 0 1 1'><title>x</title><desc>x</desc></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><script/></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><foreignObject/></svg>",
        "<svg viewBox='0 0 1 1' onload='x'><title>x</title><desc>x</desc></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><use href='https://x'/></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><use href='//x'/></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><use href='../x'/></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><style>@import url(https://x)</style></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><style>fill:url(https://x)</style></svg>",
        "<svg><title>x</title><desc>x</desc></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title></svg>",
        "<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc>",
    ),
)
def test_referenced_svg_uses_structured_safety_gate(tmp_path, unsafe_svg):
    ref = make_project_ref(tmp_path)
    _write_article(tmp_path, _article(diagrams=[{"id": "unsafe", "caption": "unsafe", "alt": "unsafe"}]))
    _write_evidence(tmp_path, [_evidence()])
    _write_svg(tmp_path, "unsafe", unsafe_svg)

    with pytest.raises(ValueError, match="article-svg"):
        load_project_article(ref, _gate())


def test_system_map_is_optional_and_uses_same_svg_gate(tmp_path):
    ref = make_project_ref(tmp_path)
    assert load_system_map(ref, _gate()) is None
    path = _atlas_dir(tmp_path) / "system-map.svg"
    path.write_text(SAFE_SVG, encoding="utf-8")
    assert load_system_map(ref, _gate()) == SAFE_SVG
    path.write_text("<svg viewBox='0 0 1 1'><title>x</title><desc>x</desc><script/></svg>", encoding="utf-8")
    with pytest.raises(ValueError, match="system-map-svg"):
        load_system_map(ref, _gate())


def test_evidence_loader_rejects_cross_project_duplicate_ids_and_invalid_records(tmp_path):
    ref = make_project_ref(tmp_path)
    _write_article(tmp_path, _article())
    bad = _evidence()
    bad["project_id"] = "beta"
    with pytest.raises(ValueError, match="project"):
        _write_evidence(tmp_path, [bad])
        load_project_evidence(ref, _gate())

    duplicate = [_evidence(), _evidence()]
    _write_evidence(tmp_path, duplicate)
    with pytest.raises(ValueError, match="duplicate evidence"):
        load_project_evidence(ref, _gate())

    invalid = _evidence()
    invalid["extra"] = "no"
    _write_evidence(tmp_path, [invalid])
    with pytest.raises(ValueError, match="allowed"):
        load_project_evidence(ref, _gate())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_type", []),
        ("privacy_class", []),
        ("claim_role", []),
        ("observed_at", "2026-08-27"),
        ("content_hash", "A" * 64),
        ("url", "not a uri"),
    ),
)
def test_evidence_loader_reports_invalid_literals_and_shapes_as_value_errors(tmp_path, field, value):
    ref = make_project_ref(tmp_path)
    _write_article(tmp_path, _article())
    record = _evidence()
    record[field] = value
    _write_evidence(tmp_path, [record])

    with pytest.raises(ValueError):
        load_project_evidence(ref, _gate())


def test_article_loader_rejects_symlinked_sources_without_following_them(tmp_path):
    ref = make_project_ref(tmp_path)
    outside = tmp_path / "outside.yaml"
    outside.write_text(yaml.safe_dump(_article(), allow_unicode=True), encoding="utf-8")
    article_path = _atlas_dir(tmp_path) / "article.yaml"
    article_path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        load_project_article(ref, _gate())


def test_loaded_article_validator_is_called_by_audit_and_can_return_ready(tmp_path):
    ref = make_project_ref(tmp_path)
    _write_article(tmp_path, _article())
    _write_evidence(tmp_path, [_evidence()])
    article = load_project_article(ref, _gate())
    assert article is not None

    audit = audit_project_content(
        ref, _manifest(), article, load_project_evidence(ref, _gate()), (), article_validator=ArticleValidator()
    )

    assert audit.readiness == "ready"
