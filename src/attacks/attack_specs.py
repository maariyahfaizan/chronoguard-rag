"""Definitions and validation rules for Week-5 temporal poisoning attacks.

This module defines the attack conditions only. It does not modify data,
generate poisoned pools, or run retrieval/generation experiments.
"""

from dataclasses import dataclass
from typing import Literal


AttackType = Literal[
    "stale_evidence",
    "fabricated_fresh",
    "future_date",
    "duplicate_fresh",
    "correct_content_wrong_date",
]


@dataclass(frozen=True)
class AttackSpec:
    """Specification for one controlled temporal poisoning condition."""

    name: AttackType
    description: str
    requires_replacement_text: bool
    requires_timestamp_shift: bool
    requires_duplicate: bool


ATTACK_SPECS = {
    "stale_evidence": AttackSpec(
        name="stale_evidence",
        description=(
            "Insert or amplify older evidence that is topically relevant "
            "but obsolete at the query reference time."
        ),
        requires_replacement_text=True,
        requires_timestamp_shift=False,
        requires_duplicate=False,
    ),
    "fabricated_fresh": AttackSpec(
        name="fabricated_fresh",
        description=(
            "Insert controlled false evidence presented as newer or fresher "
            "than the valid evidence."
        ),
        requires_replacement_text=True,
        requires_timestamp_shift=True,
        requires_duplicate=False,
    ),
    "future_date": AttackSpec(
        name="future_date",
        description=(
            "Shift an otherwise plausible evidence timestamp so that the "
            "passage appears newer than it should be."
        ),
        requires_replacement_text=False,
        requires_timestamp_shift=True,
        requires_duplicate=False,
    ),
    "duplicate_fresh": AttackSpec(
        name="duplicate_fresh",
        description=(
            "Insert repeated or near-duplicate temporally attractive "
            "evidence to test redundancy effects on retrieval and generation."
        ),
        requires_replacement_text=True,
        requires_timestamp_shift=False,
        requires_duplicate=True,
    ),
    "correct_content_wrong_date": AttackSpec(
        name="correct_content_wrong_date",
        description=(
            "Keep the evidence content correct while deliberately assigning "
            "an incorrect timestamp, isolating timestamp sensitivity from "
            "content falsification."
        ),
        requires_replacement_text=False,
        requires_timestamp_shift=True,
        requires_duplicate=False,
    ),
}


def get_attack_spec(attack_type: AttackType) -> AttackSpec:
    """Return the specification for a supported attack type."""
    try:
        return ATTACK_SPECS[attack_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported attack type: {attack_type!r}. "
            f"Supported types: {sorted(ATTACK_SPECS)}"
        ) from exc


def validate_attack_type(attack_type: str) -> None:
    """Raise ValueError if attack_type is not supported."""
    get_attack_spec(attack_type)  # type: ignore[arg-type]