"""
tests/test_analyzer.py
======================
Tests for:
  - app/analyzer.py  (R1–R4 rules in isolation + integration)
  - POST /cases/{id}/analyze  (real findings returned)
  - GET /cases/{id}/findings
  - GET /findings/{id}
  - POST /findings/{id}/review

Each test class sets up a minimal case with only the files needed to exercise
the rule under test, confirms mappings, then calls analyze.

Shared-cache SQLite pattern (same as test_cases_api.py / test_mapping_api.py).
"""
from __future__ import annotations

import io
import json
import os

import pytest

# ---------------------------------------------------------------------------
# DB isolation — must happen before importing main
# ---------------------------------------------------------------------------
import app.models as _app_models
import database as _legacy_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TEST_DB_URI = (
    "sqlite:///file:sounddue_analyzertest?mode=memory&cache=shared&uri=true"
)
_cases_engine = create_engine(
    _TEST_DB_URI,
    connect_args={"check_same_thread": False},
)
_CasesSession = sessionmaker(bind=_cases_engine, autocommit=False, autoflush=False)
_app_models.Base.metadata.create_all(bind=_cases_engine)
_app_models.engine = _cases_engine
_app_models.SessionLocal = _CasesSession


def _get_cases_db():
    db = _CasesSession()
    try:
        yield db
    finally:
        db.close()


_app_models.get_db = _get_cases_db

_LEGACY_URI = (
    "sqlite:///file:sounddue_analyzertest_legacy?mode=memory&cache=shared&uri=true"
)
_legacy_engine = create_engine(
    _LEGACY_URI,
    connect_args={"check_same_thread": False},
)
_LegacySession = sessionmaker(bind=_legacy_engine, autocommit=False, autoflush=False)
_legacy_db.engine = _legacy_engine
_legacy_db.SessionLocal = _LegacySession


def _get_legacy_db():
    db = _LegacySession()
    try:
        yield db
    finally:
        db.close()


from main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app.dependency_overrides[_legacy_db.get_db] = _get_legacy_db
app.dependency_overrides[_app_models.get_db] = _get_cases_db

client = TestClient(app)


# ---------------------------------------------------------------------------
# Reset tables between tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset():
    _app_models.engine = _cases_engine
    _app_models.SessionLocal = _CasesSession
    _app_models.get_db = _get_cases_db
    app.dependency_overrides[_app_models.get_db] = _get_cases_db
    _app_models.Base.metadata.drop_all(bind=_cases_engine)
    _app_models.Base.metadata.create_all(bind=_cases_engine)
    yield


# ---------------------------------------------------------------------------
# CSV fixtures (canonical headers — mappings confirm these directly)
# ---------------------------------------------------------------------------

# Recordings: canonical headers so we can map Track Code → recording_id etc.
def _recordings_csv(rows: list[str]) -> bytes:
    header = "Track Code,Track Title,Main Artist,Version,Secs,ISRC Code\r\n"
    return (header + "".join(r + "\r\n" for r in rows)).encode()


def _works_csv(rows: list[str]) -> bytes:
    header = "work_id,title,writers,iswc\r\n"
    return (header + "".join(r + "\r\n" for r in rows)).encode()


# Ownership with Work Code / Songwriter % headers (synonym exact)
def _ownership_csv(rows: list[str]) -> bytes:
    header = (
        "Work Code,Writer Code,Songwriter,Songwriter %,Convention,"
        "Rights Type,Territory,Valid From,Valid To,Claim Status\r\n"
    )
    return (header + "".join(r + "\r\n" for r in rows)).encode()


# Ownership with alternate headers (Composition ID / Share % — for S4-B)
def _ownership_alt_csv(rows: list[str]) -> bytes:
    header = (
        "Composition ID,Contributor ID,Rights Holder,Share %,Share Type,"
        "Rights Category,Market,Period Start,Period End,Status\r\n"
    )
    return (header + "".join(r + "\r\n" for r in rows)).encode()


def _mappings_csv(rows: list[str]) -> bytes:
    header = "recording_id,work_id,source_label,verified\r\n"
    return (header + "".join(r + "\r\n" for r in rows)).encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_REC_MAPPINGS = [
    {"source_column": "Track Code", "canonical_field": "recording_id"},
    {"source_column": "Track Title", "canonical_field": "title"},
]
_WORK_MAPPINGS = [
    {"source_column": "work_id", "canonical_field": "work_id"},
    {"source_column": "title", "canonical_field": "title"},
]
_OWN_MAPPINGS = [
    {"source_column": "Work Code", "canonical_field": "work_id"},
    {"source_column": "Songwriter %", "canonical_field": "share"},
    {"source_column": "Rights Type", "canonical_field": "rights_category"},
    {"source_column": "Territory", "canonical_field": "territory"},
    {"source_column": "Valid From", "canonical_field": "effective_from"},
    {"source_column": "Valid To", "canonical_field": "effective_to"},
    {"source_column": "Claim Status", "canonical_field": "status"},
    {"source_column": "Writer Code", "canonical_field": "contributor_id"},
]
_OWN_ALT_MAPPINGS = [
    {"source_column": "Composition ID", "canonical_field": "work_id"},
    {"source_column": "Share %", "canonical_field": "share"},
    {"source_column": "Rights Category", "canonical_field": "rights_category"},
    {"source_column": "Market", "canonical_field": "territory"},
    {"source_column": "Period Start", "canonical_field": "effective_from"},
    {"source_column": "Period End", "canonical_field": "effective_to"},
    {"source_column": "Status", "canonical_field": "status"},
    {"source_column": "Contributor ID", "canonical_field": "contributor_id"},
]
_MAP_MAPPINGS = [
    {"source_column": "recording_id", "canonical_field": "recording_id"},
    {"source_column": "work_id", "canonical_field": "work_id"},
    {"source_column": "verified", "canonical_field": "verified"},
]


def _create_case(name: str = "Test") -> int:
    r = client.post("/cases", data={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def _upload(case_id: int, content: bytes, kind: str, name: str) -> int:
    r = client.post(
        f"/cases/{case_id}/files",
        data={"file_kind": kind},
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()["file_id"]


def _confirm(file_id: int, mappings: list[dict]) -> None:
    r = client.put(f"/files/{file_id}/mapping", json={"mappings": mappings})
    assert r.status_code == 200, r.text


def _analyze(case_id: int, expect_status: int = 202) -> dict:
    r = client.post(f"/cases/{case_id}/analyze")
    assert r.status_code == expect_status, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Analyzer unit tests (rules in isolation)
# ---------------------------------------------------------------------------
class TestRuleR1:
    """R1 — possible_missing_claim: explicit 'unclaimed' label."""

    def test_fires_on_unclaimed_label(self):
        from app.analyzer import _rule_r1
        rows = [
            {"work_id": "W1", "share": "60", "rights_category": "mech",
             "territory": "WW", "status": "claimed"},
            {"work_id": "W1", "share": "40", "rights_category": "mech",
             "territory": "WW", "status": "unclaimed"},
        ]
        findings = _rule_r1(rows)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "possible_missing_claim"
        assert findings[0]["rule_id"] == "R1"
        assert findings[0]["severity"] == "warning"

    def test_does_not_fire_without_unclaimed(self):
        from app.analyzer import _rule_r1
        rows = [
            {"work_id": "W1", "share": "60", "status": "claimed"},
            {"work_id": "W1", "share": "40", "status": "claimed"},
        ]
        assert _rule_r1(rows) == []

    def test_pool_label_also_triggers(self):
        from app.analyzer import _rule_r1
        rows = [{"work_id": "W1", "share": "40", "status": "Pool",
                 "rights_category": "mech", "territory": "WW"}]
        findings = _rule_r1(rows)
        assert len(findings) == 1


class TestRuleR2:
    """R2 — incomplete_ownership_info: silent gap, no unclaimed label."""

    def test_fires_when_gap_and_no_unclaimed(self):
        from app.analyzer import _rule_r2
        rows = [
            {"work_id": "W1", "share": "60", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
        ]
        findings = _rule_r2(rows)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "incomplete_ownership_info"
        assert findings[0]["rule_id"] == "R2"

    def test_does_not_fire_when_100_pct(self):
        from app.analyzer import _rule_r2
        rows = [
            {"work_id": "W1", "share": "60", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
            {"work_id": "W1", "share": "40", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
        ]
        assert _rule_r2(rows) == []

    def test_does_not_fire_when_unclaimed_present(self):
        """Gap exists but it's explicitly labelled — R1 should fire, not R2."""
        from app.analyzer import _rule_r2
        rows = [
            {"work_id": "W1", "share": "60", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
            {"work_id": "W1", "share": "40", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "unclaimed"},
        ]
        assert _rule_r2(rows) == []

    def test_different_scopes_checked_independently(self):
        from app.analyzer import _rule_r2
        rows = [
            # Scope 1: 100% — no finding
            {"work_id": "W1", "share": "100", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
            # Scope 2: 60% — finding
            {"work_id": "W2", "share": "60", "rights_category": "mech",
             "territory": "WW", "effective_from": "2020-01-01",
             "effective_to": "2030-12-31", "status": "claimed"},
        ]
        findings = _rule_r2(rows)
        assert len(findings) == 1
        assert findings[0]["evidence"]["work_id"] == "W2"


class TestRuleR3:
    """R3 — conflicting_shares: same contributor, same scope, different figures."""

    def test_fires_on_conflicting_shares(self):
        from app.analyzer import _rule_r3
        rows = [
            {"work_id": "W1", "contributor_id": "C1", "share": "60",
             "rights_category": "mech", "territory": "WW",
             "effective_from": "2020-01-01", "effective_to": "2030-12-31"},
            {"work_id": "W1", "contributor_id": "C1", "share": "50",
             "rights_category": "mech", "territory": "WW",
             "effective_from": "2020-01-01", "effective_to": "2030-12-31"},
        ]
        findings = _rule_r3(rows)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "conflicting_shares"
        assert findings[0]["severity"] == "error"
        assert findings[0]["rule_id"] == "R3"

    def test_does_not_fire_when_shares_agree(self):
        from app.analyzer import _rule_r3
        rows = [
            {"work_id": "W1", "contributor_id": "C1", "share": "60",
             "rights_category": "mech", "territory": "WW",
             "effective_from": "2020-01-01", "effective_to": "2030-12-31"},
            {"work_id": "W1", "contributor_id": "C1", "share": "60.0000",
             "rights_category": "mech", "territory": "WW",
             "effective_from": "2020-01-01", "effective_to": "2030-12-31"},
        ]
        assert _rule_r3(rows) == []

    def test_different_scopes_not_conflicting(self):
        """Incompatible scopes (different territory/rights_category) → no R3."""
        from app.analyzer import _rule_r3
        rows = [
            {"work_id": "W1", "contributor_id": "C1", "share": "60",
             "rights_category": "all-rights", "territory": "WW",
             "effective_from": "2020-01-01", "effective_to": "2025-12-31"},
            {"work_id": "W1", "contributor_id": "C1", "share": "50",
             "rights_category": "mechanical", "territory": "US",
             "effective_from": "2019-01-01", "effective_to": "2023-12-31"},
        ]
        assert _rule_r3(rows) == []


class TestRuleR4:
    """R4 — unlinked_recording: no verified mapping."""

    def test_fires_for_unlinked_recording(self):
        from app.analyzer import _rule_r4
        recs = [{"recording_id": "R1", "title": "Song A"}]
        maps = [{"recording_id": "R2", "work_id": "W1", "verified": "true"}]
        findings = _rule_r4(recs, maps)
        assert len(findings) == 1
        assert findings[0]["finding_type"] == "unlinked_recording"
        assert findings[0]["rule_id"] == "R4"

    def test_does_not_fire_when_verified_mapping_exists(self):
        from app.analyzer import _rule_r4
        recs = [{"recording_id": "R1", "title": "Song A"}]
        maps = [{"recording_id": "R1", "work_id": "W1", "verified": "true"}]
        assert _rule_r4(recs, maps) == []

    def test_unverified_mapping_does_not_count(self):
        """verified=false → still triggers R4."""
        from app.analyzer import _rule_r4
        recs = [{"recording_id": "R1", "title": "Song A"}]
        maps = [{"recording_id": "R1", "work_id": "W1", "verified": "false"}]
        findings = _rule_r4(recs, maps)
        assert len(findings) == 1

    def test_no_mappings_file_all_recordings_flagged(self):
        from app.analyzer import _rule_r4
        recs = [
            {"recording_id": "R1", "title": "A"},
            {"recording_id": "R2", "title": "B"},
        ]
        findings = _rule_r4(recs, [])
        assert len(findings) == 2


# ---------------------------------------------------------------------------
# Integration tests via API
# ---------------------------------------------------------------------------

class TestScenario01_MidnightTrainUnclaimed:
    """R1 fires. R2 must NOT fire."""

    def test_analyze_produces_r1_finding(self):
        cid = _create_case("S1")
        # recordings
        fid = _upload(cid, _recordings_csv(["REC-S1-001,Midnight Train,Artist A,Orig,214,"]),
                      "recordings", "rec.csv")
        _confirm(fid, _REC_MAPPINGS)
        # works
        wid = _upload(cid, _works_csv(["WRK-S1-001,Midnight Train,Writer A,"]),
                      "works", "works.csv")
        _confirm(wid, _WORK_MAPPINGS)
        # ownership: explicit unclaimed row
        oid = _upload(cid, _ownership_csv([
            "WRK-S1-001,WRT-A,Writer A,60.0000,pub,mechanical,WW,2020-01-01,2030-12-31,claimed",
            "WRK-S1-001,POOL,Unclaimed Pool,40.0000,pub,mechanical,WW,2020-01-01,2030-12-31,unclaimed",
        ]), "ownership", "own.csv")
        _confirm(oid, _OWN_MAPPINGS)
        # mappings
        mid = _upload(cid, _mappings_csv(["REC-S1-001,WRK-S1-001,Reg,true"]),
                      "mappings", "map.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        types = result["findings_by_type"]
        assert "possible_missing_claim" in types
        assert "incomplete_ownership_info" not in types

    def test_finding_has_correct_rule_id(self):
        cid = _create_case("S1b")
        fid = _upload(cid, _recordings_csv(["R1,Song,A,v1,200,"]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Song,A,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "W1,C1,Writer A,60.0000,pub,mech,WW,2020-01-01,2030-12-31,claimed",
            "W1,POOL,Pool,40.0000,pub,mech,WW,2020-01-01,2030-12-31,unclaimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv(["R1,W1,src,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        _analyze(cid)
        findings = client.get(f"/cases/{cid}/findings").json()
        r1_findings = [f for f in findings if f["rule_id"] == "R1"]
        assert len(r1_findings) >= 1


class TestScenario02_SilentOmission:
    """R2 fires. R1 must NOT fire."""

    def test_analyze_produces_r2_not_r1(self):
        cid = _create_case("S2")
        fid = _upload(cid, _recordings_csv(["R1,Silent Song,A,Orig,200,"]),
                      "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Silent Song,Writer A,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        # Only 60% supplied — no unclaimed label
        oid = _upload(cid, _ownership_csv([
            "W1,C1,Writer A,60.0000,pub,mechanical,WW,2020-01-01,2030-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv(["R1,W1,src,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        types = result["findings_by_type"]
        assert "incomplete_ownership_info" in types
        assert "possible_missing_claim" not in types


class TestScenario03_SameTitleDifferentWriters:
    """Two works with the same title but different IDs. No findings expected."""

    def test_no_findings(self):
        cid = _create_case("S3")
        fid = _upload(cid, _recordings_csv([
            "R1,Golden Hour,X,v1,200,",
            "R2,Golden Hour,Y,v1,200,",
        ]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv([
            "W1,Golden Hour,Writer X,",
            "W2,Golden Hour,Writer Y,",
        ]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "W1,C1,Writer X,100.0000,pub,mechanical,WW,2021-01-01,2031-12-31,claimed",
            "W2,C2,Writer Y,100.0000,pub,mechanical,WW,2021-01-01,2031-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv([
            "R1,W1,src,true",
            "R2,W2,src,true",
        ]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        assert result["finding_count"] == 0
        # Explicitly check none of the disallowed types appear
        types = result["findings_by_type"]
        assert "works_merged" not in types
        assert "title_match_link" not in types
        assert "incomplete_ownership_info" not in types
        assert "conflicting_shares" not in types


class TestScenario04_ConflictingShares:
    """R3 fires. R2 must NOT fire (100% in each source)."""

    def test_analyze_produces_r3(self):
        cid = _create_case("S4")
        fid = _upload(cid, _recordings_csv(["R1,Conflict Song,A,v1,200,"]),
                      "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Conflict Song,A,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)

        # Source A: 60/40
        oid_a = _upload(cid, _ownership_csv([
            "W1,C1,Writer A,60.0000,pub,mechanical,WW,2019-01-01,2029-12-31,claimed",
            "W1,C2,Writer B,40.0000,pub,mechanical,WW,2019-01-01,2029-12-31,claimed",
        ]), "ownership", "own_a.csv")
        _confirm(oid_a, _OWN_MAPPINGS)

        # Source B: 50/50 (alternate headers)
        oid_b = _upload(cid, _ownership_alt_csv([
            "W1,C1,Writer A,50.0000,pub,mechanical,WW,2019-01-01,2029-12-31,claimed",
            "W1,C2,Writer B,50.0000,pub,mechanical,WW,2019-01-01,2029-12-31,claimed",
        ]), "ownership", "own_b.csv")
        _confirm(oid_b, _OWN_ALT_MAPPINGS)

        mid = _upload(cid, _mappings_csv(["R1,W1,src,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        types = result["findings_by_type"]
        assert "conflicting_shares" in types
        assert "incomplete_ownership_info" not in types


class TestScenario05_IncompatibleScopes:
    """Different territory, rights_category, period → NO conflict (R3 must not fire)."""

    def test_no_conflicting_shares_finding(self):
        cid = _create_case("S5")
        fid = _upload(cid, _recordings_csv(["R1,Scope Song,C,v1,180,"]),
                      "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Scope Song,C,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)

        # Source A: WW / all-rights / 2020-2025
        oid_a = _upload(cid, _ownership_csv([
            "W1,C1,Writer C,70.0000,pub,all-rights,WW,2020-01-01,2025-12-31,claimed",
            "W1,C2,Writer D,30.0000,pub,all-rights,WW,2020-01-01,2025-12-31,claimed",
        ]), "ownership", "own_ww.csv")
        _confirm(oid_a, _OWN_MAPPINGS)

        # Source B: US / mechanical / 2019-2023 (different scope — no conflict)
        oid_b = _upload(cid, _ownership_alt_csv([
            "W1,C1,Writer C,60.0000,pub,mechanical,US,2019-01-01,2023-12-31,claimed",
            "W1,C2,Writer D,40.0000,pub,mechanical,US,2019-01-01,2023-12-31,claimed",
        ]), "ownership", "own_us.csv")
        _confirm(oid_b, _OWN_ALT_MAPPINGS)

        mid = _upload(cid, _mappings_csv(["R1,W1,src,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        assert "conflicting_shares" not in result["findings_by_type"]


class TestScenario06_UnmappedRecording:
    """R4 fires for REC-S6-001. REC-S6-002 is mapped → no R4 for it."""

    def test_r4_fires_only_for_unmapped(self):
        cid = _create_case("S6")
        fid = _upload(cid, _recordings_csv([
            "REC-S6-001,Ghost Signal,Artist Z,Demo,163,",
            "REC-S6-002,Ghost Signal,Artist Z,Album,171,",
        ]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["WRK-S6-001,Ghost Signal,Z,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "WRK-S6-001,C1,Writer Z,100.0000,pub,mechanical,WW,2020-01-01,2030-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        # Only REC-S6-002 is mapped
        mid = _upload(cid, _mappings_csv(["REC-S6-002,WRK-S6-001,LabelZ,true"]),
                      "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)

        result = _analyze(cid)
        types = result["findings_by_type"]
        assert "unlinked_recording" in types
        assert types["unlinked_recording"] == 1  # only one unmapped recording

        # Verify the flagged recording is REC-S6-001, not REC-S6-002
        findings = client.get(f"/cases/{cid}/findings").json()
        r4 = [f for f in findings if f.get("rule_id") == "R4"]
        assert len(r4) == 1
        detail = client.get(f"/findings/{r4[0]['id']}").json()
        ev = detail["evidence"][0]["field_values"]
        assert ev["recording_id"] == "REC-S6-001"


# ---------------------------------------------------------------------------
# GET /cases/{id}/findings
# ---------------------------------------------------------------------------
class TestListFindings:
    def test_empty_before_analysis(self):
        cid = _create_case()
        r = client.get(f"/cases/{cid}/findings")
        assert r.status_code == 200
        assert r.json() == []

    def test_404_for_missing_case(self):
        r = client.get("/cases/99999/findings")
        assert r.status_code == 404

    def test_findings_returned_after_analysis(self):
        cid = _create_case()
        fid = _upload(cid, _recordings_csv(["R1,A,X,v1,100,"]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,A,X,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "W1,C1,X,60.0000,pub,mech,WW,2020-01-01,2030-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv(["R1,W1,s,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)
        _analyze(cid)

        findings = client.get(f"/cases/{cid}/findings").json()
        assert isinstance(findings, list)
        assert len(findings) > 0
        f = findings[0]
        assert "id" in f
        assert "severity" in f
        assert "rule_id" in f


# ---------------------------------------------------------------------------
# GET /findings/{id}
# ---------------------------------------------------------------------------
class TestGetFinding:
    def _setup_with_r2(self) -> tuple[int, int]:
        """Returns (case_id, finding_id) for an R2 finding."""
        cid = _create_case()
        fid = _upload(cid, _recordings_csv(["R1,Song,A,v,100,"]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Song,A,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "W1,C1,A,60.0000,pub,mech,WW,2020-01-01,2030-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv(["R1,W1,s,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)
        _analyze(cid)
        findings = client.get(f"/cases/{cid}/findings").json()
        return cid, findings[0]["id"]

    def test_returns_full_detail(self):
        _, fid = self._setup_with_r2()
        r = client.get(f"/findings/{fid}")
        assert r.status_code == 200
        data = r.json()
        assert "rule_trace" in data
        assert "evidence" in data
        assert "review_decisions" in data
        assert data["rule_trace"]["rule_id"] in ("R1", "R2", "R3", "R4")

    def test_rule_trace_fields_present(self):
        _, fid = self._setup_with_r2()
        data = client.get(f"/findings/{fid}").json()
        rt = data["rule_trace"]
        assert "matched_conditions" in rt
        assert "missing_information" in rt
        assert "evaluated_at" in rt

    def test_404_for_missing_finding(self):
        r = client.get("/findings/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /findings/{id}/review
# ---------------------------------------------------------------------------
class TestReviewFinding:
    def _get_finding_id(self) -> int:
        cid = _create_case()
        fid = _upload(cid, _recordings_csv(["R1,Song,A,v,100,"]), "recordings", "r.csv")
        _confirm(fid, _REC_MAPPINGS)
        wid = _upload(cid, _works_csv(["W1,Song,A,"]), "works", "w.csv")
        _confirm(wid, _WORK_MAPPINGS)
        oid = _upload(cid, _ownership_csv([
            "W1,C1,A,60.0000,pub,mech,WW,2020-01-01,2030-12-31,claimed",
        ]), "ownership", "o.csv")
        _confirm(oid, _OWN_MAPPINGS)
        mid = _upload(cid, _mappings_csv(["R1,W1,s,true"]), "mappings", "m.csv")
        _confirm(mid, _MAP_MAPPINGS)
        _analyze(cid)
        return client.get(f"/cases/{cid}/findings").json()[0]["id"]

    def test_accept_sets_resolved(self):
        fid = self._get_finding_id()
        r = client.post(f"/findings/{fid}/review",
                        json={"decision": "accept", "note": "looks fine"})
        assert r.status_code == 200
        assert r.json()["new_status"] == "resolved"

    def test_reject_sets_rejected(self):
        fid = self._get_finding_id()
        r = client.post(f"/findings/{fid}/review",
                        json={"decision": "reject", "note": "false positive"})
        assert r.status_code == 200
        assert r.json()["new_status"] == "rejected"

    def test_correct_sets_resolved_with_values(self):
        fid = self._get_finding_id()
        r = client.post(f"/findings/{fid}/review", json={
            "decision": "correct",
            "note": "fixed share",
            "corrected_values": {"share": "100"},
        })
        assert r.status_code == 200
        assert r.json()["new_status"] == "resolved"

    def test_review_appears_in_decision_history(self):
        fid = self._get_finding_id()
        client.post(f"/findings/{fid}/review",
                    json={"decision": "accept", "note": "ok"})
        detail = client.get(f"/findings/{fid}").json()
        assert len(detail["review_decisions"]) == 1
        assert detail["review_decisions"][0]["decision"] == "accept"
        assert detail["status"] == "resolved"

    def test_invalid_decision_returns_400(self):
        fid = self._get_finding_id()
        r = client.post(f"/findings/{fid}/review",
                        json={"decision": "approve"})
        assert r.status_code == 400

    def test_404_for_missing_finding(self):
        r = client.post("/findings/99999/review",
                        json={"decision": "accept"})
        assert r.status_code == 404
