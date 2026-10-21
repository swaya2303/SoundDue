"""
tests/test_linker.py
====================
Tests for app.linker.generate_links — exact-match candidate generation.

Critical invariants:
  * Scenario 3 (same title "Golden Hour", different work IDs): produces
    exactly 2 links, each pairing the right recording with the right work.
    No cross-link (REC-S3-001 must NOT link to WRK-S3-002).
  * Title-only match (same title but no shared IDs): generates ZERO links.
  * Verified mapping row  → RecordingLink.verified == True, method == "explicit_mapping"
  * Unverified mapping row → RecordingLink.verified == False, method == "unverified_mapping"
  * ISRC + ISWC exact match via mapping row → method == "isrc_iswc"
  * No match without explicit mapping row (no free-standing cross-file ISRC lookup)

DB isolation uses a unique shared-cache in-memory SQLite URI per this module.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models as _models
from app.linker import RecordingLink, generate_links
from app.models import Base, MatchCandidate, Record
from app.normaliser import NormalisedRow

# ---------------------------------------------------------------------------
# DB Setup — unique in-memory DB per this test module
# ---------------------------------------------------------------------------

_engine = create_engine(
    "sqlite:///file:sounddue_linkertest?mode=memory&cache=shared&uri=true",
    connect_args={"check_same_thread": False},
)
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def _reset_db():
    """Drop and recreate all tables before each test."""
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


def _make_db():
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_record(db, case_id: int, record_type: str, normalised: dict) -> Record:
    """Insert a bare Record row and return it with its DB id."""
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
    db.flush()  # populate rec.id
    return rec


def _make_nr(record: Record, normalised: dict, source_ref: dict | None = None) -> NormalisedRow:
    """Construct a NormalisedRow with record_id attached in source_ref."""
    ref = dict(source_ref or {})
    ref["record_id"] = record.id
    return NormalisedRow(
        normalised=normalised,
        raw={},
        comparison_keys={},
        source_ref=ref,
    )


def _mapping_nr(normalised: dict, row_number: int = 1) -> NormalisedRow:
    """Mapping row without a Record DB row (not stored in records table)."""
    return NormalisedRow(
        normalised=normalised,
        raw={},
        comparison_keys={},
        source_ref={"file_name": "mappings.csv", "file_id": None, "row_number": row_number},
    )


# ---------------------------------------------------------------------------
# Verified / unverified explicit mapping
# ---------------------------------------------------------------------------

class TestExplicitMapping:
    def test_verified_mapping_creates_link(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [_mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": True})]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)

            assert len(links) == 1
            assert links[0].verified is True
            assert links[0].method == "explicit_mapping"
            assert links[0].score == Decimal("1.0")
            assert links[0].recording_id == "REC-001"
            assert links[0].work_id == "WRK-001"
        finally:
            db.close()

    def test_unverified_mapping_creates_link_with_lower_score(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [_mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": False})]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)

            assert len(links) == 1
            assert links[0].verified is False
            assert links[0].method == "unverified_mapping"
            assert links[0].score == Decimal("0.9")
        finally:
            db.close()

    def test_match_candidate_row_persisted(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [_mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": True})]

            generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            db.commit()

            candidates = db.query(MatchCandidate).all()
            assert len(candidates) == 1
            assert candidates[0].left_record_id == rec_rec.id
            assert candidates[0].right_record_id == wrk_rec.id
            assert candidates[0].status == "pending"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TITLE-ONLY — must NEVER create a link
# ---------------------------------------------------------------------------

class TestTitleOnlyNeverCreatesLink:
    """
    Critical invariant: shared title with no matching IDs → zero links.
    Comparison keys exist on NormalisedRow but are deliberately not used.
    """

    def test_same_title_no_matching_ids_zero_links(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-TITLE-01", "title": "Golden Hour"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-TITLE-01", "title": "Golden Hour"})

            rec_nrows = [_make_nr(rec_rec, {
                "recording_id": "REC-TITLE-01",
                "title": "Golden Hour",
                "isrc": "",
            })]
            wrk_nrows = [_make_nr(wrk_rec, {
                "work_id": "WRK-TITLE-01",
                "title": "Golden Hour",
                "iswc": "",
            })]
            # No mapping rows at all
            map_nrows = []

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert links == [], "Title-only match must never create a link"
        finally:
            db.close()

    def test_same_title_wrong_ids_in_mapping_zero_links(self):
        """Mapping row points to IDs that don't exist in recordings/works — no link."""
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-A"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-B"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-A", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-B", "iswc": ""})]
            # Mapping references completely different IDs
            map_nrows = [_mapping_nr({"recording_id": "REC-Z", "work_id": "WRK-Z", "verified": True})]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert links == []
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Scenario 3 — same title "Golden Hour", different writers and IDs
# ---------------------------------------------------------------------------

class TestScenario3SameTitleDifferentWriters:
    """
    Scenario 3: two works titled "Golden Hour" (WRK-S3-001 / WRK-S3-002)
    with two recordings (REC-S3-001 / REC-S3-002).  Mapping rows link them
    correctly:
        REC-S3-001 → WRK-S3-001 (Writer X)
        REC-S3-002 → WRK-S3-002 (Writer Y)

    Expected outcome:
      - Exactly 2 links.
      - No cross-link: REC-S3-001 must NOT link to WRK-S3-002, and vice versa.
    """

    def _setup(self, db):
        rec1 = _seed_record(db, 1, "recording", {
            "recording_id": "REC-S3-001", "title": "Golden Hour",
        })
        rec2 = _seed_record(db, 1, "recording", {
            "recording_id": "REC-S3-002", "title": "Golden Hour",
        })
        wrk1 = _seed_record(db, 1, "work", {
            "work_id": "WRK-S3-001", "title": "Golden Hour", "writers": "Writer X",
        })
        wrk2 = _seed_record(db, 1, "work", {
            "work_id": "WRK-S3-002", "title": "Golden Hour", "writers": "Writer Y",
        })
        return rec1, rec2, wrk1, wrk2

    def test_produces_exactly_two_links(self):
        db = _make_db()
        try:
            rec1, rec2, wrk1, wrk2 = self._setup(db)

            rec_nrows = [
                _make_nr(rec1, {"recording_id": "REC-S3-001", "title": "Golden Hour", "isrc": ""}),
                _make_nr(rec2, {"recording_id": "REC-S3-002", "title": "Golden Hour", "isrc": ""}),
            ]
            wrk_nrows = [
                _make_nr(wrk1, {"work_id": "WRK-S3-001", "title": "Golden Hour", "iswc": ""}),
                _make_nr(wrk2, {"work_id": "WRK-S3-002", "title": "Golden Hour", "iswc": ""}),
            ]
            map_nrows = [
                _mapping_nr({"recording_id": "REC-S3-001", "work_id": "WRK-S3-001", "verified": True}, row_number=1),
                _mapping_nr({"recording_id": "REC-S3-002", "work_id": "WRK-S3-002", "verified": True}, row_number=2),
            ]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert len(links) == 2
        finally:
            db.close()

    def test_no_cross_link(self):
        """REC-S3-001 must NOT be linked to WRK-S3-002 and vice versa."""
        db = _make_db()
        try:
            rec1, rec2, wrk1, wrk2 = self._setup(db)

            rec_nrows = [
                _make_nr(rec1, {"recording_id": "REC-S3-001", "title": "Golden Hour", "isrc": ""}),
                _make_nr(rec2, {"recording_id": "REC-S3-002", "title": "Golden Hour", "isrc": ""}),
            ]
            wrk_nrows = [
                _make_nr(wrk1, {"work_id": "WRK-S3-001", "title": "Golden Hour", "iswc": ""}),
                _make_nr(wrk2, {"work_id": "WRK-S3-002", "title": "Golden Hour", "iswc": ""}),
            ]
            map_nrows = [
                _mapping_nr({"recording_id": "REC-S3-001", "work_id": "WRK-S3-001", "verified": True}, row_number=1),
                _mapping_nr({"recording_id": "REC-S3-002", "work_id": "WRK-S3-002", "verified": True}, row_number=2),
            ]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)

            # Build set of (recording_record_id, work_record_id) pairs
            pairs = {(lnk.recording_record_id, lnk.work_record_id) for lnk in links}

            # Correct pairs
            assert (rec1.id, wrk1.id) in pairs, "REC-S3-001 should link to WRK-S3-001"
            assert (rec2.id, wrk2.id) in pairs, "REC-S3-002 should link to WRK-S3-002"

            # Cross-links must NOT exist
            assert (rec1.id, wrk2.id) not in pairs, "REC-S3-001 must NOT link to WRK-S3-002"
            assert (rec2.id, wrk1.id) not in pairs, "REC-S3-002 must NOT link to WRK-S3-001"
        finally:
            db.close()

    def test_correct_work_ids_in_links(self):
        """Verify work_id and recording_id fields on each link."""
        db = _make_db()
        try:
            rec1, rec2, wrk1, wrk2 = self._setup(db)

            rec_nrows = [
                _make_nr(rec1, {"recording_id": "REC-S3-001", "isrc": ""}),
                _make_nr(rec2, {"recording_id": "REC-S3-002", "isrc": ""}),
            ]
            wrk_nrows = [
                _make_nr(wrk1, {"work_id": "WRK-S3-001", "iswc": ""}),
                _make_nr(wrk2, {"work_id": "WRK-S3-002", "iswc": ""}),
            ]
            map_nrows = [
                _mapping_nr({"recording_id": "REC-S3-001", "work_id": "WRK-S3-001", "verified": True}, 1),
                _mapping_nr({"recording_id": "REC-S3-002", "work_id": "WRK-S3-002", "verified": True}, 2),
            ]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            by_rec = {lnk.recording_id: lnk.work_id for lnk in links}

            assert by_rec["REC-S3-001"] == "WRK-S3-001"
            assert by_rec["REC-S3-002"] == "WRK-S3-002"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# ISRC / ISWC exact match
# ---------------------------------------------------------------------------

class TestIsrcIswcMatch:
    def test_isrc_iswc_creates_link(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-X", "isrc": "US123"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-X", "iswc": "T-123456789-0"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-X", "isrc": "US123"})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-X", "iswc": "T-123456789-0"})]
            map_nrows = [_mapping_nr({
                "recording_id": "",      # no explicit ID match
                "work_id": "",
                "isrc": "US123",
                "iswc": "T-123456789-0",
                "verified": True,
            })]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert len(links) == 1
            assert links[0].method == "isrc_iswc"
            assert links[0].score == Decimal("1.0")
        finally:
            db.close()

    def test_isrc_only_no_iswc_no_link(self):
        """ISRC without matching ISWC in the mapping row → no link."""
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-X", "isrc": "US123"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-X", "iswc": "T-123456789-0"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-X", "isrc": "US123"})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-X", "iswc": "T-123456789-0"})]
            # Mapping only has ISRC, not ISWC
            map_nrows = [_mapping_nr({
                "recording_id": "",
                "work_id": "",
                "isrc": "US123",
                "iswc": "",
                "verified": True,
            })]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert links == []
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_inputs_no_links(self):
        db = _make_db()
        try:
            links = generate_links(db, 1, [], [], [])
            assert links == []
        finally:
            db.close()

    def test_no_mapping_rows_no_links(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, [])
            assert links == []
        finally:
            db.close()

    def test_duplicate_mapping_rows_deduplicated(self):
        """Two identical mapping rows should not create duplicate candidates."""
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [
                _mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": True}, 1),
                _mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": True}, 2),
            ]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert len(links) == 1  # deduplicated
        finally:
            db.close()

    def test_source_ref_attached_to_link(self):
        """Source ref (file_name, row_number) should be present on the link."""
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [_mapping_nr(
                {"recording_id": "REC-001", "work_id": "WRK-001", "verified": True},
                row_number=5,
            )]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert links[0].source_ref.get("row_number") == 5
            assert links[0].source_ref.get("file_name") == "mappings.csv"
        finally:
            db.close()

    def test_reasons_list_populated(self):
        db = _make_db()
        try:
            rec_rec = _seed_record(db, 1, "recording", {"recording_id": "REC-001"})
            wrk_rec = _seed_record(db, 1, "work", {"work_id": "WRK-001"})

            rec_nrows = [_make_nr(rec_rec, {"recording_id": "REC-001", "isrc": ""})]
            wrk_nrows = [_make_nr(wrk_rec, {"work_id": "WRK-001", "iswc": ""})]
            map_nrows = [_mapping_nr({"recording_id": "REC-001", "work_id": "WRK-001", "verified": True})]

            links = generate_links(db, 1, rec_nrows, wrk_nrows, map_nrows)
            assert len(links[0].reasons) >= 1
        finally:
            db.close()
