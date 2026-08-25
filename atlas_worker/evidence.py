"""Evidence precedence rules for Project Atlas knowledge."""

from collections import defaultdict
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Iterable

from .models import EvidenceClaim, ProjectKnowledge


SOURCE_PRIORITY = {
    "session": 10,
    "source": 20,
    "git": 30,
    "project_memory": 40,
    "profile": 50,
}


def merge_claims(claims: Iterable[EvidenceClaim]) -> ProjectKnowledge:
    """Select one deterministic, highest-precedence claim for every field."""
    grouped: dict[str, list[EvidenceClaim]] = defaultdict(list)
    for claim in claims:
        if claim.source_class not in SOURCE_PRIORITY:
            raise ValueError(f"Unknown source_class: {claim.source_class}")
        if _is_absolute_path_value(claim.value):
            raise ValueError(f"Absolute path value is not allowed for field: {claim.field}")
        grouped[claim.field].append(claim)

    values: dict[str, object] = {}
    winners: dict[str, EvidenceClaim] = {}
    for field, options in grouped.items():
        winner = max(
            options,
            key=lambda item: (
                SOURCE_PRIORITY[item.source_class],
                item.confidence,
                item.evidence_id,
            ),
        )
        values[field] = winner.value
        winners[field] = winner
    return ProjectKnowledge(values=values, winners=winners)


def _is_absolute_path_value(value: object) -> bool:
    if isinstance(value, PurePath):
        candidate = str(value)
        return (
            value.is_absolute()
            or PurePosixPath(candidate).is_absolute()
            or PureWindowsPath(candidate).is_absolute()
        )
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    return PurePosixPath(candidate).is_absolute() or PureWindowsPath(candidate).is_absolute()
