#!/usr/bin/env python3
"""Promote project problem statements and materialize evidence-backed system maps."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml

REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from atlas_worker.models import validate_schema
from scripts.project_system_map_specs import SPECS


_ARTICLE_ORDER = (
    "project_id",
    "title",
    "summary",
    "orientation",
    "orientation_evidence_ids",
    "readiness",
    "prior_context",
    "sections",
    "decision_index",
)
_SERVICE_TERMS = ("api", "backend", "proxy", "provider", "server", "모델", "서버", "호출", "공급자")
_STATE_TERMS = (
    "cookie",
    "database",
    "db",
    "json",
    "memory",
    "schema",
    "sqlite",
    "state",
    "기록",
    "메모리",
    "보존",
    "상태",
    "스키마",
    "원장",
    "저장",
)
_INTERFACE_TERMS = (
    "browser",
    "desktop",
    "mobile",
    "popup",
    "ui",
    "web",
    "widget",
    "데스크톱",
    "모바일",
    "브라우저",
    "위젯",
    "웹",
    "화면",
)
_GUARDRAIL_TERMS = (
    "approval",
    "auth",
    "boundary",
    "fallback",
    "gate",
    "privacy",
    "rollback",
    "validation",
    "검증",
    "경계",
    "롤백",
    "보안",
    "분리",
    "실패",
    "승인",
    "제한",
)
_INDEXED_OPENING_TITLES = {
    "260317-desktop-scheduler": "바탕화면에서 바로 여는 단일 사용자 일정표",
    "260331-iphone-calculator-clone": "일반 계산기가 아닌 상호작용 클론",
    "260401-wine-cellar-scan": "인식보다 확인을 중심에 둔 v1",
    "260410-keyboard-piano": "설치 없이 바로 연주하는 정적 앱",
    "260418-japanese-word-study": "단어 수보다 다시 만날 순서",
    "260621-easy-news": "세 분 안에 이슈 흐름 읽기",
    "260725-household-account-book": "월별 화면보다 연간 비교 유지",
}


class _LiteralDumper(yaml.SafeDumper):
    pass


def _represent_string(dumper: yaml.SafeDumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_LiteralDumper.add_representer(str, _represent_string)


def promote_opening_to_orientation(article: dict[str, Any]) -> bool:
    """Move the article's own opening problem statement above the tabbed sections."""
    indexed_section_ids = {
        item["section_id"] for item in article.get("decision_index", [])
    }
    if article.get("orientation"):
        if not article.get("orientation_evidence_ids"):
            raise ValueError("existing orientation must retain evidence IDs")
        existing_section_ids = {section["id"] for section in article.get("sections", [])}
        missing_indexed_sections = indexed_section_ids - existing_section_ids
        if not missing_indexed_sections:
            return False
        if missing_indexed_sections != {"planning-background"}:
            raise ValueError("decision index references an unknown non-opening section")
        opening_title = _INDEXED_OPENING_TITLES.get(article["project_id"])
        if opening_title is None:
            raise ValueError("indexed opening section needs a curated title")
        original_orientation = article["orientation"]
        article["orientation"] = _first_sentence(original_orientation)
        article["sections"].insert(
            0,
            {
                "id": "planning-background",
                "title": opening_title,
                "section_type": "decision",
                "body": original_orientation,
                "evidence_ids": list(article["orientation_evidence_ids"]),
            },
        )
        return True

    sections = article.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("article must contain an opening section")
    opening = sections[0]
    if opening.get("section_type") != "planning":
        raise ValueError("the first section must be a planning problem statement")
    evidence_ids = opening.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValueError("the opening problem statement must cite evidence")

    keep_as_decision = opening["id"] in indexed_section_ids
    article["orientation"] = (
        _first_sentence(opening["body"]) if keep_as_decision else opening["body"]
    )
    article["orientation_evidence_ids"] = list(evidence_ids)
    if keep_as_decision:
        opening["section_type"] = "decision"
    else:
        article["sections"] = sections[1:]
    return True


def build_system_map(article: dict[str, Any]) -> dict[str, Any]:
    """Build a project-function map from a reviewed, evidence-linked specification."""
    sections = {section["id"]: section for section in article.get("sections", [])}
    spec = SPECS.get(article["project_id"])
    if spec is None:
        return _build_testable_fallback_map(article, sections)

    nodes = []
    evidence_ids: list[str] = []
    seen_evidence: set[str] = set()
    for source in spec["nodes"]:
        section_id = source["section"]
        if section_id not in sections:
            raise ValueError(
                f"system map specification references missing section {section_id} "
                f"for {article['project_id']}"
            )
        nodes.append({key: source[key] for key in ("id", "label", "kind", "description")})
        for evidence_id in sections[section_id].get("evidence_ids", []):
            if evidence_id not in seen_evidence:
                evidence_ids.append(evidence_id)
                seen_evidence.add(evidence_id)

    decision_links = []
    node_by_section: dict[str, list[str]] = {}
    for source in spec["nodes"]:
        node_by_section.setdefault(source["section"], []).append(source["id"])
    for section_id in spec["decision_sections"]:
        section = sections.get(section_id)
        node_ids = node_by_section.get(section_id, [])
        if section is None or not node_ids:
            raise ValueError(
                f"system map decision link references missing map subject {section_id} "
                f"for {article['project_id']}"
            )
        decision_links.append(
            {
                "node_ids": node_ids,
                "section_id": section_id,
                "label": section["title"],
            }
        )
        for evidence_id in section.get("evidence_ids", []):
            if evidence_id not in seen_evidence:
                evidence_ids.append(evidence_id)
                seen_evidence.add(evidence_id)

    return {
        "project_id": article["project_id"],
        "map_type": spec["map_type"],
        "title": spec["title"],
        "summary": spec["summary"],
        "nodes": nodes,
        "flows": spec["flows"],
        "decision_links": decision_links,
        "evidence_ids": evidence_ids,
    }


def _build_testable_fallback_map(
    article: dict[str, Any], sections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Keep small unit fixtures usable without making fallback maps part of the catalog."""
    ordered = list(sections.values())
    if len(ordered) < 2:
        raise ValueError("a public system map needs at least two project subjects")
    selected = (ordered[0], ordered[1], ordered[-1]) if len(ordered) > 2 else tuple(ordered)
    nodes = [
        {
            "id": f"subject-{index:02}",
            "label": _truncate(section["title"], 40),
            "kind": "input" if index == 0 else "output" if index == len(selected) - 1 else "state",
            "description": _first_paragraph(section["body"]),
        }
        for index, section in enumerate(selected)
    ]
    evidence_ids = list(dict.fromkeys(
        evidence_id
        for section in selected
        for evidence_id in section.get("evidence_ids", [])
    ))
    decision = next((section for section in ordered if section["section_type"] == "decision"), None)
    return {
        "project_id": article["project_id"],
        "map_type": "documentation-publishing",
        "title": "프로젝트 입력과 결과",
        "summary": "테스트용 프로젝트 입력이 저장 상태를 거쳐 결과로 이어지는 최소 흐름이다.",
        "nodes": nodes,
        "flows": [
            {"id": f"flow-{index:02}", "from": nodes[index]["id"], "to": nodes[index + 1]["id"], "label": "다음 상태"}
            for index in range(len(nodes) - 1)
        ],
        "decision_links": [
            {"node_ids": [nodes[0]["id"]], "section_id": decision["id"], "label": decision["title"]}
        ] if decision else [],
        "evidence_ids": evidence_ids,
    }


def _node_kind(section: dict[str, Any]) -> str:
    section_type = section["section_type"]
    if section_type == "validation":
        return "guardrail"
    if section_type == "result":
        return "output"
    if section_type == "implementation":
        return "process"

    haystack = f"{section['title']} {_first_paragraph(section['body'])}".lower()
    for kind, terms in (
        ("guardrail", _GUARDRAIL_TERMS),
        ("service", _SERVICE_TERMS),
        ("state", _STATE_TERMS),
        ("interface", _INTERFACE_TERMS),
    ):
        if any(term in haystack for term in terms):
            return kind
    return "process"


def _flow_label(target: dict[str, Any]) -> str:
    return {
        "decision": "다음 판단",
        "implementation": "구현으로 연결",
        "validation": "검증",
        "result": "현재 결과",
    }.get(target["section_type"], "다음 단계")


def _first_paragraph(body: str) -> str:
    return body.strip().split("\n\n", 1)[0].replace("\n", " ")


def _first_sentence(body: str) -> str:
    return re.split(r"(?<=\.)\s+", body.strip(), maxsplit=1)[0]


def _truncate(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 3].rstrip()}..."


def _ordered_article(article: dict[str, Any]) -> dict[str, Any]:
    ordered = {key: article[key] for key in _ARTICLE_ORDER if key in article}
    ordered.update({key: value for key, value in article.items() if key not in ordered})
    return ordered


def _dump_yaml(value: dict[str, Any]) -> str:
    return yaml.dump(
        value,
        Dumper=_LiteralDumper,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def materialize(workspace: Path, expected_count: int, check: bool) -> tuple[int, int]:
    article_paths = sorted(
        workspace.glob("projects/**/project_memory/project-atlas/article.yaml")
    )
    if len(article_paths) != expected_count:
        raise ValueError(
            f"expected {expected_count} curated articles, found {len(article_paths)}"
        )

    changed_articles = 0
    changed_maps = 0
    for article_path in article_paths:
        loaded = yaml.safe_load(article_path.read_text(encoding="utf-8"))
        article = deepcopy(loaded)
        promote_opening_to_orientation(article)
        article = _ordered_article(article)
        system_map = build_system_map(article)
        validate_schema(article, "project-article")
        validate_schema(system_map, "project-system-map")

        article_text = _dump_yaml(article)
        map_path = article_path.with_name("system-map.yaml")
        map_text = _dump_yaml(system_map)
        article_changed = article_path.read_text(encoding="utf-8") != article_text
        map_changed = not map_path.exists() or map_path.read_text(encoding="utf-8") != map_text
        changed_articles += int(article_changed)
        changed_maps += int(map_changed)
        if not check:
            if article_changed:
                _write_atomic(article_path, article_text)
            if map_changed:
                _write_atomic(map_path, map_text)

    return changed_articles, changed_maps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=33)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed_articles, changed_maps = materialize(
        args.workspace.expanduser().resolve(), args.expected_count, args.check
    )
    print(
        f"articles_changed={changed_articles} system_maps_changed={changed_maps} "
        f"mode={'check' if args.check else 'write'}"
    )
    return int(bool(args.check and (changed_articles or changed_maps)))


if __name__ == "__main__":
    raise SystemExit(main())
