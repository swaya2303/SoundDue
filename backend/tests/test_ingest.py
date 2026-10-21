"""
tests/test_ingest.py — Unit tests for ingest.parse_file and store_batch.
"""

import sys
import os

# Ensure backend/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from ingest import parse_file, store_batch

DEMO_DIR = Path(__file__).parent.parent / "demo_data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# parse_file tests
# ---------------------------------------------------------------------------
class TestParseFile:
    def test_recordings_csv_row_count(self):
        df = parse_file(DEMO_DIR / "recordings.csv", "recordings")
        assert len(df) == 4

    def test_works_csv_row_count(self):
        df = parse_file(DEMO_DIR / "works.csv", "works")
        assert len(df) == 4

    def test_ownership_csv_row_count(self):
        df = parse_file(DEMO_DIR / "ownership.csv", "ownership")
        assert len(df) == 8

    def test_mappings_csv_row_count(self):
        df = parse_file(DEMO_DIR / "mappings.csv", "mappings")
        assert len(df) == 4

    def test_column_normalization_recordings(self):
        df = parse_file(DEMO_DIR / "recordings.csv", "recordings")
        for col in df.columns:
            assert col == col.lower(), f"Column not lowercase: {col!r}"
            assert " " not in col, f"Column contains space: {col!r}"

    def test_column_normalization_ownership(self):
        df = parse_file(DEMO_DIR / "ownership.csv", "ownership")
        expected_cols = {"rights_holder", "work_iswc", "share_pct", "rights_category",
                         "territory", "period_start", "period_end"}
        assert expected_cols.issubset(set(df.columns))

    def test_recordings_isrc_values(self):
        df = parse_file(DEMO_DIR / "recordings.csv", "recordings")
        isrcs = set(df["isrc"].tolist())
        assert "USRC17607839" in isrcs
        assert "USRC17607999" in isrcs

    def test_works_iswc_values(self):
        df = parse_file(DEMO_DIR / "works.csv", "works")
        iswcs = set(df["iswc"].tolist())
        assert "T-034524680-1" in iswcs
        assert "T-034524683-1" in iswcs

    def test_mappings_orphan_isrc(self):
        df = parse_file(DEMO_DIR / "mappings.csv", "mappings")
        isrcs = set(df["recording_isrc"].tolist())
        assert "USRC17607888" in isrcs  # ghost ISRC

    def test_unsupported_extension_raises(self, tmp_path):
        bad_file = tmp_path / "file.txt"
        bad_file.write_text("data")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            parse_file(bad_file, "recordings")


# ---------------------------------------------------------------------------
# store_batch tests
# ---------------------------------------------------------------------------
class TestStoreBatch:
    def test_store_recordings(self, db):
        df = parse_file(DEMO_DIR / "recordings.csv", "recordings")
        batch = store_batch(df, "recordings", "recordings.csv", db)
        assert batch.id is not None
        assert batch.row_count == 4
        assert batch.file_type == "recordings"

    def test_store_works(self, db):
        df = parse_file(DEMO_DIR / "works.csv", "works")
        batch = store_batch(df, "works", "works.csv", db)
        assert batch.row_count == 4

    def test_store_ownership(self, db):
        df = parse_file(DEMO_DIR / "ownership.csv", "ownership")
        batch = store_batch(df, "ownership", "ownership.csv", db)
        assert batch.row_count == 8

    def test_store_mappings(self, db):
        df = parse_file(DEMO_DIR / "mappings.csv", "mappings")
        batch = store_batch(df, "mappings", "mappings.csv", db)
        assert batch.row_count == 4

    def test_invalid_share_pct_raises(self, db, tmp_path):
        import pandas as pd
        bad_csv = tmp_path / "bad_ownership.csv"
        bad_csv.write_text(
            "rights_holder,work_iswc,share_pct,rights_category,territory,period_start,period_end\n"
            "A,T-001,abc,mechanical,WW,2020-01-01,2025-12-31\n"
        )
        df = parse_file(bad_csv, "ownership")
        with pytest.raises(ValueError, match="share_pct must be numeric"):
            store_batch(df, "ownership", "bad.csv", db)

    def test_zero_share_pct_raises(self, db, tmp_path):
        import pandas as pd
        bad_csv = tmp_path / "zero_share.csv"
        bad_csv.write_text(
            "rights_holder,work_iswc,share_pct,rights_category,territory,period_start,period_end\n"
            "A,T-001,0,mechanical,WW,2020-01-01,2025-12-31\n"
        )
        df = parse_file(bad_csv, "ownership")
        with pytest.raises(ValueError, match="share_pct must be between"):
            store_batch(df, "ownership", "zero.csv", db)

    def test_over_100_share_pct_raises(self, db, tmp_path):
        bad_csv = tmp_path / "over_share.csv"
        bad_csv.write_text(
            "rights_holder,work_iswc,share_pct,rights_category,territory,period_start,period_end\n"
            "A,T-001,101,mechanical,WW,2020-01-01,2025-12-31\n"
        )
        df = parse_file(bad_csv, "ownership")
        with pytest.raises(ValueError, match="share_pct must be between"):
            store_batch(df, "ownership", "over.csv", db)

    def test_unknown_file_type_raises(self, db):
        import pandas as pd
        df = pd.DataFrame({"col": ["val"]})
        with pytest.raises(ValueError, match="Unknown file_type"):
            store_batch(df, "invalid_type", "file.csv", db)
