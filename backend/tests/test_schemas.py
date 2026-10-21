"""
tests/test_schemas.py
=====================
Unit tests for backend/app/schemas — validation of inputs and findings models.

Covers:
  - Bad / empty IDs
  - Share out of range (zero, negative, >100)
  - Share passed as float (should be accepted and converted to Decimal)
  - Share that cannot be parsed at all
  - Date range where effective_to < effective_from
  - Status vocabulary enforcement
  - ISRC / ISWC pattern enforcement
  - Mapping ID validation
  - Evidence must have at least one SourceRef
  - RuleTrace empty id/version rejected
  - Finding empty text fields rejected
  - ReviewDecision decision vocabulary + empty actor rejected
  - Happy-path round-trips for every model
"""

from __future__ import annotations

import sys
import os
from datetime import date, datetime
from decimal import Decimal

import pytest

# Make backend/ importable when running from backend/ or repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas import (
    Evidence,
    Finding,
    Mapping,
    OwnershipClaim,
    RecordingRow,
    ReviewDecision,
    RuleTrace,
    SourceRef,
    WorkRow,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _src(**kwargs) -> SourceRef:
    defaults = dict(file_name="test.csv", row_number=1, raw_values={})
    return SourceRef(**(defaults | kwargs))


def _claim(**kwargs) -> OwnershipClaim:
    defaults = dict(
        work_id="W-001",
        contributor_id="C-001",
        contributor_name="Alice",
        share=Decimal("50.00"),
        share_convention="publisher-share",
        rights_category="mechanical",
        territory="WW",
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        status="claimed",
        source=_src(),
    )
    return OwnershipClaim(**(defaults | kwargs))


def _rule_trace(**kwargs) -> RuleTrace:
    defaults = dict(rule_id="RULE-001", rule_version="1.0")
    return RuleTrace(**(defaults | kwargs))


def _evidence(**kwargs) -> Evidence:
    defaults = dict(sources=[_src()])
    return Evidence(**(defaults | kwargs))


def _finding(**kwargs) -> Finding:
    defaults = dict(
        type="share_gap",
        issue="Shares sum to 80%, not 100%.",
        evidence=_evidence(),
        rule_trace=_rule_trace(),
        uncertainty="Gap may reflect missing claims in supplied records.",
        next_step="Obtain share schedules from all rights holders.",
        status="open",
    )
    return Finding(**(defaults | kwargs))


# ===========================================================================
# SourceRef
# ===========================================================================
class TestSourceRef:
    def test_happy_path(self):
        s = _src(file_name="recordings.csv", row_number=5, raw_values={"isrc": "USRC001"})
        assert s.file_name == "recordings.csv"
        assert s.row_number == 5

    def test_row_number_must_be_positive(self):
        with pytest.raises(Exception):
            _src(row_number=0)


# ===========================================================================
# RecordingRow
# ===========================================================================
class TestRecordingRow:
    def test_happy_path(self):
        r = RecordingRow(
            recording_id="REC-001",
            title="Shape of You",
            performer="Ed Sheeran",
            version="Radio Edit",
            duration_seconds=234,
            isrc="USRC17607839",
            source=_src(),
        )
        assert r.recording_id == "REC-001"
        assert r.isrc == "USRC17607839"

    def test_empty_recording_id_rejected(self):
        with pytest.raises(Exception, match="recording_id"):
            RecordingRow(recording_id="", title="Track", source=_src())

    def test_whitespace_recording_id_rejected(self):
        with pytest.raises(Exception, match="recording_id"):
            RecordingRow(recording_id="   ", title="Track", source=_src())

    def test_empty_title_rejected(self):
        with pytest.raises(Exception, match="title"):
            RecordingRow(recording_id="REC-001", title="", source=_src())

    def test_invalid_isrc_pattern(self):
        with pytest.raises(Exception):
            RecordingRow(
                recording_id="REC-001",
                title="Track",
                isrc="BADISRC",
                source=_src(),
            )

    def test_valid_isrc_accepted(self):
        r = RecordingRow(
            recording_id="R1", title="T", isrc="GBAYE0601477", source=_src()
        )
        assert r.isrc == "GBAYE0601477"

    def test_optional_fields_default_none(self):
        r = RecordingRow(recording_id="R1", title="T", source=_src())
        assert r.performer is None
        assert r.version is None
        assert r.duration_seconds is None
        assert r.isrc is None


# ===========================================================================
# WorkRow
# ===========================================================================
class TestWorkRow:
    def test_happy_path(self):
        w = WorkRow(
            work_id="W-001",
            title="Shape of You",
            writers=["Ed Sheeran"],
            iswc="T-034524680-1",
            source=_src(),
        )
        assert w.work_id == "W-001"
        assert w.iswc == "T-034524680-1"

    def test_empty_work_id_rejected(self):
        with pytest.raises(Exception, match="work_id"):
            WorkRow(work_id="", title="Song", source=_src())

    def test_empty_title_rejected(self):
        with pytest.raises(Exception, match="title"):
            WorkRow(work_id="W-1", title="  ", source=_src())

    def test_invalid_iswc_pattern(self):
        with pytest.raises(Exception):
            WorkRow(work_id="W-1", title="T", iswc="BADISWC", source=_src())

    def test_writers_as_csv_string(self):
        """A comma-separated string should be split into a list."""
        w = WorkRow(work_id="W-1", title="T", writers="Alice, Bob, Carol", source=_src())
        assert w.writers == ["Alice", "Bob", "Carol"]

    def test_writers_default_empty(self):
        w = WorkRow(work_id="W-1", title="T", source=_src())
        assert w.writers == []


# ===========================================================================
# Mapping
# ===========================================================================
class TestMapping:
    def test_happy_path(self):
        m = Mapping(
            recording_id="REC-001",
            work_id="W-001",
            source=_src(),
            source_label="Sony",
            verified=True,
        )
        assert m.verified is True

    def test_empty_recording_id_rejected(self):
        with pytest.raises(Exception):
            Mapping(recording_id="", work_id="W-1", source=_src())

    def test_empty_work_id_rejected(self):
        with pytest.raises(Exception):
            Mapping(recording_id="R-1", work_id="", source=_src())

    def test_verified_defaults_false(self):
        m = Mapping(recording_id="R1", work_id="W1", source=_src())
        assert m.verified is False


# ===========================================================================
# OwnershipClaim — share validation
# ===========================================================================
class TestOwnershipClaimShare:
    def test_happy_path_decimal_string(self):
        c = _claim(share="33.3333")
        assert c.share == Decimal("33.3333")

    def test_share_as_int_accepted(self):
        c = _claim(share=50)
        assert c.share == Decimal("50")

    def test_share_as_float_coerced_to_decimal(self):
        """Floats are accepted but stored as Decimal."""
        c = _claim(share=33.33)
        assert isinstance(c.share, Decimal)

    def test_share_zero_rejected(self):
        with pytest.raises(Exception, match="share must be"):
            _claim(share=Decimal("0"))

    def test_share_negative_rejected(self):
        with pytest.raises(Exception, match="share must be"):
            _claim(share=Decimal("-1"))

    def test_share_over_100_rejected(self):
        with pytest.raises(Exception, match="share must be"):
            _claim(share=Decimal("100.0001"))

    def test_share_exactly_100_accepted(self):
        c = _claim(share=Decimal("100"))
        assert c.share == Decimal("100")

    def test_share_non_numeric_string_rejected(self):
        with pytest.raises(Exception):
            _claim(share="fifty")


# ===========================================================================
# OwnershipClaim — date validation
# ===========================================================================
class TestOwnershipClaimDates:
    def test_valid_date_range(self):
        c = _claim(
            effective_from=date(2020, 1, 1),
            effective_to=date(2025, 12, 31),
        )
        assert c.effective_to > c.effective_from

    def test_same_day_accepted(self):
        d = date(2023, 6, 1)
        c = _claim(effective_from=d, effective_to=d)
        assert c.effective_from == c.effective_to

    def test_end_before_start_rejected(self):
        with pytest.raises(Exception, match="effective_to"):
            _claim(
                effective_from=date(2025, 1, 1),
                effective_to=date(2020, 12, 31),
            )


# ===========================================================================
# OwnershipClaim — status validation
# ===========================================================================
class TestOwnershipClaimStatus:
    @pytest.mark.parametrize("s", ["claimed", "unclaimed", "disputed", "pending", "unknown"])
    def test_valid_statuses(self, s: str):
        c = _claim(status=s)
        assert c.status == s

    def test_status_case_insensitive(self):
        """Uppercase input should be lowercased and accepted."""
        c = _claim(status="CLAIMED")
        assert c.status == "claimed"

    def test_invalid_status_rejected(self):
        with pytest.raises(Exception, match="status must be one of"):
            _claim(status="approved")


# ===========================================================================
# OwnershipClaim — ID validation
# ===========================================================================
class TestOwnershipClaimIds:
    def test_empty_work_id_rejected(self):
        with pytest.raises(Exception):
            _claim(work_id="")

    def test_whitespace_contributor_id_rejected(self):
        with pytest.raises(Exception):
            _claim(contributor_id="   ")

    def test_empty_contributor_name_rejected(self):
        with pytest.raises(Exception, match="contributor_name"):
            _claim(contributor_name="")


# ===========================================================================
# Evidence
# ===========================================================================
class TestEvidence:
    def test_happy_path(self):
        e = _evidence(field_values={"total_pct": "80.0"}, notes="Gap of 20%")
        assert e.field_values["total_pct"] == "80.0"
        assert e.notes == "Gap of 20%"

    def test_at_least_one_source_required(self):
        with pytest.raises(Exception):
            Evidence(sources=[])


# ===========================================================================
# RuleTrace
# ===========================================================================
class TestRuleTrace:
    def test_happy_path(self):
        rt = _rule_trace(
            matched_conditions=["share_sum < 99.99"],
            supporting_record_ids=["claim:3", "claim:4"],
            missing_information=["share schedule from Warner"],
        )
        assert rt.rule_id == "RULE-001"
        assert len(rt.matched_conditions) == 1

    def test_empty_rule_id_rejected(self):
        with pytest.raises(Exception):
            RuleTrace(rule_id="", rule_version="1.0")

    def test_empty_rule_version_rejected(self):
        with pytest.raises(Exception):
            RuleTrace(rule_id="RULE-001", rule_version="  ")


# ===========================================================================
# Finding
# ===========================================================================
class TestFinding:
    def test_happy_path(self):
        f = _finding()
        assert f.status == "open"
        assert isinstance(f.created_at, datetime)

    def test_empty_issue_rejected(self):
        with pytest.raises(Exception):
            _finding(issue="")

    def test_empty_type_rejected(self):
        with pytest.raises(Exception):
            _finding(type="   ")

    def test_valid_statuses(self):
        for s in ("open", "resolved", "rejected"):
            f = _finding(status=s)
            assert f.status == s

    def test_invalid_status_rejected(self):
        with pytest.raises(Exception):
            _finding(status="closed")


# ===========================================================================
# ReviewDecision
# ===========================================================================
class TestReviewDecision:
    def test_accept(self):
        rd = ReviewDecision(
            target="finding:1",
            decision="accept",
            actor="demo-user",
            note="Verified against CMO records.",
        )
        assert rd.decision == "accept"

    def test_reject(self):
        rd = ReviewDecision(target="finding:2", decision="reject", actor="demo-user")
        assert rd.decision == "reject"
        assert rd.corrected_values is None

    def test_correct_with_values(self):
        rd = ReviewDecision(
            target="candidate:3",
            decision="correct",
            actor="demo-user",
            corrected_values={"share": "50.0000"},
        )
        assert rd.corrected_values["share"] == "50.0000"

    def test_invalid_decision_rejected(self):
        with pytest.raises(Exception):
            ReviewDecision(target="finding:1", decision="approve", actor="demo-user")

    def test_empty_actor_rejected(self):
        with pytest.raises(Exception):
            ReviewDecision(target="finding:1", decision="accept", actor="")

    def test_empty_target_rejected(self):
        with pytest.raises(Exception):
            ReviewDecision(target="", decision="accept", actor="demo-user")
