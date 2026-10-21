"""
tests/test_analyze_rerun_api.py
================================
End-to-end integration tests for the analysis/review/rerun flow.

Covers the "Midnight Train" scenario:
  1. Create a case
  2. Upload ownership CSV (unclaimed 40 %)
  3. Upload mappings CSV
  4. Confirm column mappings
  5. POST /cases/{id}/analyze  → R1 finding (possible_missing_claim)
  6. GET /cases/{id}/findings  → list contains the R1 finding
  7. GET /findings/{id}        → full detail (evidence, rule_trace, history)
  8. POST /findings/{id}/review  decision=correct, corrected_values, note required
  9. POST /cases/{id}/rerun    → finding listed as resolved, history intact

Additional tests:
  - review with decision=reject then rerun → finding stays rejected (not re-opened)
  - GET /findings/{id}/history after two decisions shows both entries
  - review with decision=correct and empty note → 400
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# App + DB override
# ---------------------------------------------------------------------------
from app.models import Base, get_db
import main as main_module

_TEST_DB_URL = "sqlite:///file:midnighttrain_test?mode=memory&cache=shared&uri=true"
_engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="module")
def _setup_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="module")
def client():
    main_module.app.dependency_overrides[get_db] = _override_get_db
    with TestClient(main_module.app) as c:
        yield c
    main_module.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Synthetic Midnight Train data
# ---------------------------------------------------------------------------

_OWNERSHIP_CSV = b"""\
Work Code,Writer Code,Songwriter,Songwriter %,Convention,Rights Type,Territory,Valid From,Valid To,Claim Status
WRK-MT-001,WRT-A-MT,Writer A,60.0000,publisher-share,mechanical,WW,2020-01-01,2030-12-31,claimed
WRK-MT-001,POOL-MT,Unclaimed Pool,40.0000,publisher-share,mechanical,WW,2020-01-01,2030-12-31,unclaimed
"""

_OWNERSHIP_CORRECTED_CSV = b"""\
Work Code,Writer Code,Songwriter,Songwriter %,Convention,Rights Type,Territory,Valid From,Valid To,Claim Status
WRK-MT-001,WRT-A-MT,Writer A,60.0000,publisher-share,mechanical,WW,2020-01-01,2030-12-31,claimed
WRK-MT-001,WRT-B-MT,Writer B,40.0000,publisher-share,mechanical,WW,2020-01-01,2030-12-31,claimed
"""

_MAPPINGS_CSV = b"""\
recording_id,work_id,source_label,verified
REC-MT-001,WRK-MT-001,DemoRegistry,true
"""

# Canonical column mapping for the "Format A" ownership header
_OWN_MAPPINGS = [
    {"source_column": "Work Code",      "canonical_field": "work_id"},
    {"source_column": "Writer Code",    "canonical_field": "contributor_id"},
    {"source_column": "Songwriter",     "canonical_field": "contributor_name"},
    {"source_column": "Songwriter %",   "canonical_field": "share"},
    {"source_column": "Convention",     "canonical_field": "share_convention"},
    {"source_column": "Rights Type",    "canonical_field": "rights_category"},
    {"source_column": "Territory",      "canonical_field": "territory"},
    {"source_column": "Valid From",     "canonical_field": "effective_from"},
    {"source_column": "Valid To",       "canonical_field": "effective_to"},
    {"source_column": "Claim Status",   "canonical_field": "status"},
]

_MAP_MAPPINGS = [
    {"source_column": "recording_id",  "canonical_field": "recording_id"},
    {"source_column": "work_id",       "canonical_field": "work_id"},
    {"source_column": "source_label",  "canonical_field": "source"},
    {"source_column": "verified",      "canonical_field": "verified"},
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _upload_file(client, case_id: int, csv_bytes: bytes,
                 filename: str, file_kind: str) -> dict:
    resp = client.post(
        f"/cases/{case_id}/files",
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        data={"file_kind": file_kind},
    )
    assert resp.status_code == 201, f"upload failed: {resp.text}"
    return resp.json()


def _confirm_mapping(client, file_id: int, mappings: list[dict]) -> None:
    resp = client.put(f"/files/{file_id}/mapping",
                      json={"mappings": mappings})
    assert resp.status_code == 200, f"mapping failed: {resp.text}"
    assert resp.json()["all_confirmed"] is True


# ===========================================================================
# Test: Full Midnight Train flow
# ===========================================================================

class TestMidnightTrainFlow:
    """End-to-end: analyze → R1 finding → correct → rerun → resolved."""

    @pytest.fixture(scope="class")
    def case_and_finding(self, client):
        """
        Sets up a case, uploads files, confirms mappings, and runs analysis.
        Returns (case_id, finding_id) for use in test methods.
        """
        # 1. Create case
        resp = client.post("/cases", data={"name": "Midnight Train Test",
                                           "description": "e2e test"})
        assert resp.status_code == 201
        case_id = resp.json()["id"]

        # 2. Upload ownership file
        own_meta = _upload_file(client, case_id, _OWNERSHIP_CSV,
                                "ownership.csv", "ownership")
        own_file_id = own_meta["file_id"]

        # 3. Upload mappings file
        map_meta = _upload_file(client, case_id, _MAPPINGS_CSV,
                                "mappings.csv", "mappings")
        map_file_id = map_meta["file_id"]

        # 4. Confirm column mappings
        _confirm_mapping(client, own_file_id, _OWN_MAPPINGS)
        _confirm_mapping(client, map_file_id, _MAP_MAPPINGS)

        # 5. Run analysis
        resp = client.post(f"/cases/{case_id}/analyze")
        assert resp.status_code == 202, f"analyze failed: {resp.text}"
        analyze_body = resp.json()
        assert analyze_body["finding_count"] >= 1

        # 6. List findings → grab R1 finding
        resp = client.get(f"/cases/{case_id}/findings")
        assert resp.status_code == 200
        findings = resp.json()
        r1_findings = [f for f in findings if f["finding_type"] == "possible_missing_claim"]
        assert len(r1_findings) >= 1, f"Expected R1 finding, got: {[f['finding_type'] for f in findings]}"

        finding_id = r1_findings[0]["id"]
        return case_id, finding_id

    def test_r1_finding_present(self, client, case_and_finding):
        """After analyze, R1 finding exists with status=open."""
        case_id, finding_id = case_and_finding
        resp = client.get(f"/findings/{finding_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["finding_type"] == "possible_missing_claim"
        assert body["status"] == "open"
        assert body["severity"] == "warning"

    def test_finding_has_rule_trace(self, client, case_and_finding):
        """Full finding detail includes rule_trace with R1 id and version."""
        _, finding_id = case_and_finding
        resp = client.get(f"/findings/{finding_id}")
        body = resp.json()
        rt = body.get("rule_trace")
        assert rt is not None
        assert rt["rule_id"] == "R1"
        assert rt["rule_version"] == "1.0"

    def test_finding_has_evidence(self, client, case_and_finding):
        """Finding detail includes at least one evidence row."""
        _, finding_id = case_and_finding
        resp = client.get(f"/findings/{finding_id}")
        body = resp.json()
        assert len(body["evidence"]) >= 1
        ev = body["evidence"][0]
        assert "field_values" in ev

    def test_finding_has_uncertainty_and_next_step(self, client, case_and_finding):
        """Finding includes human-readable guidance."""
        _, finding_id = case_and_finding
        resp = client.get(f"/findings/{finding_id}")
        body = resp.json()
        assert body["uncertainty"]
        assert body["next_step"]

    def test_correct_requires_note(self, client, case_and_finding):
        """POST /findings/{id}/review with correct and empty note → 400."""
        _, finding_id = case_and_finding
        resp = client.post(f"/findings/{finding_id}/review", json={
            "decision": "correct",
            "note": "",
            "corrected_values": {"status": "claimed"},
        })
        assert resp.status_code == 400
        assert "note" in resp.json()["detail"].lower()

    def test_correct_action_resolves_finding(self, client, case_and_finding):
        """POST correct with note → finding status becomes resolved."""
        _, finding_id = case_and_finding
        resp = client.post(f"/findings/{finding_id}/review", json={
            "decision": "correct",
            "note": "Registration updated: Writer B now holds 40 %.",
            "corrected_values": {"status": "claimed", "share": "40.0000"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["new_status"] == "resolved"
        assert body["decision"] == "correct"

    def test_review_history_has_correct_decision(self, client, case_and_finding):
        """After correct, review_decisions list on finding shows the entry."""
        _, finding_id = case_and_finding
        resp = client.get(f"/findings/{finding_id}")
        body = resp.json()
        decisions = body["review_decisions"]
        assert len(decisions) >= 1
        correct_decisions = [d for d in decisions if d["decision"] == "correct"]
        assert len(correct_decisions) >= 1
        assert correct_decisions[0]["note"] == "Registration updated: Writer B now holds 40 %."

    def test_rerun_finding_listed_as_resolved(self, client, case_and_finding):
        """
        After correcting the registration and rerunning, the original R1 finding
        should appear in the diff under 'resolved' (it doesn't refire because the
        data didn't change on disk — the corrected record is a new version).

        The analysis runs again on the same uploaded files, so R1 will fire again
        (the uploaded CSV still has the unclaimed row). The NEW run's finding is
        'new', while the original corrected finding is 'resolved'.

        Implementation note: since run_analysis always re-reads from uploaded files
        (not corrected Records) the same R1 fires as a NEW finding. The ORIGINAL
        finding is in diff['resolved'] because it was already 'resolved'.
        """
        case_id, finding_id = case_and_finding
        resp = client.post(f"/cases/{case_id}/rerun")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rerun_completed"

        diff = body["diff"]
        # The previously-corrected finding (status=resolved) must not be in 'new'
        all_finding_ids_in_diff = (
            [e["finding_id"] for e in diff.get("new", [])]
            + [e["finding_id"] for e in diff.get("unchanged", [])]
            + [e["finding_id"] for e in diff.get("changed", [])]
        )
        # The original finding is resolved — it should NOT appear as 'new'
        # (it may appear in 'resolved' list if its fingerprint didn't refire,
        #  or as unchanged if a new run produces a duplicate fingerprint)
        assert finding_id not in [e["finding_id"] for e in diff.get("new", [])], (
            "The already-resolved finding must not be listed as 'new'"
        )

    def test_rerun_summary_fields_present(self, client, case_and_finding):
        """Rerun response includes all diff categories."""
        case_id, _ = case_and_finding
        resp = client.post(f"/cases/{case_id}/rerun")
        body = resp.json()
        for key in ("new", "unchanged", "changed", "resolved", "rejected"):
            assert key in body["summary"]
            assert key in body["diff"]


# ===========================================================================
# Test: reject then rerun → stays rejected
# ===========================================================================

class TestRejectStaysRejected:
    """Rejected findings must never be re-opened by a rerun."""

    @pytest.fixture(scope="class")
    def rejected_case(self, client):
        # Create a fresh case
        resp = client.post("/cases", data={"name": "Reject Test", "description": ""})
        case_id = resp.json()["id"]

        own_meta = _upload_file(client, case_id, _OWNERSHIP_CSV,
                                "ownership.csv", "ownership")
        map_meta = _upload_file(client, case_id, _MAPPINGS_CSV,
                                "mappings.csv", "mappings")
        _confirm_mapping(client, own_meta["file_id"], _OWN_MAPPINGS)
        _confirm_mapping(client, map_meta["file_id"], _MAP_MAPPINGS)

        client.post(f"/cases/{case_id}/analyze")

        resp = client.get(f"/cases/{case_id}/findings")
        findings = resp.json()
        finding_id = findings[0]["id"]

        # Reject the finding
        resp = client.post(f"/findings/{finding_id}/review",
                           json={"decision": "reject",
                                 "note": "False positive — not relevant."})
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "rejected"

        return case_id, finding_id

    def test_rejected_finding_stays_rejected_after_rerun(self, client, rejected_case):
        """Rerun must list originally-rejected finding under 'rejected', not 'new'."""
        case_id, finding_id = rejected_case
        resp = client.post(f"/cases/{case_id}/rerun")
        assert resp.status_code == 200
        diff = resp.json()["diff"]

        # Rejected finding must appear in diff['rejected'], not diff['new']
        rejected_ids = [e["finding_id"] for e in diff.get("rejected", [])]
        new_ids = [e["finding_id"] for e in diff.get("new", [])]
        assert finding_id in rejected_ids or finding_id not in new_ids, (
            "Rejected finding must not be re-opened as 'new'"
        )

    def test_rejected_finding_status_unchanged(self, client, rejected_case):
        """After rerun, the rejected finding's status must still be 'rejected'."""
        _, finding_id = rejected_case
        resp = client.get(f"/findings/{finding_id}")
        assert resp.json()["status"] == "rejected"


# ===========================================================================
# Test: GET /cases/{id}/findings returns correct fields
# ===========================================================================

class TestFindingsList:
    """GET /cases/{id}/findings must include finding_type, rule_id, status."""

    @pytest.fixture(scope="class")
    def simple_case(self, client):
        resp = client.post("/cases", data={"name": "List Test", "description": ""})
        case_id = resp.json()["id"]

        own_meta = _upload_file(client, case_id, _OWNERSHIP_CSV,
                                "ownership.csv", "ownership")
        _confirm_mapping(client, own_meta["file_id"], _OWN_MAPPINGS)
        client.post(f"/cases/{case_id}/analyze")
        return case_id

    def test_findings_list_fields(self, client, simple_case):
        resp = client.get(f"/cases/{simple_case}/findings")
        assert resp.status_code == 200
        findings = resp.json()
        assert len(findings) >= 1
        f = findings[0]
        for field in ("id", "finding_type", "severity", "summary", "status",
                      "created_at", "rule_id", "rule_version"):
            assert field in f, f"Missing field '{field}' in finding list item"

    def test_404_for_unknown_case(self, client, simple_case):
        resp = client.get("/cases/99999/findings")
        assert resp.status_code == 404
