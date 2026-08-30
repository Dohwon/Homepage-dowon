"""Command-line orchestration for the local Project Atlas worker."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import stat
import sys
import tempfile
from typing import Any

import yaml
from yaml.error import YAMLError

from .backfill import (
    SignalClaimExtractor,
    classify_backfill_claims,
    should_skip_session,
    updated_cursors,
)
from .article import load_project_article, load_project_evidence, load_system_map
from .bundle import (
    BundleContext,
    SearchDocument,
    build_candidate_bundle,
    promote_bundle,
    validate_bundle,
)
from .config import DiscoveryConfig
from .content_audit import audit_curated_project_content
from .discovery import discover_projects
from .evidence import merge_claims
from .fs_safety import (
    FileWrite,
    commit_file_transaction,
    read_confined_text,
    require_write_destination,
)
from .kg import build_knowledge_graph, load_knowledge_taxonomy, load_project_relations
from .memory import load_project_memory
from .memory_writer import plan_project_memory_writes
from .models import (
    DiscoveryReport,
    EvidenceRecord,
    EvidenceClaim,
    ProjectArticle,
    ProjectEvent,
    ProjectMemory,
    ProjectRef,
    PromotionResult,
    PublicProject,
    TagSet,
    validate_schema,
)
from .privacy import MIN_ALIAS_KEY_BYTES, PrivacyGate, PrivacyViolation
from .publish import publish_bundle
from .runtime_state import RuntimeState
from .session_index import index_session, map_session_trace, merge_child_evidence
from .source_manifest import SubprocessGitRunner, build_source_manifest, resolve_git_owner


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_PRIVACY = 3
EXIT_IO = 4
_AUDIT_EMPTY_EVIDENCE_COUNTS = {
    "context": 0,
    "contradicts": 0,
    "supports": 0,
    "total": 0,
}
_AUDIT_EMPTY_SESSION_COUNTS = {
    "ambiguous": 0,
    "mapped": 0,
    "total": 0,
    "unmapped": 0,
}

_PROFILE_KEYS = (
    "id",
    "name",
    "lifecycle",
    "publication",
    "summary",
    "tags",
    "aliases",
    "outcome",
    "rejected_tags",
    "source_files",
    "repository_url",
    "live_url",
)
_REVIEWED_CLAIM_KEYS = frozenset(
    {
        "project_id",
        "claim_type",
        "confidence",
        "evidence_id",
        "event_date",
        "value",
        "selected",
    }
)
_SAFE_ERROR_COMPONENT = re.compile(r"^[A-Za-z0-9_$.[\]-]+$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class ConfigError(ValueError):
    """Configuration failure whose raw details must not reach stderr."""

    def __init__(self, pointer: str = "$") -> None:
        super().__init__("invalid Project Atlas configuration")
        self.pointer = pointer


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ConfigError("/arguments")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="project-atlas")
    commands = parser.add_subparsers(dest="command", required=True)

    discover = commands.add_parser("discover")
    _add_workspace(discover)
    _add_format(discover)

    bootstrap = commands.add_parser("bootstrap-profiles")
    _add_workspace(bootstrap)
    _add_format(bootstrap)
    bootstrap.add_argument("--dry-run", action="store_true")
    bootstrap.add_argument("--apply-reviewed-report", type=Path)

    backfill = commands.add_parser("backfill")
    _add_workspace(backfill)
    _add_format(backfill)
    backfill.add_argument("--sessions-root", type=Path)
    backfill.add_argument("--apply-reviewed-report", type=Path)
    backfill.add_argument("--dry-run", action="store_true")

    build = commands.add_parser("build")
    _add_workspace(build)
    _add_format(build)
    build.add_argument("--dry-run", action="store_true")

    validate = commands.add_parser("validate")
    location = validate.add_mutually_exclusive_group(required=True)
    location.add_argument("--workspace", type=Path)
    location.add_argument("--fixture", type=Path)
    _add_format(validate)

    run = commands.add_parser("run")
    _add_workspace(run)
    _add_format(run)
    run.add_argument("--sessions-root", type=Path)
    run.add_argument("--apply-reviewed-report", type=Path)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--changed-only", action="store_true")

    publish = commands.add_parser("publish")
    _add_workspace(publish)
    _add_format(publish)
    publish.add_argument("--changed-only", action="store_true")
    publish.add_argument("--push", action="store_true")

    audit = commands.add_parser("audit-content")
    _add_workspace(audit)
    _add_format(audit)
    audit.add_argument("--project")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = dispatch(args)
        _emit_json(result)
        return EXIT_OK
    except PrivacyViolation as error:
        _emit_error(_privacy_error_category(error), "$")
        return EXIT_PRIVACY
    except ConfigError as error:
        _emit_error("config", error.pointer)
        return EXIT_VALIDATION
    except (YAMLError, ValueError, TypeError) as error:
        _emit_error("validation", _validation_pointer(error))
        return EXIT_VALIDATION
    except (OSError, UnicodeError):
        _emit_error("io", "$")
        return EXIT_IO


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "discover":
        return _command_discover(args)
    if args.command == "bootstrap-profiles":
        return _command_bootstrap_profiles(args)
    if args.command == "backfill":
        return _command_backfill(args)
    if args.command == "build":
        return _command_build(args)
    if args.command == "validate":
        return _command_validate(args)
    if args.command == "run":
        return _command_run(args)
    if args.command == "publish":
        return _command_publish(args)
    if args.command == "audit-content":
        return _command_audit_content(args)
    raise ConfigError("/command")


def _add_workspace(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=Path, default=Path.cwd())


def _add_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json",), default="json")


def _command_discover(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    report = _discover(workspace, config)
    return _discovery_payload(report)


def _command_bootstrap_profiles(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    report = _discover(workspace, config)
    ambiguous = tuple(_project_record(ref) for ref in report.ambiguous)
    if args.apply_reviewed_report is None:
        if not args.dry_run:
            raise ConfigError("/apply-reviewed-report")
        return {"ambiguous": list(ambiguous), "dry_run": True, "written": []}

    profiles = _load_reviewed_profiles(args.apply_reviewed_report)
    writes = _profile_write_plan(workspace, report, profiles)
    if not args.dry_run:
        commit_file_transaction(tuple(write for write, _ in writes))
    return {
        "ambiguous": list(ambiguous),
        "dry_run": bool(args.dry_run),
        "written": [] if args.dry_run else [relative for _, relative in writes],
        "would_write": [relative for _, relative in writes] if args.dry_run else [],
    }


def _command_backfill(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    report = _discover(workspace, config)
    if not args.dry_run and args.apply_reviewed_report is None:
        raise ConfigError("/apply-reviewed-report")
    sessions_root = _sessions_root(workspace, config, args.sessions_root)
    if sessions_root is None:
        if args.apply_reviewed_report is not None:
            raise ConfigError("/sessions-root")
        return _empty_backfill_result(dry_run=bool(args.dry_run))
    return _execute_backfill(
        workspace,
        config,
        report,
        sessions_root,
        dry_run=bool(args.dry_run),
        reviewed_report=args.apply_reviewed_report,
    )


def _command_build(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    gate = _privacy_gate(workspace, config, ephemeral=bool(args.dry_run))
    report = _discover(workspace, config, source_gate=gate)
    return _execute_build(workspace, config, report, gate, dry_run=bool(args.dry_run))


def _command_validate(args: argparse.Namespace) -> dict[str, object]:
    if args.fixture is not None:
        bundle_dir = Path(args.fixture).expanduser()
    else:
        workspace = _workspace(args.workspace)
        config = _load_runtime_config(workspace)
        bundle_dir = _service_root(workspace, config) / "public-bundle"
    manifest = validate_bundle(bundle_dir, PrivacyGate(alias_key=secrets.token_bytes(32)))
    return {
        "projects": list(manifest.projects),
        "valid": True,
        "version": manifest.version,
    }


def _command_run(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    if args.dry_run:
        return _execute_run(args, workspace, config, runtime_state=None)
    runtime_state = RuntimeState.open(workspace)
    with runtime_state.lock():
        return _execute_run(args, workspace, config, runtime_state=runtime_state)


def _execute_run(
    args: argparse.Namespace,
    workspace: Path,
    config: Mapping[str, object],
    *,
    runtime_state: RuntimeState | None,
) -> dict[str, object]:
    gate = _privacy_gate(workspace, config, ephemeral=bool(args.dry_run))
    report = _discover(workspace, config, source_gate=gate)
    sessions_root = _sessions_root(workspace, config, args.sessions_root)

    if sessions_root is None:
        if args.apply_reviewed_report is not None:
            raise ConfigError("/sessions-root")
        backfill = _empty_backfill_result(dry_run=True)
    else:
        backfill = _execute_backfill(
            workspace,
            config,
            report,
            sessions_root,
            dry_run=bool(args.dry_run) or args.apply_reviewed_report is None,
            reviewed_report=args.apply_reviewed_report,
        )

    build = _execute_build(
        workspace,
        config,
        report,
        gate,
        dry_run=bool(args.dry_run),
        runtime_state=runtime_state,
        changed_only=bool(args.changed_only),
    )
    return {
        "affected_projects": build["affected_projects"],
        "backfill": backfill,
        "build": build,
        "discovery": {
            "ambiguous": len(report.ambiguous),
            "projects": len(report.projects),
        },
        "dry_run": bool(args.dry_run),
        "validation": {
            "projects": build["projects"],
            "valid": bool(build["validated"]),
            "version": build["version"],
        },
    }


def _command_audit_content(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    report = _discover(workspace, config)
    runner = SubprocessGitRunner()
    if args.project is not None:
        project = next((item for item in report.projects if item.project_id == args.project), None)
        if project is None:
            raise ConfigError("/project")
        return build_source_manifest(project, runner).audit_payload()

    gate = PrivacyGate(alias_key=secrets.token_bytes(MIN_ALIAS_KEY_BYTES))
    ambiguous_ids = {ref.project_id for ref in report.ambiguous}
    projects = [
        _audit_content_item(project, runner, gate)
        for project in report.projects
        if project.publication == "public" and project.project_id not in ambiguous_ids
    ]
    return {"projects": projects}


def _command_publish(args: argparse.Namespace) -> dict[str, object]:
    workspace = _workspace(args.workspace)
    config = _load_runtime_config(workspace)
    runtime_state = RuntimeState.open(workspace)
    with runtime_state.lock():
        from scripts.audit_public_atlas_catalog import audit_public_catalog

        catalog = audit_public_catalog(workspace)
        if not catalog.ready:
            raise ConfigError("/catalog-audit")
        gate = _privacy_gate(workspace, config, ephemeral=False)
        discovery = _discover(workspace, config, source_gate=gate)
        build = _execute_build(
            workspace,
            config,
            discovery,
            gate,
            dry_run=False,
            runtime_state=runtime_state,
            changed_only=bool(args.changed_only),
        )
        promotion = PromotionResult(
            changed=bool(build["changed"]),
            changed_projects=tuple(str(item) for item in build["changed_projects"]),
        )
        publication = publish_bundle(
            _service_root(workspace, config),
            promotion,
            push=bool(args.push),
        )
    return {
        "build": build,
        "catalog": {"project_count": len(catalog.project_ids), "ready": catalog.ready},
        "publication": {
            "committed": publication.committed,
            "deferred": publication.deferred,
            "pushed": publication.pushed,
            "staged_paths": list(publication.staged_paths),
        },
    }


def _audit_content_item(
    project: ProjectRef,
    runner: SubprocessGitRunner,
    gate: PrivacyGate,
) -> dict[str, object]:
    try:
        manifest = build_source_manifest(project, runner)
    except Exception:
        return _audit_failure_item(project.project_id, "source-manifest-error")

    item = {
        "project_id": project.project_id,
        "source_manifest": {
            "status": "ready",
            "summary": _manifest_summary(manifest.audit_payload()),
            "finding_codes": [],
        },
        "content_audit": _content_audit_payload(project, manifest, gate),
    }
    gate.require_safe(item)
    return item


def _manifest_summary(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "files": payload["files"],
        "content_hash": payload["content_hash"],
    }


def _content_audit_payload(
    project: ProjectRef,
    manifest: Any,
    gate: PrivacyGate,
) -> dict[str, object]:
    try:
        audit = audit_curated_project_content(project, manifest, (), gate)
    except Exception:
        return _audit_failure_status("content-audit-error")
    return {
        "readiness": audit.readiness,
        "evidence_counts": dict(audit.evidence_counts),
        "session_counts": dict(audit.session_stats),
        "finding_codes": list(audit.findings),
    }


def _audit_failure_item(project_id: str, code: str) -> dict[str, object]:
    return {
        "project_id": project_id,
        "source_manifest": {
            "status": "review-required",
            "summary": None,
            "finding_codes": [code],
        },
        "content_audit": _audit_failure_status(code),
    }


def _audit_failure_status(code: str) -> dict[str, object]:
    return {
        "readiness": "review-required",
        "evidence_counts": dict(_AUDIT_EMPTY_EVIDENCE_COUNTS),
        "session_counts": dict(_AUDIT_EMPTY_SESSION_COUNTS),
        "finding_codes": [code],
    }


def _workspace(value: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.exists() or not candidate.is_dir():
        raise ConfigError("/workspace")
    return candidate.resolve()


def _load_runtime_config(workspace: Path) -> dict[str, object]:
    path = workspace / ".knowledge-worker" / "config.yaml"
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except YAMLError:
        raise ConfigError("/runtime-config") from None
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ConfigError("/runtime-config")
    config = dict(value)
    _validate_runtime_config(config)
    return config


def _validate_runtime_config(config: Mapping[str, object]) -> None:
    if "registered_assets" in config:
        registered = config["registered_assets"]
        if not isinstance(registered, list) or any(not isinstance(item, str) for item in registered):
            raise ConfigError("/runtime-config/registered-assets")
    for key in (
        "sessions_root",
        "aliases_file",
        "service_root",
        "alias_key_file",
        "hmac_key_path",
    ):
        if key in config and (not isinstance(config[key], str) or not config[key]):
            raise ConfigError(f"/runtime-config/{key.replace('_', '-')}")
    if "sessions" in config:
        sessions = config["sessions"]
        if not isinstance(sessions, dict) or any(not isinstance(key, str) for key in sessions):
            raise ConfigError("/runtime-config/sessions")
        if "root" in sessions and (
            not isinstance(sessions["root"], str) or not sessions["root"]
        ):
            raise ConfigError("/runtime-config/sessions/root")


def _discover(
    workspace: Path,
    runtime_config: Mapping[str, object],
    source_gate: PrivacyGate | None = None,
) -> DiscoveryReport:
    registered = runtime_config.get("registered_assets", ())
    if registered is None:
        registered = ()
    if not isinstance(registered, (list, tuple)) or any(not isinstance(item, str) for item in registered):
        raise ConfigError("/registered-assets")
    config = DiscoveryConfig.for_workspace(
        workspace,
        registered_assets=tuple(Path(item) for item in registered),
    )
    if source_gate is None:
        source_gate = PrivacyGate(alias_key=secrets.token_bytes(32))
    return discover_projects(config, source_gate=source_gate)


def _discovery_payload(report: DiscoveryReport) -> dict[str, object]:
    return {
        "ambiguous": [ref.project_id for ref in report.ambiguous],
        "projects": [_project_record(ref) for ref in report.projects],
    }


def _project_record(ref: ProjectRef) -> dict[str, object]:
    return {
        "aliases": list(ref.aliases),
        "id": ref.project_id,
        "lifecycle": ref.lifecycle,
        "name": ref.display_name,
        "publication": ref.publication,
        "relative_path": ref.relative_path,
    }


def _load_reviewed_profiles(path: Path) -> tuple[dict[str, object], ...]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"profiles"}:
        raise ConfigError("/profiles")
    profiles = payload["profiles"]
    if not isinstance(profiles, list) or any(not isinstance(profile, dict) for profile in profiles):
        raise ConfigError("/profiles")
    return tuple(dict(profile) for profile in profiles)


def _profile_write_plan(
    workspace: Path,
    report: DiscoveryReport,
    profiles: tuple[dict[str, object], ...],
) -> tuple[tuple[FileWrite, str], ...]:
    targets = {ref.project_id: ref for ref in report.ambiguous}
    targets.update(
        (ref.project_id, ref)
        for ref in report.projects
        if ref.standalone_asset and ref.profile_path is not None
    )
    seen: set[str] = set()
    writes: list[tuple[FileWrite, str]] = []
    for profile in profiles:
        validate_schema(profile, "project-profile")
        project_id = profile.get("id")
        if not isinstance(project_id, str) or project_id in seen or project_id not in targets:
            raise ConfigError("/profiles/id")
        seen.add(project_id)
        ref = targets[project_id]
        if profile.get("lifecycle") != ref.lifecycle:
            raise ConfigError("/profiles/lifecycle")
        _validate_profile_aliases(profile.get("aliases", ()))
        ordered = {key: profile[key] for key in _PROFILE_KEYS if key in profile}
        content = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False)
        path = ref.profile_path or ref.root / "project_memory" / "project-profile.yaml"
        boundary = ref.root.parent if ref.standalone_asset else ref.root
        if ref.standalone_asset:
            read_confined_text(ref.root, boundary)
        path = require_write_destination(path, boundary)
        if path.exists() and not ref.standalone_asset:
            raise ConfigError("/profiles/id")
        relative = path.relative_to(workspace).as_posix()
        writes.append((FileWrite(path=path, content=content.encode("utf-8"), root=boundary), relative))
    return tuple(sorted(writes, key=lambda item: item[1]))


def _validate_profile_aliases(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, (list, tuple)) or any(not isinstance(alias, str) for alias in value):
        raise ConfigError("/profiles/aliases")
    for alias in value:
        normalized = posixpath.normpath(alias.strip().replace("\\", "/"))
        if (
            not normalized
            or normalized == "."
            or normalized.startswith("/")
            or normalized.startswith("../")
            or _WINDOWS_DRIVE.match(normalized)
        ):
            raise ConfigError("/profiles/aliases")


def _sessions_root(
    workspace: Path,
    runtime_config: Mapping[str, object],
    explicit: Path | None,
) -> Path | None:
    value: object = explicit
    if value is None:
        value = runtime_config.get("sessions_root")
    if value is None:
        sessions = runtime_config.get("sessions")
        if isinstance(sessions, dict):
            value = sessions.get("root")
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise ConfigError("/sessions-root")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    if not path.exists() or not path.is_dir():
        raise ConfigError("/sessions-root")
    return path.resolve()


def _execute_backfill(
    workspace: Path,
    runtime_config: Mapping[str, object],
    discovery: DiscoveryReport,
    sessions_root: Path,
    *,
    dry_run: bool,
    reviewed_report: Path | None,
) -> dict[str, object]:
    aliases = _load_aliases(workspace, runtime_config)
    runtime_root = workspace / ".knowledge-worker"
    cursor_path = require_write_destination(runtime_root / "session-cursor.json", runtime_root)
    cursors = _load_cursor(cursor_path)
    paths = tuple(
        path
        for path in sorted(sessions_root.rglob("*.jsonl"), key=lambda item: item.as_posix())
        if path.is_file() and not path.is_symlink()
    )
    process_paths = paths if reviewed_report is not None else tuple(
        path for path in paths if not should_skip_session(path, cursors)
    )
    scanned = _scan_sessions(process_paths, discovery.projects, aliases)
    sanitized_claims = [_sanitize_claim(project_id, claim) for project_id, claim in scanned["claims"]]
    sanitized_claims.sort(
        key=lambda item: (
            item["project_id"],
            item["claim_type"],
            item["evidence_id"],
        )
    )
    claim_counts = dict(sorted(Counter(item["claim_type"] for item in sanitized_claims).items()))
    classified = classify_backfill_claims(claim for _, claim in scanned["claims"])
    buckets = {
        "automatic": _claim_type_counts(classified.automatic_merge),
        "review": _claim_type_counts(classified.review),
    }

    selected: tuple[tuple[str, EvidenceClaim], ...] = ()
    if reviewed_report is not None:
        selected = _selected_reviewed_claims(reviewed_report, sanitized_claims)

    applied_claims = 0
    applied_files = 0
    applied_projects = 0
    transaction: list[FileWrite] = []
    if selected:
        refs = {ref.project_id: ref for ref in discovery.projects}
        grouped: dict[str, list[EvidenceClaim]] = defaultdict(list)
        for project_id, claim in selected:
            grouped[project_id].append(claim)
        for project_id in sorted(grouped):
            knowledge = merge_claims(grouped[project_id])
            writes = plan_project_memory_writes(refs[project_id], knowledge)
            transaction.extend(writes)
            applied_claims += len(grouped[project_id])
            applied_files += len(writes)
            applied_projects += 1

    cursor_written = False
    if reviewed_report is not None:
        next_cursors = updated_cursors(paths, cursors)
        cursor_content = (
            json.dumps(next_cursors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        transaction.append(FileWrite(path=cursor_path, content=cursor_content, root=runtime_root))
    if not dry_run:
        changed_paths = commit_file_transaction(transaction)
        cursor_written = cursor_path in changed_paths

    return {
        "applied": {
            "claims": applied_claims,
            "files": applied_files,
            "projects": applied_projects,
        },
        "claim_buckets": buckets,
        "claim_counts": claim_counts,
        "claims": sanitized_claims,
        "cursor_written": cursor_written,
        "dry_run": dry_run,
        "sessions": {
            "files": len(paths),
            "mapped_events": scanned["mapped_events"],
            "parse_errors": scanned["parse_errors"],
            "unmapped_events": scanned["unmapped_events"],
            "parent_sessions": scanned["parent_sessions"],
            "child_sessions": scanned["child_sessions"],
            "mapped_by_reason": scanned["mapped_by_reason"],
            "ambiguous_sessions": scanned["ambiguous_sessions"],
        },
    }


def _scan_sessions(
    paths: tuple[Path, ...],
    projects: tuple[ProjectRef, ...],
    aliases: Mapping[str, str],
) -> dict[str, Any]:
    mapped_events = 0
    parse_errors = 0
    unmapped_events = 0
    extractors = {
        project.project_id: SignalClaimExtractor()
        for project in projects
    }
    runner = SubprocessGitRunner()

    def git_owner(path: Path, refs: Sequence[ProjectRef]) -> str | None:
        return resolve_git_owner(path, refs, runner)

    traces = tuple(index_session(path) for path in paths)
    direct_mappings = tuple(
        map_session_trace(trace, projects, aliases, git_owner) for trace in traces
    )
    mappings = merge_child_evidence(traces, direct_mappings)
    mapped_by_reason = Counter(
        mapping.reason for mapping in mappings if mapping.project_id is not None
    )
    for trace, mapping in zip(traces, mappings):
        for event in trace.events:
            if event.parse_error:
                parse_errors += 1
                continue
            if mapping.project_id is None:
                unmapped_events += 1
            else:
                mapped_events += 1
                extractor = extractors.get(mapping.project_id)
                if extractor is not None:
                    extractor.consume(event)

    claims: list[tuple[str, EvidenceClaim]] = []
    for project in projects:
        claims.extend(
            (project.project_id, claim)
            for claim in extractors[project.project_id].claims
        )
    return {
        "claims": tuple(claims),
        "mapped_events": mapped_events,
        "parse_errors": parse_errors,
        "unmapped_events": unmapped_events,
        "parent_sessions": sum(
            1 for mapping in mappings if mapping.child_session_ids
        ),
        "child_sessions": sum(1 for trace in traces if trace.parent_session_id),
        "mapped_by_reason": dict(sorted(mapped_by_reason.items())),
        "ambiguous_sessions": sum(
            1 for mapping in mappings if mapping.reason == "ambiguous"
        ),
    }


def _sanitize_claim(project_id: str, claim: EvidenceClaim) -> dict[str, object]:
    return {
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "event_date": claim.event_date,
        "evidence_id": claim.evidence_id,
        "project_id": project_id,
        "selected": False,
        "value": claim.value,
    }


def _selected_reviewed_claims(
    path: Path,
    candidates: list[dict[str, object]],
) -> tuple[tuple[str, EvidenceClaim], ...]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or "claims" not in payload:
        raise ConfigError("/claims")
    records = payload["claims"]
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ConfigError("/claims")
    available = {
        _reviewed_claim_identity(candidate): candidate
        for candidate in candidates
    }
    selected: list[tuple[str, EvidenceClaim]] = []
    seen: set[tuple[object, ...]] = set()
    for record in records:
        if set(record) != _REVIEWED_CLAIM_KEYS or record.get("selected") is not True:
            raise ConfigError("/claims/selected")
        identity = _reviewed_claim_identity(record)
        if identity in seen or identity not in available:
            raise ConfigError("/claims")
        seen.add(identity)
        project_id = record["project_id"]
        evidence_id = record["evidence_id"]
        selected.append(
            (
                project_id,
                EvidenceClaim(
                    field=f"history:{evidence_id}",
                    value=record["value"],
                    source_class="session",
                    confidence=float(record["confidence"]),
                    evidence_id=evidence_id,
                    claim_type=record["claim_type"],
                    event_date=record["event_date"],
                    selected=True,
                ),
            )
        )
    return tuple(selected)


def _reviewed_claim_identity(record: Mapping[str, object]) -> tuple[object, ...]:
    required = (
        "project_id",
        "claim_type",
        "confidence",
        "evidence_id",
        "event_date",
        "value",
    )
    if any(key not in record for key in required):
        raise ConfigError("/claims")
    values = tuple(record[key] for key in required)
    if (
        any(not isinstance(value, str) or not value or "\n" in value or "\r" in value for value in (values[0], values[1], values[3], values[4], values[5]))
        or not isinstance(values[2], (int, float))
        or isinstance(values[2], bool)
    ):
        raise ConfigError("/claims")
    return values


def _claim_type_counts(claims: Sequence[EvidenceClaim]) -> dict[str, int]:
    return dict(sorted(Counter(claim.claim_type for claim in claims).items()))


def _empty_backfill_result(*, dry_run: bool) -> dict[str, object]:
    return {
        "applied": {"claims": 0, "files": 0, "projects": 0},
        "claim_buckets": {"automatic": {}, "review": {}},
        "claim_counts": {},
        "claims": [],
        "cursor_written": False,
        "dry_run": dry_run,
        "sessions": {
            "files": 0,
            "mapped_events": 0,
            "parse_errors": 0,
            "unmapped_events": 0,
            "parent_sessions": 0,
            "child_sessions": 0,
            "mapped_by_reason": {},
            "ambiguous_sessions": 0,
        },
    }


def _load_aliases(workspace: Path, runtime_config: Mapping[str, object]) -> dict[str, str]:
    configured = runtime_config.get("aliases_file")
    path = Path(configured).expanduser() if isinstance(configured, str) else workspace / ".knowledge-worker" / "project-aliases.yaml"
    if not path.is_absolute():
        path = workspace / path
    if not path.is_file():
        if configured is not None:
            raise OSError("configured aliases file is unavailable")
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except YAMLError:
        raise ConfigError("/aliases") from None
    if isinstance(payload, dict) and "aliases" in payload:
        payload = payload["aliases"]
    if not isinstance(payload, dict) or any(
        not isinstance(alias, str) or not isinstance(project_id, str)
        for alias, project_id in payload.items()
    ):
        raise ConfigError("/aliases")
    return dict(payload)


def _load_cursor(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or any(
        not isinstance(source, str) or not isinstance(checksum, str)
        for source, checksum in payload.items()
    ):
        raise ConfigError("/cursor")
    return dict(payload)


def _execute_build(
    workspace: Path,
    runtime_config: Mapping[str, object],
    discovery: DiscoveryReport,
    gate: PrivacyGate,
    *,
    dry_run: bool,
    runtime_state: RuntimeState | None = None,
    changed_only: bool = False,
) -> dict[str, object]:
    service_root = _service_root(workspace, runtime_config)
    public_dir = service_root / "public-bundle"
    previous_manifest = validate_bundle(public_dir, gate) if public_dir.is_dir() else None
    context = _bundle_context(
        workspace,
        discovery,
        gate,
        previous_manifest=previous_manifest,
    )
    if changed_only and runtime_state is not None:
        affected_projects = runtime_state.changed_project_ids(
            source_hashes=context.source_hashes,
            audit_hashes=context.audit_hashes,
        )
    else:
        affected_projects = tuple(sorted(context.source_hashes))
    with tempfile.TemporaryDirectory(prefix=".project-atlas-staging-", dir=service_root) as temporary:
        staging = Path(temporary) / "candidate"
        manifest = build_candidate_bundle(context, staging)
        validated = validate_bundle(staging, gate)
        changed = False
        changed_projects: list[str] = []
        if not dry_run:
            promotion = promote_bundle(staging, public_dir, gate)
            changed = promotion.changed
            changed_projects = list(promotion.changed_projects)
            validated = validate_bundle(public_dir, gate)
            if runtime_state is not None:
                runtime_state.save_success(
                    source_hashes=context.source_hashes,
                    audit_hashes=context.audit_hashes,
                    manifest=validated.to_dict(),
                )
    return {
        "affected_projects": list(affected_projects),
        "changed": changed,
        "changed_projects": changed_projects,
        "dry_run": dry_run,
        "projects": list(manifest.projects),
        "validated": True,
        "version": validated.version,
    }


def _bundle_context(
    workspace: Path,
    discovery: DiscoveryReport,
    gate: PrivacyGate,
    *,
    previous_manifest: Any = None,
) -> BundleContext:
    ambiguous_ids = {ref.project_id for ref in discovery.ambiguous}
    projects: list[PublicProject] = []
    memories: dict[str, ProjectMemory] = {}
    articles = {}
    evidence_by_project = {}
    relations_by_project = {}
    system_maps = {}
    source_hashes: dict[str, str] = {}
    audit_hashes: dict[str, str] = {}
    git_runner = SubprocessGitRunner()
    for ref in discovery.projects:
        if ref.publication != "public" or ref.project_id in ambiguous_ids:
            continue
        memory = load_project_memory(ref, gate)
        profile = memory.profile
        if profile.get("id") != ref.project_id or profile.get("publication") != "public":
            raise ConfigError("/project-profile/id")
        tags = profile["tags"]
        project = PublicProject(
            project_id=ref.project_id,
            display_name=ref.display_name,
            lifecycle=ref.lifecycle,
            summary=profile["summary"],
            tags=TagSet(
                domain=tuple(tags["domain"]),
                problem=tuple(tags["problem"]),
                pattern=tuple(tags["pattern"]),
                technology=tuple(tags["technology"]),
                outcome=tuple(tags["outcome"]),
            ),
            outcome=profile.get("outcome", ""),
            aliases=(),
        )
        validate_schema(project.to_dict(), "public-project")
        projects.append(project)
        memories[ref.project_id] = memory
        article = None
        evidence = ()
        if not ref.standalone_asset:
            article = load_project_article(ref, gate)
            evidence = load_project_evidence(ref, gate)
            relations = load_project_relations(ref.root, gate)
            if relations:
                relations_by_project[ref.project_id] = relations
        source_manifest = build_source_manifest(ref, git_runner)
        audit_hashes[ref.project_id] = str(source_manifest.audit_payload()["content_hash"])
        if article is not None:
            audit = audit_curated_project_content(
                ref,
                source_manifest,
                (),
                gate,
            )
            if article.readiness != "ready" or audit.readiness != "ready":
                raise ConfigError("/project-atlas/readiness")
            articles[ref.project_id] = article
            evidence_by_project[ref.project_id] = evidence
            system_map = load_system_map(ref, gate)
            if system_map is not None:
                system_maps[ref.project_id] = system_map
        source_hashes[ref.project_id] = _curated_source_hash(
            project,
            article,
            evidence,
            memory.events,
            system_maps.get(ref.project_id),
            relations_by_project.get(ref.project_id, ()),
        )

    ordered = tuple(sorted(projects, key=lambda project: project.project_id))
    graph = build_knowledge_graph(
        ordered,
        articles,
        evidence_by_project,
        relations_by_project,
        load_knowledge_taxonomy(),
    )
    search_documents = tuple(
        document
        for project in ordered
        for document in _project_search_documents(project, articles.get(project.project_id))
    )
    return BundleContext(
        projects=ordered,
        project_memories=memories,
        project_events={
            project_id: memory.events
            for project_id, memory in sorted(memories.items())
            if memory.events
        },
        graph=graph,
        search_documents=search_documents,
        source_hashes=source_hashes,
        previous_manifest=previous_manifest,
        audit_hashes=audit_hashes,
        privacy_gate=gate,
        project_articles=articles,
        project_evidence=evidence_by_project,
        project_system_maps=system_maps,
    )


def _project_search_documents(
    project: PublicProject,
    article: ProjectArticle | None,
) -> tuple[SearchDocument, ...]:
    documents = [
        SearchDocument(
            document_id=f"project:{project.project_id}",
            project_id=project.project_id,
            title=project.display_name,
            body=project.summary,
            url=f"/projects/{project.project_id}",
        )
    ]
    if article is not None:
        for section in article.sections:
            documents.append(
                SearchDocument(
                    document_id=f"article:{project.project_id}:{section.section_id}",
                    project_id=project.project_id,
                    title=section.title,
                    body=section.body,
                    url=f"/projects/{project.project_id}?tab=decisions#{section.section_id}",
                )
            )
    return tuple(documents)


def _curated_source_hash(
    project: PublicProject,
    article: ProjectArticle | None,
    evidence: tuple[EvidenceRecord, ...],
    events: tuple[ProjectEvent, ...],
    system_map: str | None,
    relations: Sequence[Mapping[str, object]],
) -> str:
    payload = {
        "article": article.to_public_dict() if article is not None else None,
        "evidence": [item.to_public_dict() for item in evidence],
        "events": [
            {
                "context": event.context,
                "date": event.date,
                "decision": event.decision,
                "event_id": event.event_id,
                "outcome": event.outcome,
                "stage": event.stage,
                "title": event.title,
            }
            for event in events
        ],
        "project": project.to_dict(),
        "relations": list(relations),
        "system_map": system_map,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _service_root(workspace: Path, runtime_config: Mapping[str, object]) -> Path:
    configured = runtime_config.get("service_root", "portfolio-homepage")
    if not isinstance(configured, str) or not configured:
        raise ConfigError("/service-root")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = workspace / path
    if not path.exists() or not path.is_dir():
        raise ConfigError("/service-root")
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ConfigError("/service-root") from None
    return resolved


def _privacy_gate(
    workspace: Path,
    runtime_config: Mapping[str, object],
    *,
    ephemeral: bool,
) -> PrivacyGate:
    key = _runtime_alias_key(workspace, runtime_config)
    if key is None:
        if not ephemeral:
            raise ConfigError("/alias-key")
        key = secrets.token_bytes(32)
    elif not ephemeral and len(key) < MIN_ALIAS_KEY_BYTES:
        raise ConfigError("/alias-key")
    return PrivacyGate(alias_key=key)


def _runtime_alias_key(
    workspace: Path,
    runtime_config: Mapping[str, object],
) -> bytes | None:
    direct = os.environ.get("PROJECT_ATLAS_HMAC_KEY")
    if direct:
        return direct.encode("utf-8")
    configured: object = os.environ.get("PROJECT_ATLAS_HMAC_KEY_PATH")
    if not configured:
        configured = runtime_config.get("alias_key_file") or runtime_config.get("hmac_key_path")
    if configured is None:
        return None
    if not isinstance(configured, str) or not configured:
        raise ConfigError("/alias-key")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = workspace / path
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ConfigError("/alias-key")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise ConfigError("/alias-key")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            key = source.read().rstrip(b"\r\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not key:
        raise ConfigError("/alias-key")
    return key


def _load_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _emit_error(category: str, pointer: str) -> None:
    payload = {"error": {"category": category, "pointer": pointer}}
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")), file=sys.stderr)


def _privacy_error_category(error: PrivacyViolation) -> str:
    values = re.findall(r"[a-z][a-z0-9_]*", str(error).casefold())
    ignored = {"public", "bundle", "blocked"}
    return next((value for value in values if value not in ignored), "privacy")


def _validation_pointer(error: BaseException) -> str:
    match = re.match(r"Schema validation failed at ([^:]+):", str(error))
    if match is None or not _SAFE_ERROR_COMPONENT.fullmatch(match.group(1)):
        return "$"
    value = match.group(1)
    if value == "$":
        return "$"
    return "/" + value.replace(".", "/")
