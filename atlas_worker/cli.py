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
import sys
import tempfile
from typing import Any

import yaml
from yaml.error import YAMLError

from .backfill import (
    classify_backfill_claims,
    extract_signal_claims,
    should_skip_session,
    updated_cursors,
)
from .bundle import (
    BundleContext,
    SearchDocument,
    build_candidate_bundle,
    promote_bundle,
    validate_bundle,
)
from .config import DiscoveryConfig
from .discovery import discover_projects
from .evidence import merge_claims
from .graph import build_graph
from .manifest import require_no_symlink_path
from .memory import load_project_memory
from .memory_writer import update_project_memory
from .models import (
    DiscoveryReport,
    EvidenceClaim,
    ProjectMemory,
    ProjectRef,
    PublicProject,
    TagSet,
    validate_schema,
)
from .privacy import PrivacyGate, PrivacyViolation
from .sessions import iter_session_events, map_session


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_PRIVACY = 3
EXIT_IO = 4

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
        for path, content, _ in writes:
            _atomic_write_text(path, content)
    return {
        "ambiguous": list(ambiguous),
        "dry_run": bool(args.dry_run),
        "written": [] if args.dry_run else [relative for _, _, relative in writes],
        "would_write": [relative for _, _, relative in writes] if args.dry_run else [],
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
    report = _discover(workspace, config)
    gate = _privacy_gate(workspace, config, ephemeral=bool(args.dry_run))
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
    report = _discover(workspace, config)
    gate = _privacy_gate(workspace, config, ephemeral=bool(args.dry_run))
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

    build = _execute_build(workspace, config, report, gate, dry_run=bool(args.dry_run))
    return {
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


def _workspace(value: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.exists() or not candidate.is_dir():
        raise ConfigError("/workspace")
    return candidate.resolve()


def _load_runtime_config(workspace: Path) -> dict[str, object]:
    path = workspace / ".knowledge-worker" / "config.yaml"
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ConfigError("/runtime-config")
    return dict(value)


def _discover(workspace: Path, runtime_config: Mapping[str, object]) -> DiscoveryReport:
    registered = runtime_config.get("registered_assets", ())
    if registered is None:
        registered = ()
    if not isinstance(registered, (list, tuple)) or any(not isinstance(item, str) for item in registered):
        raise ConfigError("/registered-assets")
    config = DiscoveryConfig.for_workspace(
        workspace,
        registered_assets=tuple(Path(item) for item in registered),
    )
    return discover_projects(config)


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
) -> tuple[tuple[Path, str, str], ...]:
    targets = {ref.project_id: ref for ref in report.ambiguous}
    seen: set[str] = set()
    writes: list[tuple[Path, str, str]] = []
    for profile in profiles:
        validate_schema(profile, "project-profile")
        project_id = profile.get("id")
        if not isinstance(project_id, str) or project_id in seen or project_id not in targets:
            raise ConfigError("/profiles/id")
        seen.add(project_id)
        ref = targets[project_id]
        if profile.get("lifecycle") != ref.lifecycle or not ref.root.is_dir():
            raise ConfigError("/profiles/lifecycle")
        _validate_profile_aliases(profile.get("aliases", ()))
        ordered = {key: profile[key] for key in _PROFILE_KEYS if key in profile}
        content = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False)
        path = ref.root / "project_memory" / "project-profile.yaml"
        require_no_symlink_path(path)
        if path.exists():
            raise ConfigError("/profiles/id")
        relative = path.relative_to(workspace).as_posix()
        writes.append((path, content, relative))
    return tuple(sorted(writes, key=lambda item: item[2]))


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
    cursor_path = workspace / ".knowledge-worker" / "session-cursor.json"
    require_no_symlink_path(cursor_path)
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
    if selected:
        refs = {ref.project_id: ref for ref in discovery.projects}
        grouped: dict[str, list[EvidenceClaim]] = defaultdict(list)
        for project_id, claim in selected:
            grouped[project_id].append(claim)
        for project_id in sorted(grouped):
            knowledge = merge_claims(grouped[project_id])
            update = update_project_memory(refs[project_id], knowledge, dry_run=dry_run)
            applied_claims += len(grouped[project_id])
            applied_files += len(update.changed_files)
            applied_projects += 1

    cursor_written = False
    if not dry_run and reviewed_report is not None:
        next_cursors = updated_cursors(paths, cursors)
        cursor_written = _atomic_write_json(cursor_path, next_cursors)

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
    for path in paths:
        for event in iter_session_events(path):
            if event.parse_error:
                parse_errors += 1
                continue
            if map_session(event, projects, aliases) is None:
                unmapped_events += 1
            else:
                mapped_events += 1

    claims: list[tuple[str, EvidenceClaim]] = []
    for project in projects:
        def project_events():
            for session_path in paths:
                for event in iter_session_events(session_path):
                    if not event.parse_error and map_session(event, projects, aliases) == project.project_id:
                        yield event

        claims.extend((project.project_id, claim) for claim in extract_signal_claims(project_events()))
    return {
        "claims": tuple(claims),
        "mapped_events": mapped_events,
        "parse_errors": parse_errors,
        "unmapped_events": unmapped_events,
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
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
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
) -> dict[str, object]:
    service_root = _service_root(workspace, runtime_config)
    context = _bundle_context(discovery, gate)
    public_dir = service_root / "public-bundle"
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
    return {
        "changed": changed,
        "changed_projects": changed_projects,
        "dry_run": dry_run,
        "projects": list(manifest.projects),
        "validated": True,
        "version": validated.version,
    }


def _bundle_context(discovery: DiscoveryReport, gate: PrivacyGate) -> BundleContext:
    ambiguous_ids = {ref.project_id for ref in discovery.ambiguous}
    projects: list[PublicProject] = []
    memories: dict[str, ProjectMemory] = {}
    source_hashes: dict[str, str] = {}
    for ref in discovery.projects:
        if ref.publication != "public" or ref.project_id in ambiguous_ids:
            continue
        memory = load_project_memory(ref)
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
        source_hashes[ref.project_id] = _curated_source_hash(project, memory)

    ordered = tuple(sorted(projects, key=lambda project: project.project_id))
    graph = build_graph(ordered)
    search_documents = tuple(
        SearchDocument(
            document_id=f"project:{project.project_id}",
            project_id=project.project_id,
            title=project.display_name,
            body=project.summary,
            url=f"/projects/{project.project_id}",
        )
        for project in ordered
    )
    return BundleContext(
        projects=ordered,
        project_memories=memories,
        project_events={},
        graph=graph,
        search_documents=search_documents,
        source_hashes=source_hashes,
        previous_manifest=None,
        privacy_gate=gate,
    )


def _curated_source_hash(project: PublicProject, memory: ProjectMemory) -> str:
    payload = {
        "build_story": list(memory.build_story),
        "decisions": list(memory.decisions),
        "project": project.to_dict(),
        "rollbacks": list(memory.rollbacks),
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
    key = path.read_bytes()
    if not key:
        raise ConfigError("/alias-key")
    return key


def _load_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, value: object) -> bool:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> bool:
    encoded = content.encode("utf-8")
    require_no_symlink_path(path)
    if path.is_file() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return True


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
