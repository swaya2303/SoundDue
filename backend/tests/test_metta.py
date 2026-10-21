"""
tests/test_metta.py — Isolated unit tests for each MeTTa rule.

Each test seeds a minimal in-memory SQLite DB, runs the relevant rule,
and asserts the expected findings.
"""

import sys
import os

# Ensure backend/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, OwnershipClaim, Mapping, MatchCandidate, Recording, Work
from metta_engine import MeTTaEngine


# ---------------------------------------------------------------------------
# Shared fixture: fresh in-memory DB + session
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_claim(
    db,
    *,
    work_iswc,
    rights_holder,
    share_pct,
    rights_category="mechanical",
    territory="WW",
    period_start="2020-01-01",
    period_end="2025-12-31",
    batch_id=1,
):
    c = OwnershipClaim(
        batch_id=batch_id,
        rights_holder=rights_holder,
        work_iswc=work_iswc,
        share_pct=Decimal(str(share_pct)),
        rights_category=rights_category,
        territory=territory,
        period_start=period_start,
        period_end=period_end,
        raw_json={},
    )
    db.add(c)
    db.flush()
    return c


# ===========================================================================
# RULE-001: share_sum_check
# ===========================================================================
class TestRule001:
    def test_no_finding_when_shares_sum_to_100(self, db):
        make_claim(db, work_iswc="T-001", rights_holder="A", share_pct=60.0)
        make_claim(db, work_iswc="T-001", rights_holder="B", share_pct=40.0)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_001_share_sum_check(db)
        assert findings == [], "Expected no findings when shares sum to 100"

    def test_warning_when_shares_gap(self, db):
        make_claim(db, work_iswc="T-002", rights_holder="A", share_pct=50.0)
        make_claim(db, work_iswc="T-002", rights_holder="B", share_pct=30.0)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_001_share_sum_check(db)
        assert len(findings) == 1
        f = findings[0]
        assert f["rule_id"] == "RULE-001"
        assert f["severity"] == "warning"
        assert "gap" in f["summary"].lower()
        assert f["evidence"]["total_pct"] == pytest.approx(80.0)

    def test_error_when_shares_exceed_100(self, db):
        make_claim(db, work_iswc="T-003", rights_holder="A", share_pct=60.0)
        make_claim(db, work_iswc="T-003", rights_holder="B", share_pct=50.0)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_001_share_sum_check(db)
        assert len(findings) == 1
        f = findings[0]
        assert f["severity"] == "error"
        assert "exceed" in f["summary"].lower()

    def test_groups_separately_by_category_and_territory(self, db):
        # mechanical WW sums to 100 — no finding
        make_claim(db, work_iswc="T-004", rights_holder="A", share_pct=60.0,
                   rights_category="mechanical", territory="WW")
        make_claim(db, work_iswc="T-004", rights_holder="B", share_pct=40.0,
                   rights_category="mechanical", territory="WW")
        # performance WW sums to 80 — warning
        make_claim(db, work_iswc="T-004", rights_holder="A", share_pct=50.0,
                   rights_category="performance", territory="WW")
        make_claim(db, work_iswc="T-004", rights_holder="B", share_pct=30.0,
                   rights_category="performance", territory="WW")
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_001_share_sum_check(db)
        assert len(findings) == 1
        assert findings[0]["severity"] == "warning"


# ===========================================================================
# RULE-002: missing_isrc_on_mapping
# ===========================================================================
class TestRule002:
    def test_no_finding_when_isrc_exists(self, db):
        rec = Recording(batch_id=1, isrc="ISRC001", title="Track A", raw_json={})
        db.add(rec)
        m = Mapping(batch_id=1, recording_isrc="ISRC001", work_iswc="T-001",
                    source_label="Label", raw_json={})
        db.add(m)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_002_missing_isrc_on_mapping(db)
        assert findings == []

    def test_warning_when_isrc_missing(self, db):
        m = Mapping(batch_id=1, recording_isrc="ISRC999", work_iswc="T-001",
                    source_label="Label", raw_json={})
        db.add(m)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_002_missing_isrc_on_mapping(db)
        assert len(findings) == 1
        f = findings[0]
        assert f["rule_id"] == "RULE-002"
        assert f["severity"] == "warning"
        assert f["evidence"]["recording_isrc"] == "ISRC999"


# ===========================================================================
# RULE-003: recording_work_no_link
# ===========================================================================
class TestRule003:
    def test_info_when_recording_has_no_mapping(self, db):
        rec = Recording(batch_id=1, isrc="ISRC001", title="Unlinked Track", raw_json={})
        db.add(rec)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_003_recording_work_no_link(db)
        assert len(findings) == 1
        f = findings[0]
        assert f["rule_id"] == "RULE-003"
        assert f["severity"] == "info"
        assert f["evidence"]["isrc"] == "ISRC001"

    def test_no_finding_when_recording_has_mapping(self, db):
        rec = Recording(batch_id=1, isrc="ISRC002", title="Linked Track", raw_json={})
        db.add(rec)
        m = Mapping(batch_id=1, recording_isrc="ISRC002", work_iswc="T-001",
                    source_label="L", raw_json={})
        db.add(m)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_003_recording_work_no_link(db)
        assert findings == []

    def test_no_finding_when_accepted_candidate(self, db):
        rec = Recording(batch_id=1, isrc="ISRC003", title="Candidate Track", raw_json={})
        db.add(rec)
        work = Work(batch_id=1, iswc="T-002", title="Candidate Work", raw_json={})
        db.add(work)
        db.flush()
        mc = MatchCandidate(
            recording_id=rec.id, work_id=work.id,
            score=Decimal("0.9"), method="fuzzy_title", status="accepted"
        )
        db.add(mc)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_003_recording_work_no_link(db)
        assert findings == []


# ===========================================================================
# RULE-004: incompatible_share_comparison
# ===========================================================================
class TestRule004:
    def test_no_finding_when_single_combo(self, db):
        make_claim(db, work_iswc="T-001", rights_holder="A", share_pct=60.0)
        make_claim(db, work_iswc="T-001", rights_holder="B", share_pct=40.0)
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_004_incompatible_share_comparison(db)
        assert findings == []

    def test_info_when_multiple_combos(self, db):
        make_claim(db, work_iswc="T-002", rights_holder="A", share_pct=50.0,
                   rights_category="mechanical", territory="WW")
        make_claim(db, work_iswc="T-002", rights_holder="B", share_pct=50.0,
                   rights_category="performance", territory="WW")
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_004_incompatible_share_comparison(db)
        assert len(findings) == 1
        f = findings[0]
        assert f["rule_id"] == "RULE-004"
        assert f["severity"] == "info"
        assert len(f["evidence"]["distinct_combos"]) == 2

    def test_multiple_territories_triggers(self, db):
        make_claim(db, work_iswc="T-003", rights_holder="A", share_pct=70.0,
                   rights_category="mechanical", territory="US")
        make_claim(db, work_iswc="T-003", rights_holder="B", share_pct=30.0,
                   rights_category="mechanical", territory="WW")
        db.commit()

        engine = MeTTaEngine()
        findings = engine._rule_004_incompatible_share_comparison(db)
        assert len(findings) == 1
