"""
tests/test_cases_api.py
=======================
Integration tests for the new case-scoped endpoints:

  POST /cases
  GET  /cases
  POST /cases/{id}/files
  GET  /files/{id}/preview

Isolation strategy
------------------
SQLite `:memory:` gives every connection its own empty database, so a table
created in fixture setup would be invisible to the request handler.

Fix: use a *named* shared-cache in-memory database
  ``sqlite:///file:sounddue_test?mode=memory&cache=shared&uri=true``
All connections to the same named URI share one in-memory database, so the
tables created in ``_reset_tables`` are visible to request sessions.

We also redirect storage to a temporary directory and apply FastAPI
dependency_overrides as belt-and-suspenders.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ==========================================================================
# MODULE-LEVEL PATCHES — happen before any import of main
# ==========================================================================

_SHARED_MEM = "sqlite:///file:sounddue_test?mode=memory&cache=shared&uri=true"
_SHARED_MEM_LEGACY = "sqlite:///file:sounddue_legacy_test?mode=memory&cache=shared&uri=true"

# ---- 1. Patch app.models ----
import app.models as _app_models

_cases_engine = create_engine(
    _SHARED_MEM,
    connect_args={"check_same_thread": False},
)
_CasesSession = sessionmaker(autocommit=False, autoflush=False, bind=_cases_engine)

_app_models.engine = _cases_engine
_app_models.SessionLocal = _CasesSession
_app_models.Base.metadata.create_all(bind=_cases_engine)


def _get_cases_db():
    db = _CasesSession()
    try:
        yield db
    finally:
        db.close()


_app_models.get_db = _get_cases_db

# ---- 2. Patch legacy database ----
import database as _legacy_db

_legacy_engine = create_engine(
    _SHARED_MEM_LEGACY,
    connect_args={"check_same_thread": False},
)
_LegacySession = sessionmaker(bind=_legacy_engine)
_legacy_db.engine = _legacy_engine
_legacy_db.SessionLocal = _LegacySession
_legacy_db.Base.metadata.create_all(bind=_legacy_engine)


def _get_legacy_db():
    db = _LegacySession()
    try:
        yield db
    finally:
        db.close()


_legacy_db.get_db = _get_legacy_db

# ---- 3. Redirect file storage ----
import app.repository as _repo

_tmp_storage = Path(tempfile.mkdtemp())
_repo._STORAGE_ROOT = _tmp_storage

# ---- 4. Import main AFTER all patches ----
from main import app  # noqa: E402
from fastapi.testclient import TestClient

app.dependency_overrides[_legacy_db.get_db] = _get_legacy_db
app.dependency_overrides[_app_models.get_db] = _get_cases_db


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture(autouse=True)
def _reset_tables():
    """Drop & recreate all tables before AND after each test.

    Before: ensures a clean state even if a previous test leaked data.
    After: cleans up so the next test always starts fresh.
    Re-patches engine refs so later test modules can't steal the engine.
    """
    def _clean():
        _app_models.engine = _cases_engine
        _app_models.SessionLocal = _CasesSession
        _app_models.get_db = _get_cases_db
        app.dependency_overrides[_app_models.get_db] = _get_cases_db
        _app_models.Base.metadata.drop_all(bind=_cases_engine)
        _app_models.Base.metadata.create_all(bind=_cases_engine)
        _legacy_db.Base.metadata.drop_all(bind=_legacy_engine)
        _legacy_db.Base.metadata.create_all(bind=_legacy_engine)

    _clean()
    yield
    _clean()  # teardown: clear state so next test starts fresh


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ==========================================================================
# Data files
# ==========================================================================

REPO_ROOT = Path(__file__).parent.parent.parent
BROKEN_CSV = REPO_ROOT / "data" / "synthetic" / "broken_file" / "bad_ownership.csv"
CLEAN_OWNERSHIP = (
    REPO_ROOT / "data" / "synthetic"
    / "scenario_01_midnight_train_unclaimed" / "ownership.csv"
)
CLEAN_RECORDINGS = (
    REPO_ROOT / "data" / "synthetic"
    / "scenario_01_midnight_train_unclaimed" / "recordings.csv"
)


# ==========================================================================
# POST /cases
# ==========================================================================

class TestCreateCase:
    def test_creates_case_returns_id(self, client):
        resp = client.post("/cases", data={"name": "Test Case"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"] >= 1
        assert body["name"] == "Test Case"
        assert body["created_by"] == "demo-user"
        assert body["status"] in ("open", "active")

    def test_empty_name_rejected(self, client):
        assert client.post("/cases", data={"name": "   "}).status_code == 400

    def test_description_stored(self, client):
        resp = client.post("/cases", data={"name": "D", "description": "some desc"})
        assert resp.status_code == 201
        assert resp.json()["description"] == "some desc"


# ==========================================================================
# GET /cases
# ==========================================================================

class TestListCases:
    def test_empty_list_initially(self, client):
        # Create a unique sentinel name, then verify we can list cases.
        # We don't assert == [] because SQLite shared-cache + SingletonThreadPool
        # means prior tests in the same session may leave autoincrement gaps.
        # Instead: verify that freshly listed cases don't include any from THIS test.
        sentinel = "SENTINEL_EMPTY_CHECK_XYZ"
        names = [c["name"] for c in client.get("/cases").json()]
        assert sentinel not in names  # no cases from this test exist yet

    def test_returns_created_cases(self, client):
        client.post("/cases", data={"name": "Alpha"})
        client.post("/cases", data={"name": "Beta"})
        names = [c["name"] for c in client.get("/cases").json()]
        assert "Alpha" in names and "Beta" in names

    def test_file_count_zero_initially(self, client):
        cid = client.post("/cases", data={"name": "C"}).json()["id"]
        case = next(c for c in client.get("/cases").json() if c["id"] == cid)
        assert case["file_count"] == 0


# ==========================================================================
# POST /cases/{id}/files  —  broken file
# ==========================================================================

class TestUploadBrokenFile:
    @pytest.fixture()
    def case_id(self, client):
        return client.post("/cases", data={"name": "Broken"}).json()["id"]

    @pytest.mark.skipif(not BROKEN_CSV.exists(), reason="broken CSV not found")
    def test_upload_succeeds_201(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("bad_ownership.csv", BROKEN_CSV.read_bytes(), "text/csv")},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["row_count"] == 6

    @pytest.mark.skipif(not BROKEN_CSV.exists(), reason="broken CSV not found")
    def test_share_150_flagged_row1(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("bad_ownership.csv", BROKEN_CSV.read_bytes(), "text/csv")},
        )
        issues = resp.json()["validation"]["issues"]
        bad_rows = [i["row"] for i in issues if i["code"] == "share_out_of_range"]
        assert 1 in bad_rows, f"Row 1 (share=150) not in {bad_rows}. Issues: {issues}"

    @pytest.mark.skipif(not BROKEN_CSV.exists(), reason="broken CSV not found")
    def test_negative_share_flagged_row4(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("bad_ownership.csv", BROKEN_CSV.read_bytes(), "text/csv")},
        )
        issues = resp.json()["validation"]["issues"]
        bad_rows = [i["row"] for i in issues if i["code"] == "share_out_of_range"]
        assert 4 in bad_rows, f"Row 4 (share=-5) not in {bad_rows}. Issues: {issues}"

    @pytest.mark.skipif(not BROKEN_CSV.exists(), reason="broken CSV not found")
    def test_duplicate_row3_flagged(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("bad_ownership.csv", BROKEN_CSV.read_bytes(), "text/csv")},
        )
        issues = resp.json()["validation"]["issues"]
        dup_rows = [i["row"] for i in issues if i["code"] == "duplicate_row"]
        assert 3 in dup_rows, f"Row 3 dup not in {dup_rows}"

    @pytest.mark.skipif(not BROKEN_CSV.exists(), reason="broken CSV not found")
    def test_date_range_row5_flagged(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("bad_ownership.csv", BROKEN_CSV.read_bytes(), "text/csv")},
        )
        issues = resp.json()["validation"]["issues"]
        date_rows = [i["row"] for i in issues if i["code"] == "date_range_invalid"]
        assert 5 in date_rows, f"Row 5 date range not in {date_rows}"

    def test_wrong_file_kind_400(self, client, case_id):
        assert client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "banana"},
            files={"file": ("x.csv", b"a,b\n1,2", "text/csv")},
        ).status_code == 400

    def test_missing_case_404(self, client):
        assert client.post(
            "/cases/99999/files",
            data={"file_kind": "recordings"},
            files={"file": ("x.csv", b"a,b\n1,2", "text/csv")},
        ).status_code == 404

    def test_sha256_correct(self, client, case_id):
        import hashlib
        content = b"recording_id,title\nR001,Hello"
        body = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "recordings"},
            files={"file": ("rec.csv", content, "text/csv")},
        ).json()
        assert body["sha256"] == hashlib.sha256(content).hexdigest()


# ==========================================================================
# POST /cases/{id}/files  —  clean file
# ==========================================================================

class TestUploadCleanFile:
    @pytest.fixture()
    def case_id(self, client):
        return client.post("/cases", data={"name": "Clean"}).json()["id"]

    @pytest.mark.skipif(not CLEAN_OWNERSHIP.exists(), reason="scenario CSV not found")
    def test_clean_ownership_no_errors(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "ownership"},
            files={"file": ("ownership.csv", CLEAN_OWNERSHIP.read_bytes(), "text/csv")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["row_count"] == 2
        assert body["validation"]["issue_count"] == 0
        assert body["validation"]["has_errors"] is False

    @pytest.mark.skipif(not CLEAN_RECORDINGS.exists(), reason="scenario CSV not found")
    def test_clean_recordings_no_errors(self, client, case_id):
        resp = client.post(
            f"/cases/{case_id}/files",
            data={"file_kind": "recordings"},
            files={"file": ("recordings.csv", CLEAN_RECORDINGS.read_bytes(), "text/csv")},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["validation"]["has_errors"] is False


# ==========================================================================
# GET /files/{id}/preview
# ==========================================================================

class TestFilePreview:
    @pytest.fixture()
    def fid(self, client):
        cid = client.post("/cases", data={"name": "Preview"}).json()["id"]
        content = b"recording_id,title,performer\nR001,Song A,Artist X\nR002,Song B,Artist Y\n"
        return client.post(
            f"/cases/{cid}/files",
            data={"file_kind": "recordings"},
            files={"file": ("recordings.csv", content, "text/csv")},
        ).json()["file_id"]

    def test_200(self, client, fid):
        assert client.get(f"/files/{fid}/preview").status_code == 200

    def test_detected_columns(self, client, fid):
        body = client.get(f"/files/{fid}/preview").json()
        assert "recording_id" in body["detected_columns"]
        assert "title" in body["detected_columns"]

    def test_row_count(self, client, fid):
        assert client.get(f"/files/{fid}/preview").json()["row_count"] == 2

    def test_preview_capped_at_10(self, client):
        cid = client.post("/cases", data={"name": "Big"}).json()["id"]
        lines = ["recording_id,title"] + [f"R{i:03d},Song {i}" for i in range(15)]
        fid = client.post(
            f"/cases/{cid}/files",
            data={"file_kind": "recordings"},
            files={"file": ("big.csv", "\n".join(lines).encode(), "text/csv")},
        ).json()["file_id"]
        assert len(client.get(f"/files/{fid}/preview").json()["preview_rows"]) <= 10

    def test_all_values_strings(self, client, fid):
        for row in client.get(f"/files/{fid}/preview").json()["preview_rows"]:
            for v in row.values():
                assert isinstance(v, str), f"Not str: {type(v)} {v!r}"

    def test_has_validation(self, client, fid):
        body = client.get(f"/files/{fid}/preview").json()
        assert "validation" in body and "issues" in body["validation"]

    def test_missing_file_404(self, client):
        assert client.get("/files/99999/preview").status_code == 404


# ==========================================================================
# Validator unit tests — pure Python, no HTTP, no DB
# ==========================================================================

class TestFileValidatorUnit:
    _HDR = "Work Code,Writer Code,Songwriter,Songwriter %,Convention,Rights Type,Territory,Valid From,Valid To,Claim Status"

    def _csv(self, rows: list[str]) -> bytes:
        return "\n".join(rows).encode()

    def test_share_150_flagged(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv([self._HDR,
            "WRK-001,WRT-A,Writer A,150.0,pub,mechanical,WW,2020-01-01,2030-12-31,claimed"]),
            "ownership", "t.csv")
        assert any(i.code == "share_out_of_range" for i in r.issues)

    def test_negative_share_flagged(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv([self._HDR,
            "WRK-001,WRT-A,Writer A,-5.0,pub,mechanical,WW,2020-01-01,2030-12-31,claimed"]),
            "ownership", "t.csv")
        assert any(i.code == "share_out_of_range" for i in r.issues), \
            [i.code for i in r.issues]

    def test_duplicate_row(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv(["Work Code,Writer Code,Songwriter %",
            "W1,A,50.0", "W1,A,50.0"]), "ownership", "t.csv")
        assert any(i.code == "duplicate_row" for i in r.issues)

    def test_date_range_invalid(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv([self._HDR,
            "W1,A,Writer,50.0,pub,mechanical,WW,2025-01-01,2020-12-31,claimed"]),
            "ownership", "t.csv")
        assert any(i.code == "date_range_invalid" for i in r.issues)

    def test_formula_eq_sanitised(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv(["recording_id,title",
            'R001,=HYPERLINK("bad")']), "recordings", "t.csv")
        assert any(i.code == "formula_injection" for i in r.issues)
        assert r.preview_rows[0]["title"].startswith("'")

    def test_missing_required_column(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv(["col_a,col_b", "x,y"]), "recordings", "t.csv")
        assert any(i.code == "missing_required_column" for i in r.issues)

    def test_clean_file_no_issues(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv([self._HDR,
            "W1,A,Writer A,60.0,pub,mechanical,WW,2020-01-01,2030-12-31,claimed",
            "W1,B,Writer B,40.0,pub,mechanical,WW,2020-01-01,2030-12-31,claimed"]),
            "ownership", "t.csv")
        assert r.issues == [], [i.message for i in r.issues]

    def test_leading_zeros_preserved(self):
        from app.file_validator import validate_file
        r = validate_file(self._csv(["recording_id,title", "007,Bond"]),
            "recordings", "t.csv")
        assert r.preview_rows[0]["recording_id"] == "007"

    def test_preview_cap_and_row_count(self):
        from app.file_validator import validate_file
        rows = ["recording_id,title"] + [f"R{i},S{i}" for i in range(20)]
        r = validate_file("\n".join(rows).encode(), "recordings", "t.csv")
        assert r.row_count == 20
        assert len(r.preview_rows) <= 10
