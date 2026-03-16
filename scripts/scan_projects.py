#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_DIR = ROOT / "portfolio-homepage"
PROJECTS_DIR = ROOT / "projects"
DATA_DIR = PORTFOLIO_DIR / "data"
BASE_DATA_FILE = DATA_DIR / "projects.json"
GENERATED_FILE = DATA_DIR / "projects.generated.json"
SNAPSHOT_FILE = DATA_DIR / "status_snapshot.json"
STATUS_REPORT_FILE = DATA_DIR / "status_changes.md"

EXCLUDED_FILE_SUFFIXES = {".doc", ".docx", ".pdf"}
EXCLUDED_TOP_LEVEL_DIRS = {"notion"}

IN_PROGRESS_PATTERNS = [
    r"\bin\s*[- ]?progress\b",
    r"진행중",
    r"미완성",
    r"wip",
    r"todo",
]
DONE_PATTERNS = [
    r"완료",
    r"완성",
    r"done",
    r"production",
]

CATEGORY_RULES = [
    ("LLM Evaluation Tooling", ["gemini", "multiturn", "tester"]),
    ("Prompt Evaluation", ["prompt", "judge", "evaluation"]),
    ("Operational Analytics", ["operation", "log", "analy"]),
    ("NLU Schema Engineering", ["schema", "semantic", "verb"]),
    ("NLU Data Analysis", ["형태소", "학습데이터"]),
    ("NLU Similarity Analysis", ["유사도", "similarity"]),
    ("Speech Quality Metrics", ["stt", "cer"]),
]


@dataclass
class Entry:
    id: str
    name: str
    status: str
    category: str
    summary: str
    highlights: List[str]
    stack: List[str]
    tags: List[str]
    path: str
    readme: Optional[str]
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "category": self.category,
            "summary": self.summary,
            "highlights": self.highlights,
            "stack": self.stack,
            "tags": self.tags,
            "path": self.path,
            "readme": self.readme,
            "detail": self.detail,
        }


def slugify(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9가-힣]+", "-", name.strip().lower())
    return re.sub(r"-+", "-", value).strip("-") or "project"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def detect_status(readme_text: str, folder_name: str) -> str:
    lower = f"{folder_name}\n{readme_text}".lower()
    if any(re.search(p, lower) for p in IN_PROGRESS_PATTERNS):
        return "in-progress"
    if any(re.search(p, lower) for p in DONE_PATTERNS):
        return "active"
    if "v3" in folder_name.lower() and "tester" in folder_name.lower():
        return "in-progress"
    return "active"


def detect_category(name: str) -> str:
    lower = name.lower()
    for category, keys in CATEGORY_RULES:
        if any(k in lower for k in keys):
            return category
    return "General"


def default_tags(category: str) -> List[str]:
    mapping = {
        "LLM Evaluation Tooling": ["LLM", "Testing", "Multiturn"],
        "Prompt Evaluation": ["Prompt", "Eval", "Automation"],
        "Operational Analytics": ["Ops", "Log", "Analytics"],
        "NLU Schema Engineering": ["NLU", "Schema", "Corpus"],
        "NLU Data Analysis": ["NLU", "Morphology", "Data"],
        "NLU Similarity Analysis": ["NLU", "Similarity", "Intent"],
        "Speech Quality Metrics": ["STT", "CER", "Speech"],
    }
    return mapping.get(category, ["Project"])


def infer_stack(files: List[Path]) -> List[str]:
    exts = {f.suffix.lower() for f in files}
    stack: List[str] = []
    if ".py" in exts:
        stack.append("Python")
    if ".ipynb" in exts:
        stack.append("Jupyter")
    if ".yaml" in exts or ".yml" in exts:
        stack.append("YAML")
    if ".xlsx" in exts:
        stack.append("XLSX")
    if ".csv" in exts:
        stack.append("CSV")
    if ".json" in exts:
        stack.append("JSON")
    return stack or ["Unknown"]


def is_excluded_file(path: Path) -> bool:
    name = path.name.lower()
    if any(name.endswith(suffix) for suffix in EXCLUDED_FILE_SUFFIXES):
        return True
    if name.endswith(".link.md"):
        return True
    if ":zone.identifier" in name or name.endswith(".zone.identifier"):
        return True
    return False


def summarize_readme(readme_text: str) -> List[str]:
    if not readme_text.strip():
        return ["README가 없어 파일/코드 구조 기반으로 요약했습니다."]

    lines = readme_text.splitlines()
    result: List[str] = []
    in_code = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("#"):
            continue
        line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
        if len(line) < 8:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line not in result:
            result.append(line)
        if len(result) >= 4:
            break

    return result or ["README 핵심 문장을 추출하지 못해 기본 요약으로 대체했습니다."]


def pick_key_files(files: List[Path], limit: int = 6) -> List[str]:
    ranked = sorted(
        files,
        key=lambda p: (
            0 if p.name.lower().startswith("readme") else 1,
            0 if p.suffix.lower() in {".py", ".ipynb", ".yaml", ".yml", ".md"} else 1,
            len(str(p)),
        ),
    )
    out = []
    for p in ranked:
        rel = str(p.relative_to(ROOT))
        if rel not in out:
            out.append(rel)
        if len(out) >= limit:
            break
    return out


def infer_workflow(name: str, files: List[Path], readme_text: str, is_notebook: bool) -> List[Dict[str, str]]:
    lower = name.lower()

    if "gemini_multiturn_tester" in lower:
        return [
            {"step": "입력 준비", "desc": "prompt/env/scenario 또는 excel 테스트 케이스를 준비"},
            {"step": "멀티턴 실행", "desc": "run.py에서 turn 히스토리를 포함해 모델 호출"},
            {"step": "응답 기록", "desc": "요청/응답을 JSONL 또는 결과 파일로 저장"},
            {"step": "결과 분석", "desc": "턴별 품질/정합성을 검토해 프롬프트/정책 개선"},
        ]

    if "prompt_auto_evaluation" in lower:
        return [
            {"step": "테스트 세트 로드", "desc": "sample_tests.csv와 A/B 프롬프트를 입력"},
            {"step": "A/B 응답 생성", "desc": "각 모델 응답을 병렬 생성"},
            {"step": "Judge 판정", "desc": "winner/confidence/case를 JSON 스키마로 평가"},
            {"step": "리포트 산출", "desc": "CSV/JSONL 결과를 저장해 비교/회귀 분석"},
        ]

    if "operation_log_analayzer" in lower:
        return [
            {"step": "운영 로그 수집", "desc": "CSV/XLSX 대화 로그를 입력 데이터로 적재"},
            {"step": "전처리/분할", "desc": "process_logs 계열 스크립트로 정규화 및 분류"},
            {"step": "검색/판정", "desc": "judge_search 등으로 키워드/조건 기반 분석"},
            {"step": "요약 리포트", "desc": "엑셀/요약 파일로 운영 인사이트를 산출"},
        ]

    if "semantic_verb_schema" in lower:
        return [
            {"step": "코퍼스 로드", "desc": "원천 텍스트/사전을 읽어 토큰 후보를 구성"},
            {"step": "정제/필터", "desc": "품사·의미 규칙으로 후보를 필터링"},
            {"step": "스키마 매핑", "desc": "function token/semantic schema에 맞게 구조화"},
            {"step": "산출/검증", "desc": "tsv/yaml 결과를 생성하고 사전 품질을 점검"},
        ]

    if is_notebook:
        return [
            {"step": "데이터 로드", "desc": "노트북에서 입력 데이터/로그를 불러옴"},
            {"step": "전처리/특징화", "desc": "분석 목적에 맞게 텍스트/지표를 가공"},
            {"step": "실험 실행", "desc": "유사도/오류율/분류 등 핵심 실험을 수행"},
            {"step": "결과 해석", "desc": "지표와 사례를 바탕으로 개선 포인트를 정리"},
        ]

    if readme_text:
        return [
            {"step": "입력 준비", "desc": "README 기준 입력 파일/파라미터를 준비"},
            {"step": "핵심 실행", "desc": "메인 스크립트 또는 엔트리포인트를 실행"},
            {"step": "결과 저장", "desc": "산출물 파일(JSON/CSV/로그 등) 생성"},
            {"step": "검토", "desc": "결과를 검토해 다음 개선 작업으로 연결"},
        ]

    return [
        {"step": "입력 확인", "desc": "프로젝트 입력 데이터/의존성을 확인"},
        {"step": "처리 실행", "desc": "주요 코드 또는 노트북 셀을 실행"},
        {"step": "결과 확인", "desc": "산출물/로그를 점검해 품질을 판단"},
        {"step": "개선 반영", "desc": "문제점 기반으로 다음 수정안을 도출"},
    ]


def build_detail(name: str, files: List[Path], readme_text: str, is_notebook: bool) -> Dict[str, Any]:
    return {
        "readmeSummary": summarize_readme(readme_text),
        "workflow": infer_workflow(name, files, readme_text, is_notebook),
        "keyFiles": pick_key_files(files),
        "diagramCaption": "입력 -> 처리 -> 평가/검증 -> 결과/개선 흐름",
    }


def build_projects() -> List[Entry]:
    base_data = read_json(BASE_DATA_FILE, {"projects": []})
    existing_by_path = {p["path"]: p for p in base_data.get("projects", [])}
    items: List[Entry] = []

    for child in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        if child.is_dir() and child.name.lower() in EXCLUDED_TOP_LEVEL_DIRS:
            continue

        if child.is_file():
            if is_excluded_file(child):
                continue

            rel_path = str(child.relative_to(ROOT))
            existing = existing_by_path.get(rel_path)
            category = existing["category"] if existing else detect_category(child.name)
            tags = existing["tags"] if existing else default_tags(category)
            files = [child]
            detail = existing.get("detail") if existing and existing.get("detail") else build_detail(
                child.stem, files, "", child.suffix.lower() == ".ipynb"
            )
            entry = Entry(
                id=existing["id"] if existing else slugify(child.stem),
                name=existing["name"] if existing else child.stem,
                status=existing["status"] if existing else "active",
                category=category,
                summary=existing["summary"] if existing else "단일 파일 실험/분석 자산.",
                highlights=existing["highlights"] if existing else ["파일 기반 실험"],
                stack=existing["stack"] if existing else infer_stack(files),
                tags=tags,
                path=rel_path,
                readme=None,
                detail=detail,
            )
            items.append(entry)
            continue

        readme_candidates = list(child.glob("README*")) + list(child.glob("readme*"))
        readme = readme_candidates[0] if readme_candidates else None
        readme_text = readme.read_text(encoding="utf-8", errors="ignore") if readme else ""

        rel_path = str(child.relative_to(ROOT))
        existing = existing_by_path.get(rel_path)
        status = detect_status(readme_text, child.name)
        category = existing["category"] if existing else detect_category(child.name)
        tags = existing["tags"] if existing else default_tags(category)
        files = [p for p in child.rglob("*") if p.is_file() and not is_excluded_file(p)]
        detail = existing.get("detail") if existing and existing.get("detail") else build_detail(
            child.name, files, readme_text, False
        )

        entry = Entry(
            id=existing["id"] if existing else slugify(child.name),
            name=existing["name"] if existing else child.name,
            status=status,
            category=category,
            summary=existing["summary"] if existing else f"{child.name} 프로젝트 자산.",
            highlights=existing["highlights"] if existing else ["프로젝트 스캔 기반 기본 요약"],
            stack=existing["stack"] if existing else infer_stack(files),
            tags=tags,
            path=rel_path,
            readme=str(readme.relative_to(ROOT)) if readme else None,
            detail=detail,
        )
        items.append(entry)

    return items


def write_status_report(old: Dict[str, str], new: Dict[str, str]) -> None:
    changed = []
    for key, status in new.items():
        before = old.get(key)
        if before and before != status:
            changed.append((key, before, status))

    lines = ["# Status Changes", ""]
    if not changed:
        lines.append("- 변경 없음")
    else:
        for key, before, after in changed:
            lines.append(f"- `{key}`: `{before}` -> `{after}`")

    STATUS_REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    base_data = read_json(BASE_DATA_FILE, {})

    projects = build_projects()
    output = {k: v for k, v in base_data.items() if k != "projects"}
    if "owner" not in output:
        output["owner"] = {
            "name": "Dowon",
            "headline": "Portfolio",
            "careerSummary": "",
            "focusAreas": [],
        }
    output["projects"] = [p.to_dict() for p in projects]

    GENERATED_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prev = read_json(SNAPSHOT_FILE, {})
    current = {p.path: p.status for p in projects}
    write_status_report(prev, current)
    SNAPSHOT_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"generated: {GENERATED_FILE}")
    print(f"status report: {STATUS_REPORT_FILE}")


if __name__ == "__main__":
    main()
