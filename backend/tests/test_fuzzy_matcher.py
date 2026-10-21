"""
tests/test_fuzzy_matcher.py
============================
Tests for app.fuzzy_matcher.propose_fuzzy_candidates.

Critical invariants tested:
  * Same title, different names, no duration → NO candidate (corroboration required)
  * Title 100% match alone → NO candidate
  * Rejected pair → never re-proposed on re-run
  * Good title + performer match → candidate proposed
  * Good title + duration match → candidate proposed
  * Version mismatch → score penalised (× 0.85)
  * Same version token on both → no penalty
  * field_scores dict has title / name / duration keys
  * reasons list is human-readable strings

DB isolation: unique shared-cache in-memory SQLite URI.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.fuzzy_matcher import (
    VERSION_TOKENS,
    _NAME_CORROBORATION_THRESHOLD,
    _extract_version_tokens,
    _duration_score,
    _title_score,
    propose_fuzzy_candidates,
)
from app.models import Base, MatchCandidate, Record
from app.normaliser import NormalisedRow

# ---------------------------------------------------------------------------
# DB Setup
# ---------------------------------------------------------------------------

_engine = create_engine(
    "sqlite:///file:sounddue_fuzzytest?mode=memory&cache=shared&uri=true",
    connect_args={"check_same_thread": False},
)
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


def _db():
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_record(db, case_id: int, record_type: str, normalised: dict) -> Record:
    rec = Record(
        case_id=case_id,
        record_type=record_type,
        normalised_json=normalised,
        raw_json={},
        source_file_id=None,
        source_row=1,
        version=1,
    )
    db.add(rec)
    db.flush()
    return rec


def _nr(record: Record, normalised: dict) -> NormalisedRow:
    return NormalisedRow(
        normalised=normalised,
        raw={},
        comparison_keys={},
        source_ref={"record_id": record.id},
    )


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_extract_version_tokens_live(self):
        assert "live" in _extract_version_tokens("Golden Hour (Live)")

    def test_extract_version_tokens_remix(self):
        assert "remix" in _extract_version_tokens("Track (Remix)")

    def test_extract_version_tokens_empty(self):
        assert _extract_version_tokens("Studio Album") == frozenset()

    def test_title_score_exact(self):
        assert _title_score("Golden Hour", "Golden Hour") == 1.0

    def test_title_score_partial(self):
        s = _title_score("Midnight Train", "Midnight Train (Edit)")
        assert 0.7 < s < 1.0

    def test_duration_score_within_3s(self):
        score, reason = _duration_score("195", "197")
        assert score == 1.0
        assert "apart" in reason

    def test_duration_score_exactly_3s(self):
        score, reason = _duration_score("200", "203")
        assert score == 1.0

    def test_duration_score_missing(self):
        score, reason = _duration_score(None, "200")
        assert score == 0.0
        assert "unknown" in reason

    def test_duration_score_beyond_30s(self):
        score, reason = _duration_score("100", "200")
        assert score == 0.0
        assert "too different" in reason

    def test_duration_score_linear_midpoint(self):
        # at diff=16.5s (midpoint of 3–30) → ~0.75
        score, _ = _duration_score("100", "116.5")
        assert 0.6 < score < 0.9


# ---------------------------------------------------------------------------
# Corroboration requirement
# ---------------------------------------------------------------------------

class TestCorroborationRequired:
    """Title alone never creates a candidate — even at 100%."""

    def test_same_title_different_names_no_duration_no_candidate(self):
        """Scenario 3 equivalent: same title, different artist/writer, no duration."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {
                "recording_id": "REC-001", "title": "Golden Hour",
                "performer": "Artist X", "duration_seconds": None,
            })
            wrk = _seed_record(db, 1, "work", {
                "work_id": "WRK-001", "title": "Golden Hour",
                "writers": "Writer Y",
            })
            rec_nrows = [_nr(rec, {
                "title": "Golden Hour", "performer": "Artist X",
                "duration_seconds": None, "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Golden Hour", "writers": "Writer Y",
                "duration_seconds": None, "version": "",
            })]

            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert candidates == [], (
                "Title-only match with different names and no duration must not create a candidate"
            )
        finally:
            db.close()

    def test_perfect_title_still_needs_corroboration(self):
        """100% title match with no corroborating field → no candidate."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {"recording_id": "REC-A", "title": "Midnight Train"})
            wrk = _seed_record(db, 1, "work", {"work_id": "WRK-A", "title": "Midnight Train"})
            # No performer on recording, no writers on work, no durations
            rec_nrows = [_nr(rec, {"title": "Midnight Train", "performer": "", "duration_seconds": None, "version": ""})]
            wrk_nrows = [_nr(wrk, {"title": "Midnight Train", "writers": "", "duration_seconds": None, "version": ""})]

            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert candidates == []
        finally:
            db.close()

    def test_title_with_duration_corroboration_creates_candidate(self):
        """Title 85%+ AND duration within 3s → candidate proposed."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {"recording_id": "REC-B"})
            wrk = _seed_record(db, 1, "work", {"work_id": "WRK-B"})
            rec_nrows = [_nr(rec, {
                "title": "Midnight Train", "performer": "",
                "duration_seconds": "195", "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Midnight Train", "writers": "",
                "duration_seconds": "196", "version": "",
            })]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(candidates) == 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Good matches
# ---------------------------------------------------------------------------

class TestGoodMatchProposed:
    def test_title_and_performer_match(self):
        """High title + performer corroboration → candidate proposed."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {"recording_id": "REC-G1"})
            wrk = _seed_record(db, 1, "work", {"work_id": "WRK-G1"})
            rec_nrows = [_nr(rec, {
                "title": "Shape of You", "performer": "Ed Sheeran",
                "duration_seconds": None, "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Shape of You", "writers": "Ed Sheeran",
                "duration_seconds": None, "version": "",
            })]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(candidates) == 1
            assert candidates[0].status == "pending"
        finally:
            db.close()

    def test_status_starts_pending(self):
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {"title": "Perfect", "performer": "Ed Sheeran", "duration_seconds": "200", "version": ""})]
            wrk_nrows = [_nr(wrk, {"title": "Perfect", "writers": "Ed Sheeran", "duration_seconds": "201", "version": ""})]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert candidates[0].status == "pending"
        finally:
            db.close()

    def test_score_between_zero_and_one(self):
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {"title": "Blinding Lights", "performer": "The Weeknd", "duration_seconds": "200", "version": ""})]
            wrk_nrows = [_nr(wrk, {"title": "Blinding Lights", "writers": "The Weeknd", "duration_seconds": "200", "version": ""})]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(candidates) == 1
            assert 0.0 <= float(candidates[0].score) <= 1.0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Field scores and reasons
# ---------------------------------------------------------------------------

class TestFieldScoresAndReasons:
    def _make_candidate(self):
        db = _db()
        rec = _seed_record(db, 1, "recording", {})
        wrk = _seed_record(db, 1, "work", {})
        rec_nrows = [_nr(rec, {
            "title": "Golden Hour", "performer": "Kacey Musgraves",
            "duration_seconds": "195", "version": "",
        })]
        wrk_nrows = [_nr(wrk, {
            "title": "Golden Hour", "writers": "Kacey Musgraves",
            "duration_seconds": "196", "version": "",
        })]
        candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
        db.close()
        return candidates

    def test_field_scores_has_title_name_duration_keys(self):
        candidates = self._make_candidate()
        assert len(candidates) == 1
        fs = candidates[0].field_scores
        assert "title" in fs
        assert "name" in fs
        assert "duration" in fs

    def test_field_scores_values_in_range(self):
        candidates = self._make_candidate()
        fs = candidates[0].field_scores
        for k, v in fs.items():
            assert 0.0 <= v <= 1.0, f"{k} score {v} out of range"

    def test_reasons_is_list_of_strings(self):
        candidates = self._make_candidate()
        reasons = candidates[0].reasons
        assert isinstance(reasons, list)
        assert all(isinstance(r, str) for r in reasons)
        assert len(reasons) >= 1

    def test_reasons_contain_title_percentage(self):
        candidates = self._make_candidate()
        reasons = candidates[0].reasons
        title_reasons = [r for r in reasons if "title" in r]
        assert len(title_reasons) >= 1

    def test_reasons_contain_performer_info_when_matched(self):
        candidates = self._make_candidate()
        reasons = candidates[0].reasons
        # Should mention performer/name match
        name_reasons = [r for r in reasons if "performer" in r or "writer" in r or "exact" in r]
        assert len(name_reasons) >= 1


# ---------------------------------------------------------------------------
# Version mismatch penalty
# ---------------------------------------------------------------------------

class TestVersionMismatch:
    def test_live_vs_studio_penalised(self):
        """Recording with 'Live' version vs work without → score × 0.85."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            # Strong match otherwise (title+name+duration)
            rec_nrows = [_nr(rec, {
                "title": "Golden Hour", "performer": "Kacey Musgraves",
                "duration_seconds": "195", "version": "Live",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Golden Hour", "writers": "Kacey Musgraves",
                "duration_seconds": "196", "version": "",
            })]
            # Run without penalty reference first via same data minus version
            candidates_penalised = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(candidates_penalised) == 1
            penalised_score = float(candidates_penalised[0].score)

            # The penalised score should be lower than the unpenalised composite
            # (composite for exact title + exact name + dur≤3s ≈ 1.0 × 0.85 = 0.85)
            assert penalised_score <= 0.90, f"Expected penalised score ≤ 0.90, got {penalised_score}"

            # Reason should mention version mismatch
            assert any("mismatch" in r or "penalised" in r for r in candidates_penalised[0].reasons)
        finally:
            db.close()

    def test_same_version_token_no_penalty(self):
        """Both recording and work have 'live' → no penalty applied."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Golden Hour Live", "performer": "Kacey Musgraves",
                "duration_seconds": "195", "version": "Live",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Golden Hour Live", "writers": "Kacey Musgraves",
                "duration_seconds": "196", "version": "Live",
            })]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(candidates) == 1
            # No mismatch reason
            assert not any("mismatch" in r for r in candidates[0].reasons)
        finally:
            db.close()

    def test_version_mismatch_reason_in_list(self):
        """Version mismatch reason string is present and readable."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Golden Hour", "performer": "Kacey Musgraves",
                "duration_seconds": "195", "version": "Acoustic",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Golden Hour", "writers": "Kacey Musgraves",
                "duration_seconds": "196", "version": "",
            })]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            if candidates:
                mismatch_reasons = [r for r in candidates[0].reasons if "mismatch" in r or "penalised" in r]
                assert len(mismatch_reasons) >= 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Rejected pair is never re-proposed
# ---------------------------------------------------------------------------

class TestRejectedPairNotReproposed:
    """
    Critical: a rejected pair must NEVER be re-proposed on subsequent runs.
    """

    def test_rejected_pair_skipped_on_rerun(self):
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Shape of You", "performer": "Ed Sheeran",
                "duration_seconds": "234", "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Shape of You", "writers": "Ed Sheeran",
                "duration_seconds": "234", "version": "",
            })]

            # First run — get one candidate
            run1 = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(run1) == 1, "First run should produce one candidate"

            # Mark it rejected
            run1[0].status = "rejected"
            db.commit()

            # Second run — rejected pair must be skipped, no new candidates
            run2 = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert run2 == [], f"Rejected pair must not be re-proposed, got {run2}"
        finally:
            db.close()

    def test_rejected_pair_does_not_return_after_multiple_reruns(self):
        """Permanence check — 3 reruns, still no re-proposal."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Perfect", "performer": "Ed Sheeran",
                "duration_seconds": "263", "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Perfect", "writers": "Ed Sheeran",
                "duration_seconds": "263", "version": "",
            })]

            # Run 1
            run1 = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert len(run1) == 1
            run1[0].status = "rejected"
            db.commit()

            # Runs 2, 3, 4
            for i in range(3):
                run = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
                assert run == [], f"Run {i+2}: rejected pair reappeared"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Already-exact-linked recordings skipped
# ---------------------------------------------------------------------------

class TestAlreadyLinkedSkipped:
    def test_exact_linked_recording_not_proposed_as_fuzzy(self):
        """Recording already in already_linked_recording_ids → no fuzzy candidate."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Shape of You", "performer": "Ed Sheeran",
                "duration_seconds": "234", "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Shape of You", "writers": "Ed Sheeran",
                "duration_seconds": "234", "version": "",
            })]
            # Pass rec.id as already-linked
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, {rec.id})
            assert candidates == []
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Threshold — below 0.70 not proposed
# ---------------------------------------------------------------------------

class TestThreshold:
    def test_low_title_similarity_not_proposed(self):
        """Very different titles with name corroboration but low composite → no candidate."""
        db = _db()
        try:
            rec = _seed_record(db, 1, "recording", {})
            wrk = _seed_record(db, 1, "work", {})
            rec_nrows = [_nr(rec, {
                "title": "Aardvark Blues", "performer": "Ed Sheeran",
                "duration_seconds": "200", "version": "",
            })]
            wrk_nrows = [_nr(wrk, {
                "title": "Zebra Jazz", "writers": "Ed Sheeran",
                "duration_seconds": "201", "version": "",
            })]
            candidates = propose_fuzzy_candidates(db, 1, rec_nrows, wrk_nrows, set())
            assert candidates == [], "Title too different — should not be proposed even with exact name"
        finally:
            db.close()
