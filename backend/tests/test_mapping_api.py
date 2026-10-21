"""
tests/test_mapping_api.py
=========================
Tests for:
  GET  /files/{file_id}/mapping/suggestions
  PUT  /files/{file_id}/mapping
  POST /cases/{case_id}/analyze

Also unit-tests for column_mapper.suggest_column.

Uses the shared-cache SQLite pattern required for FastAPI TestClient +
SQLAlchemy sessions that span multiple connections.
"""
from __future__ import annotations

import io
import sys
import os

import pytest

# ---------------------------------------------------------------------------
# DB isolation setup — MUST happen before importing main
# ---------------------------------------------------------------------------
import app.models as _app_models
import database as _legacy_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TEST_DB_URI = (
    "sqlite:///file:sounddue_maptest?mode=memory&cache=shared&uri=true"
)
_cases_engine = create_engine(
    _TEST_DB_URI,
    connect_args={"check_same_thread": False},
    echo=False,
)
_CasesSession = sessionmaker(bind=_cases_engine, autocommit=False, autoflush=False)
_app_models.Base.metadata.create_all(bind=_cases_engine)
_app_models.engine = _cases_engine
_app_models.SessionLocal = _CasesSession


def _get_cases_db_override():
    db = _CasesSession()
    try:
        yield db
    finally:
        db.close()


_app_models.get_db = _get_cases_db_override  # patch before main import

# Legacy DB (in-memory too)
_LEGACY_URI = "sqlite:///file:sounddue_maptest_legacy?mode=memory&cache=shared&uri=true"
_legacy_engine = create_engine(
    _LEGACY_URI,
    connect_args={"check_same_thread": False},
    echo=False,
)
_LegacySession = sessionmaker(bind=_legacy_engine, autocommit=False, autoflush=False)
_legacy_db.engine = _legacy_engine
_legacy_db.SessionLocal = _LegacySession


def _get_legacy_db_override():
    db = _LegacySession()
    try:
        yield db
    finally:
        db.close()


# Now safe to import main
from main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app.dependency_overrides[_legacy_db.get_db] = _get_legacy_db_override
app.dependency_overrides[_app_models.get_db] = _get_cases_db_override

client = TestClient(app)


# ---------------------------------------------------------------------------
# Autouse fixture — reset tables between tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_tables():
    _app_models.engine = _cases_engine
    _app_models.SessionLocal = _CasesSession
    _app_models.get_db = _get_cases_db_override
    app.dependency_overrides[_app_models.get_db] = _get_cases_db_override
    _app_models.Base.metadata.drop_all(bind=_cases_engine)
    _app_models.Base.metadata.create_all(bind=_cases_engine)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_RECORDINGS_CSV = (
    "Track Code,Track Title,Main Artist,Version,Secs,ISRC Code\r\n"
    "REC-001,Midnight Train,Artist A,Original,214,\r\n"
    "REC-002,Golden Hour,Artist B,Acoustic,198,\r\n"
)

_OWNERSHIP_CSV = (
    "Work Code,Writer Code,Songwriter,Songwriter %,Convention,Rights Type,"
    "Territory,Valid From,Valid To,Claim Status\r\n"
    "WRK-001,WRT-A,Writer A,60.0000,publisher-share,mechanical,WW,"
    "2020-01-01,2030-12-31,claimed\r\n"
)


def _create_case(name: str = "Test Case") -> int:
    r = client.post("/cases", data={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload_file(case_id: int, csv_text: str, file_kind: str, filename: str) -> int:
    r = client.post(
        f"/cases/{case_id}/files",
        data={"file_kind": file_kind},
        files={"file": (filename, io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()["file_id"]


# ---------------------------------------------------------------------------
# column_mapper unit tests
# ---------------------------------------------------------------------------
class TestSuggestColumn:
    def test_track_code_exact(self):
        from app.column_mapper import suggest_column
        s = suggest_column("Track Code")
        assert s.best_canonical == "recording_id"
        assert s.method == "synonym_exact"
        assert s.score == 1.0

    def test_songwriter_pct_exact(self):
        from app.column_mapper import suggest_column
        s = suggest_column("Songwriter %")
        assert s.best_canonical == "share"
        assert s.method == "synonym_exact"

    def test_case_insensitive(self):
        from app.column_mapper import suggest_column
        s = suggest_column("TRACK CODE")
        assert s.best_canonical == "recording_id"

    def test_fuzzy_match(self):
        from app.column_mapper import suggest_column
        # "Trak Code" should fuzzy-match to recording_id
        s = suggest_column("Trak Code")
        assert s.best_canonical == "recording_id"
        assert s.method == "rapidfuzz"

    def test_unknown_column_returns_none(self):
        from app.column_mapper import suggest_column
        s = suggest_column("zzz_completely_unknown_xyz_123")
        assert s.best_canonical is None
        assert s.method == "none"

    def test_work_code_exact(self):
        from app.column_mapper import suggest_column
        s = suggest_column("Work Code")
        assert s.best_canonical == "work_id"

    def test_isrc_code_exact(self):
        from app.column_mapper import suggest_column
        s = suggest_column("ISRC Code")
        # "isrc code" → isrc (prefer isrc over recording_id)
        assert s.best_canonical in ("isrc", "recording_id")

    def test_suggest_all_columns(self):
        from app.column_mapper import suggest_all_columns
        cols = ["Track Code", "Songwriter %", "Territory"]
        results = suggest_all_columns(cols)
        assert len(results) == 3
        assert results[0].best_canonical == "recording_id"
        assert results[1].best_canonical == "share"
        assert results[2].best_canonical == "territory"


# ---------------------------------------------------------------------------
# GET /files/{file_id}/mapping/suggestions
# ---------------------------------------------------------------------------
class TestGetMappingSuggestions:
    def test_returns_suggestions_for_recordings(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        r = client.get(f"/files/{fid}/mapping/suggestions")
        assert r.status_code == 200
        data = r.json()
        assert data["file_id"] == fid
        assert data["file_kind"] == "recordings"
        assert "Track Code" in [s["source_column"] for s in data["suggestions"]]

    def test_track_code_maps_to_recording_id(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        r = client.get(f"/files/{fid}/mapping/suggestions")
        suggestions = {s["source_column"]: s for s in r.json()["suggestions"]}
        tc = suggestions["Track Code"]
        assert tc["best_canonical"] == "recording_id"
        assert tc["method"] == "synonym_exact"

    def test_songwriter_pct_maps_to_share(self):
        cid = _create_case()
        fid = _upload_file(cid, _OWNERSHIP_CSV, "ownership", "ownership.csv")
        r = client.get(f"/files/{fid}/mapping/suggestions")
        suggestions = {s["source_column"]: s for s in r.json()["suggestions"]}
        assert suggestions["Songwriter %"]["best_canonical"] == "share"
        assert suggestions["Songwriter %"]["method"] == "synonym_exact"

    def test_required_fields_returned(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        data = client.get(f"/files/{fid}/mapping/suggestions").json()
        assert "recording_id" in data["required_fields"]
        assert "title" in data["required_fields"]

    def test_all_confirmed_true_when_exact_synonyms_match(self):
        # GET /mapping/suggestions now auto-confirms exact synonym matches on first load.
        # recordings.csv has "Track Code" → recording_id and "Track Title" → title,
        # both of which are exact synonyms. So all_confirmed should be True immediately.
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        data = client.get(f"/files/{fid}/mapping/suggestions").json()
        assert data["all_confirmed"] is True

    def test_404_for_missing_file(self):
        r = client.get("/files/99999/mapping/suggestions")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PUT /files/{file_id}/mapping
# ---------------------------------------------------------------------------
class TestPutMapping:
    def test_confirm_mappings_returns_200(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        body = {
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        }
        r = client.put(f"/files/{fid}/mapping", json=body)
        assert r.status_code == 200
        data = r.json()
        confirmed = {m["source_column"]: m["canonical_field"] for m in data["confirmed_mappings"]}
        assert confirmed["Track Code"] == "recording_id"
        assert confirmed["Track Title"] == "title"

    def test_all_confirmed_true_when_required_covered(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        body = {
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        }
        r = client.put(f"/files/{fid}/mapping", json=body)
        assert r.json()["all_confirmed"] is True

    def test_all_confirmed_false_when_partial(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        body = {
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                # Missing title mapping
            ]
        }
        r = client.put(f"/files/{fid}/mapping", json=body)
        assert r.json()["all_confirmed"] is False

    def test_get_shows_all_confirmed_after_put(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        body = {
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        }
        client.put(f"/files/{fid}/mapping", json=body)
        data = client.get(f"/files/{fid}/mapping/suggestions").json()
        assert data["all_confirmed"] is True

    def test_upsert_updates_existing_mapping(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        # First confirm with wrong mapping
        client.put(f"/files/{fid}/mapping", json={
            "mappings": [{"source_column": "Track Code", "canonical_field": "isrc"}]
        })
        # Then correct it
        client.put(f"/files/{fid}/mapping", json={
            "mappings": [{"source_column": "Track Code", "canonical_field": "recording_id"}]
        })
        data = client.get(f"/files/{fid}/mapping/suggestions").json()
        confirmed = {m["source_column"]: m["canonical_field"] for m in data["confirmed_mappings"]}
        # Should now be recording_id, not isrc
        assert confirmed["Track Code"] == "recording_id"

    def test_empty_mappings_returns_400(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        r = client.put(f"/files/{fid}/mapping", json={"mappings": []})
        assert r.status_code == 400

    def test_404_for_missing_file(self):
        r = client.put("/files/99999/mapping", json={
            "mappings": [{"source_column": "X", "canonical_field": "recording_id"}]
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/analyze
# ---------------------------------------------------------------------------
class TestAnalyze:
    def test_blocked_with_no_files(self):
        cid = _create_case()
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 422
        data = r.json()["detail"]
        assert "No files" in data["message"]

    def test_blocked_when_no_mappings_confirmed(self):
        cid = _create_case()
        _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "Mappings must be confirmed" in detail["message"]
        assert len(detail["unconfirmed"]) == 1
        assert "recording_id" in detail["unconfirmed"][0]["missing_fields"]

    def test_blocked_when_only_partial_mappings(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        # Only confirm recording_id, not title
        client.put(f"/files/{fid}/mapping", json={
            "mappings": [{"source_column": "Track Code", "canonical_field": "recording_id"}]
        })
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 422
        detail = r.json()["detail"]
        missing = detail["unconfirmed"][0]["missing_fields"]
        assert "title" in missing
        assert "recording_id" not in missing  # already confirmed

    def test_accepted_when_all_mappings_confirmed(self):
        cid = _create_case()
        fid = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        client.put(f"/files/{fid}/mapping", json={
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        })
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 202
        data = r.json()
        assert data["status"] == "completed"

    def test_accepted_when_multiple_files_all_confirmed(self):
        cid = _create_case()
        # Upload recordings file
        fid1 = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        client.put(f"/files/{fid1}/mapping", json={
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        })
        # Upload ownership file
        fid2 = _upload_file(cid, _OWNERSHIP_CSV, "ownership", "ownership.csv")
        client.put(f"/files/{fid2}/mapping", json={
            "mappings": [
                {"source_column": "Work Code", "canonical_field": "work_id"},
                {"source_column": "Songwriter %", "canonical_field": "share"},
            ]
        })
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 202

    def test_blocked_when_one_of_two_files_unconfirmed(self):
        cid = _create_case()
        fid1 = _upload_file(cid, _RECORDINGS_CSV, "recordings", "recordings.csv")
        client.put(f"/files/{fid1}/mapping", json={
            "mappings": [
                {"source_column": "Track Code", "canonical_field": "recording_id"},
                {"source_column": "Track Title", "canonical_field": "title"},
            ]
        })
        # Upload ownership file but don't confirm it
        _upload_file(cid, _OWNERSHIP_CSV, "ownership", "ownership.csv")
        r = client.post(f"/cases/{cid}/analyze")
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert len(detail["unconfirmed"]) == 1
        assert detail["unconfirmed"][0]["file_kind"] == "ownership"

    def test_404_for_missing_case(self):
        r = client.post("/cases/99999/analyze")
        assert r.status_code == 404
