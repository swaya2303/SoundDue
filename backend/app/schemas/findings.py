"""
backend/app/schemas/findings.py
================================
Pydantic v2 models for the *output* side of SoundDue:
evidence, rule traces, findings, and review decisions.

These are produced by the MeTTa rule engine and presented to the human
reviewer.  They are never used to assert payment claims or ownership outcomes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .inputs import SourceRef


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
class Evidence(BaseModel):
    """
    A collection of source references and raw values that support (or
    contradict) a finding.  Every field in a finding must be traceable to at
    least one ``SourceRef``.
    """

    model_config = ConfigDict(frozen=True)

    sources: list[SourceRef] = Field(
        ...,
        min_length=1,
        description="One or more source references that this evidence draws from.",
    )
    field_values: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Key/value pairs extracted from the source rows that are directly "
            "relevant to the finding (e.g. {'total_share_pct': '80.0000'})."
        ),
    )
    notes: str | None = Field(
        None,
        description="Optional free-text annotation added during ingestion or matching.",
    )


# ---------------------------------------------------------------------------
# RuleTrace
# ---------------------------------------------------------------------------
class RuleTrace(BaseModel):
    """
    A full audit trail for a single rule evaluation.

    Every finding produced by the MeTTa engine carries exactly one
    ``RuleTrace`` so that the human reviewer can see *why* the rule fired,
    which records it examined, and what information was absent or conflicting.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(
        ...,
        description="Stable identifier for the rule, e.g. 'RULE-001'.",
    )
    rule_version: str = Field(
        ...,
        description="Semantic version of the rule definition, e.g. '1.0'.",
    )
    matched_conditions: list[str] = Field(
        default_factory=list,
        description=(
            "Human-readable description of each condition that matched and "
            "caused this rule to fire."
        ),
    )
    supporting_record_ids: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of the specific records (recordings, works, claims, mappings) "
            "that were examined by this rule evaluation."
        ),
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description=(
            "Information the rule expected but did not find in the supplied "
            "records.  Described as 'missing from the supplied records', never "
            "assumed to be 'unclaimed' unless the source explicitly says so."
        ),
    )
    conflicting_information: list[str] = Field(
        default_factory=list,
        description=(
            "Pairs or groups of values that contradict each other across the "
            "supplied records, e.g. two claims that together exceed 100%."
        ),
    )

    @field_validator("rule_id", "rule_version", mode="before")
    @classmethod
    def nonempty(cls, v: Any) -> str:
        s = str(v).strip() if v is not None else ""
        if not s:
            raise ValueError("rule_id and rule_version must not be empty.")
        return s


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------
class Finding(BaseModel):
    """
    A single reconciliation finding produced by the rule engine.

    A finding describes an issue that a human reviewer must assess.  It
    never asserts an ownership outcome, never implies that any amount is
    owed, and never decides a dispute.
    """

    model_config = ConfigDict(frozen=True)

    type: str = Field(
        ...,
        description=(
            "Category of finding, e.g. 'share_gap', 'missing_isrc', "
            "'no_work_link', 'incompatible_comparison'."
        ),
    )
    issue: str = Field(
        ...,
        description="One-sentence description of the problem found.",
    )
    evidence: Evidence = Field(
        ...,
        description="All source references and field values supporting this finding.",
    )
    rule_trace: RuleTrace = Field(
        ...,
        description="Full audit trail from the rule that produced this finding.",
    )
    uncertainty: str = Field(
        ...,
        description=(
            "Explanation of what is unknown or ambiguous.  Must not imply "
            "that any share is definitively unclaimed unless the source says so."
        ),
    )
    next_step: str = Field(
        ...,
        description="Recommended action for the human reviewer.",
    )
    status: Literal["open", "resolved", "rejected"] = Field(
        "open",
        description="Lifecycle status set by the reviewer.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this finding was generated.",
    )

    @field_validator("type", "issue", "uncertainty", "next_step", mode="before")
    @classmethod
    def nonempty(cls, v: Any) -> str:
        s = str(v).strip() if v is not None else ""
        if not s:
            raise ValueError("Finding text fields must not be empty.")
        return s


# ---------------------------------------------------------------------------
# ReviewDecision
# ---------------------------------------------------------------------------
class ReviewDecision(BaseModel):
    """
    A human reviewer's decision on a finding or match candidate.

    Decisions are append-only: a correction creates a new ``ReviewDecision``
    record, it does not overwrite the original finding or previous decisions.
    Rejected matches stay rejected on re-run (the engine checks this table).
    """

    model_config = ConfigDict(frozen=True)

    target: str = Field(
        ...,
        description=(
            "Identifier of the finding or match candidate being reviewed, "
            "e.g. 'finding:7' or 'candidate:3'."
        ),
    )
    decision: Literal["accept", "reject", "correct"] = Field(
        ...,
        description=(
            "'accept' — reviewer agrees the finding is valid.\n"
            "'reject' — reviewer dismisses the finding (stays rejected on re-run).\n"
            "'correct' — reviewer supplies corrected values via corrected_values."
        ),
    )
    actor: str = Field(
        ...,
        description="Identifier of the person or system making this decision.",
    )
    note: str | None = Field(
        None,
        description="Optional free-text explanation from the reviewer.",
    )
    corrected_values: dict[str, Any] | None = Field(
        None,
        description=(
            "If decision='correct', the reviewer's corrected field values.  "
            "These create a new record version; the original is preserved."
        ),
    )
    decided_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of this decision.",
    )

    @field_validator("target", "actor", mode="before")
    @classmethod
    def nonempty(cls, v: Any) -> str:
        s = str(v).strip() if v is not None else ""
        if not s:
            raise ValueError("target and actor must not be empty.")
        return s
