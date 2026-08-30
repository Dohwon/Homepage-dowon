#!/usr/bin/env python3
"""Fail-closed audit for the exact 33-project public Atlas catalog."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import sys
import tempfile
from typing import Sequence

REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from atlas_worker.article import load_project_article, load_project_evidence
from atlas_worker.cli import _bundle_context, _discover, _load_runtime_config
from atlas_worker.content_audit import audit_curated_project_content
from atlas_worker.kg import load_project_relations
from atlas_worker.models import EvidenceRecord
from atlas_worker.privacy import PrivacyGate
from atlas_worker.source_manifest import SubprocessGitRunner, build_source_manifest


EXPECTED_PROJECT_IDS = (
    "251104-prompt-auto-evaluation",
    "260212-feeling-traker",
    "260218-ope-log-anlayze",
    "260315-moe-prompt-routing",
    "260317-desktop-scheduler",
    "260319-llm-tool-hub",
    "260321-memento-mori-archive",
    "260322-polite-message-extension",
    "260324-central-memory-prompt-kit",
    "260329-tmap-clone",
    "260331-iphone-calculator-clone",
    "260401-wine-cellar-scan",
    "260405-execution-harness-system",
    "260408-ideal-type-editorial",
    "260410-keyboard-piano",
    "260413-dictionary-transition-bundle",
    "260418-japanese-word-study",
    "260619-chat-friends",
    "260621-easy-news",
    "260626-make-test-set",
    "260725-household-account-book",
    "260727-server-app-web-learn-book",
    "260802-map-diary",
    "260802-map-diary-v2",
    "260802-map-diary-v3",
    "260803-ai-office",
    "a2a-lambda",
    "a2a-normal",
    "a2a-test",
    "gemini-multiturn-tester-v3",
    "operation-log-analayzer",
    "semantic-verb-schema",
    "todack",
)
_GENERIC_CURATED_PATHS = (
    "build-story.md",
    "decisions.md",
    "rollbacks.md",
    "visuals/problem-solving.svg",
)
_DIRECT_RELATIONS = frozenset({"EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT"})
_MAP_DIARY_PATHS = {
    "260802-map-diary": "projects/260802_map_diary",
    "260802-map-diary-v2": "projects/260802_map_diary_v2",
    "260802-map-diary-v3": "projects/260802_map_diary_v3",
    "260329-tmap-clone": "projects/260329_tmap_clone",
}


@dataclass(frozen=True)
class ProjectSetAudit:
    project_ids: tuple[str, ...]
    missing_project_ids: tuple[str, ...]
    unexpected_project_ids: tuple[str, ...]


@dataclass(frozen=True)
class CatalogAudit:
    project_ids: tuple[str, ...]
    missing_project_ids: tuple[str, ...]
    unexpected_project_ids: tuple[str, ...]
    review_required: tuple[str, ...]
    insufficient_evidence: tuple[str, ...]
    generic_decision_documents: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    unreferenced_svgs: tuple[str, ...]
    similarity_edges: tuple[str, ...]
    inferred_relations: tuple[str, ...]
    map_diary_ownership_findings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not any(
            (
                self.missing_project_ids,
                self.unexpected_project_ids,
                self.review_required,
                self.insufficient_evidence,
                self.generic_decision_documents,
                self.invalid_evidence,
                self.unreferenced_svgs,
                self.similarity_edges,
                self.inferred_relations,
                self.map_diary_ownership_findings,
            )
        )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["project_count"] = len(self.project_ids)
        value["ready"] = self.ready
        return value


def audit_project_id_set(project_ids: Sequence[str]) -> ProjectSetAudit:
    actual = tuple(sorted(set(project_ids)))
    expected = set(EXPECTED_PROJECT_IDS)
    return ProjectSetAudit(
        project_ids=actual,
        missing_project_ids=tuple(sorted(expected - set(actual))),
        unexpected_project_ids=tuple(sorted(set(actual) - expected)),
    )


def validate_evidence_owner(project_root: Path, evidence: EvidenceRecord) -> tuple[str, ...]:
    locator = evidence.source_locator.strip()
    try:
        relative, line_text = locator.rsplit(":", 1)
        line_number = int(line_text)
    except (ValueError, AttributeError):
        return ("invalid-evidence-locator",)
    path = PurePosixPath(relative)
    if (
        line_number < 1
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return ("invalid-evidence-locator",)
    if tuple(path.parts[:2]) == ("project_memory", "project-atlas"):
        return ("self-authored-atlas-evidence",)
    source = Path(project_root).joinpath(*path.parts)
    try:
        metadata = source.lstat()
        if source.is_symlink() or not source.is_file():
            return ("evidence-source-unavailable",)
        content = source.read_bytes()
        lines = content.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return ("evidence-source-unavailable",)
    findings: list[str] = []
    if hashlib.sha256(content).hexdigest() != evidence.content_hash:
        findings.append("evidence-content-hash-mismatch")
    if line_number > len(lines) or not lines[line_number - 1].strip():
        findings.append("evidence-claim-line-invalid")
    return tuple(findings)


def audit_public_catalog(workspace: Path) -> CatalogAudit:
    root = Path(workspace).expanduser().resolve()
    config = _load_runtime_config(root)
    gate = PrivacyGate(alias_key=secrets.token_bytes(32))
    discovery = _discover(root, config, source_gate=gate)
    ambiguous = {item.project_id for item in discovery.ambiguous}
    public_refs = {
        item.project_id: item
        for item in discovery.projects
        if item.publication == "public" and item.project_id not in ambiguous
    }
    project_set = audit_project_id_set(tuple(public_refs))
    review_required: set[str] = set()
    insufficient: set[str] = set()
    generic: set[str] = set()
    invalid_evidence: set[str] = set()
    unreferenced_svgs: set[str] = set()
    map_findings: set[str] = set()
    evidence_ids_by_project: dict[str, set[str]] = {}
    relations_by_project: dict[str, tuple[dict[str, object], ...]] = {}
    runner = SubprocessGitRunner()

    for project_id in EXPECTED_PROJECT_IDS:
        ref = public_refs.get(project_id)
        if ref is None:
            continue
        if project_id in _MAP_DIARY_PATHS and ref.relative_path != _MAP_DIARY_PATHS[project_id]:
            map_findings.add(project_id)
        atlas_root = ref.root / "project_memory" / "project-atlas"
        try:
            manifest = build_source_manifest(ref, runner)
            article = load_project_article(ref, gate)
            evidence = load_project_evidence(ref, gate)
            audit = audit_curated_project_content(ref, manifest, (), gate)
            relations = load_project_relations(ref.root, gate)
        except Exception:
            review_required.add(project_id)
            continue
        if article is None or audit.readiness == "insufficient-evidence":
            insufficient.add(project_id)
        elif audit.readiness != "ready" or article.readiness != "ready":
            review_required.add(project_id)
        for record in evidence:
            for code in validate_evidence_owner(ref.root, record):
                invalid_evidence.add(f"{project_id}:{record.evidence_id}:{code}")
        evidence_ids_by_project[project_id] = {record.evidence_id for record in evidence}
        relations_by_project[project_id] = relations
        for relative in _GENERIC_CURATED_PATHS:
            if (atlas_root / relative).exists() or (atlas_root / relative).is_symlink():
                generic.add(f"{project_id}:{relative}")
        referenced = set()
        if article is not None:
            referenced = {
                diagram.source_path
                for section in article.sections
                for diagram in section.diagrams
            }
        visuals = atlas_root / "visuals"
        if visuals.is_dir():
            for svg in visuals.glob("*.svg"):
                relative = svg.relative_to(ref.root).as_posix()
                if relative not in referenced:
                    unreferenced_svgs.add(f"{project_id}:{svg.name}")

    for project_id, relations in relations_by_project.items():
        for relation in relations:
            target = relation["target"]
            if relation["type"] not in _DIRECT_RELATIONS or target not in public_refs:
                review_required.add(project_id)
                continue
            owners = evidence_ids_by_project.get(project_id, set()) | evidence_ids_by_project.get(
                str(target), set()
            )
            if any(item not in owners for item in relation["evidence_ids"]):
                review_required.add(project_id)

    similarity_edges: set[str] = set()
    inferred_relations: set[str] = set()
    if not project_set.missing_project_ids and not project_set.unexpected_project_ids:
        try:
            context = _bundle_context(root, discovery, gate)
            for edge in context.graph.edges:
                if edge.kind == "project-similarity":
                    similarity_edges.add(edge.edge_id)
                if (
                    edge.source_id.startswith("project:")
                    and edge.target_id.startswith("project:")
                    and (edge.kind not in _DIRECT_RELATIONS or not edge.evidence_links)
                ):
                    inferred_relations.add(edge.edge_id)
        except Exception:
            review_required.add("catalog-graph")

    return CatalogAudit(
        project_ids=project_set.project_ids,
        missing_project_ids=project_set.missing_project_ids,
        unexpected_project_ids=project_set.unexpected_project_ids,
        review_required=tuple(sorted(review_required)),
        insufficient_evidence=tuple(sorted(insufficient)),
        generic_decision_documents=tuple(sorted(generic)),
        invalid_evidence=tuple(sorted(invalid_evidence)),
        unreferenced_svgs=tuple(sorted(unreferenced_svgs)),
        similarity_edges=tuple(sorted(similarity_edges)),
        inferred_relations=tuple(sorted(inferred_relations)),
        map_diary_ownership_findings=tuple(sorted(map_findings)),
    )


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = audit_public_catalog(args.workspace)
    payload = result.to_dict()
    if args.output is not None:
        _write_atomic(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
