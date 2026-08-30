#!/usr/bin/env python3
"""Audit Project Atlas instruction routing without copying global policy."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Sequence


CHECKPOINT_HEADING = "## Project Atlas Meaningful-Work Checkpoint"
VALID_GLOBAL_CHECKPOINT = """## Project Atlas Meaningful-Work Checkpoint

- After substantive work in a project with `project_memory/project-profile.yaml`, decide whether it established a durable product decision, difficult revision, rollback, architecture boundary, or verified outcome.
- When it did, merge the fact into `project_memory/project-atlas/article.yaml` and `evidence.yaml`; initialize that directory only when material evidence exists or the user explicitly asks.
- Keep projects independent. A predecessor or direct project relation requires explicit documentary, Git, session, or curated-memory evidence.
- Add an SVG only for a specific structure, state transition, or data lifetime that prose alone does not explain. Never create generic problem-decision-result diagrams.
- Exclude routine commands, raw transcripts, secrets, absolute paths, one-off discussion, and unsupported conclusions.
- Audit the changed project. Keep conflicting claims in local review state and do not overwrite validated public prose.
"""
VALID_WORKSPACE_POINTER = """## Project Atlas Memory Checkpoint

- Apply the canonical `Project Atlas Meaningful-Work Checkpoint` from `~/.codex/AGENTS.md` to profiled projects in this workspace.
- Workspace-specific paths and publication tooling remain defined in this repository; do not copy the global checkpoint here.
"""
VALID_ADAPTER_POINTER = """## Project Atlas Memory Checkpoint

- Before following the workspace reference order, apply the canonical `Project Atlas Meaningful-Work Checkpoint` from `~/.codex/AGENTS.md`.
- This adapter defines reference order only and does not duplicate the global checkpoint.
"""

_REQUIRED_GLOBAL_FRAGMENTS = (
    CHECKPOINT_HEADING,
    "project_memory/project-profile.yaml",
    "durable product decision",
    "project_memory/project-atlas/article.yaml",
    "Keep projects independent.",
    "Never create generic problem-decision-result diagrams.",
    "Exclude routine commands, raw transcripts, secrets, absolute paths",
    "Audit the changed project.",
    "conflicting claims in local review state",
)
_POINTER_FRAGMENT = "canonical `Project Atlas Meaningful-Work Checkpoint` from `~/.codex/AGENTS.md`"
_GLOBAL_POLICY_MARKERS = (
    "durable product decision",
    "Never create generic problem-decision-result diagrams.",
    "conflicting claims in local review state",
)


@dataclass(frozen=True)
class Finding:
    code: str
    role: str


def audit_checkpoint(
    global_path: Path,
    workspace_path: Path,
    adapter_path: Path,
) -> tuple[Finding, ...]:
    global_text = _read(global_path)
    workspace_text = _read(workspace_path)
    adapter_text = _read(adapter_path)
    findings: list[Finding] = []

    if CHECKPOINT_HEADING not in global_text:
        findings.append(Finding("missing-project-atlas-checkpoint", "global"))
    elif any(fragment not in global_text for fragment in _REQUIRED_GLOBAL_FRAGMENTS):
        findings.append(Finding("incomplete-project-atlas-checkpoint", "global"))

    findings.extend(_pointer_findings(workspace_text, "workspace"))
    findings.extend(_pointer_findings(adapter_text, "adapter"))
    return tuple(findings)


def _pointer_findings(text: str, role: str) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if _POINTER_FRAGMENT not in text:
        findings.append(Finding(f"missing-{role}-checkpoint-pointer", role))
    if CHECKPOINT_HEADING in text or any(marker in text for marker in _GLOBAL_POLICY_MARKERS):
        findings.append(Finding("duplicated-global-checkpoint", role))
    return tuple(findings)


def _read(path: Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--global-path", type=Path, required=True)
    parser.add_argument("--workspace-path", type=Path, required=True)
    parser.add_argument("--adapter-path", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings = audit_checkpoint(args.global_path, args.workspace_path, args.adapter_path)
    print(json.dumps({"findings": [asdict(item) for item in findings]}, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
