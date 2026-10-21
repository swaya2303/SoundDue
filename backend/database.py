"""
database.py — SQLAlchemy models + session factory for SoundDue.
DB file: backend/sounddue.db (SQLite).
"""

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sounddue.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    row_count = Column(Integer, nullable=False)
    file_type = Column(String, nullable=False)  # recordings|works|ownership|mappings


class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=False)
    isrc = Column(String, index=True)
    title = Column(String)
    artist = Column(String)
    duration_secs = Column(Integer)
    raw_json = Column(JSON)


class Work(Base):
    __tablename__ = "works"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=False)
    iswc = Column(String, index=True)
    title = Column(String)
    composer = Column(String)
    publisher = Column(String)
    raw_json = Column(JSON)


class OwnershipClaim(Base):
    __tablename__ = "ownership_claims"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=False)
    rights_holder = Column(String)
    work_iswc = Column(String, index=True)
    share_pct = Column(Numeric(7, 4), nullable=False)
    rights_category = Column(String)
    territory = Column(String)
    period_start = Column(String)
    period_end = Column(String)
    raw_json = Column(JSON)


class Mapping(Base):
    __tablename__ = "mappings"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=False)
    recording_isrc = Column(String, index=True)
    work_iswc = Column(String, index=True)
    source_label = Column(String)
    raw_json = Column(JSON)


class MatchCandidate(Base):
    __tablename__ = "match_candidates"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recordings.id"), nullable=False)
    work_id = Column(Integer, ForeignKey("works.id"), nullable=False)
    score = Column(Numeric(5, 4), nullable=False)
    method = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending|accepted|rejected
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String, nullable=False)
    rule_version = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # info|warning|error
    summary = Column(Text, nullable=False)
    evidence_json = Column(JSON)
    status = Column(String, default="open", nullable=False)  # open|resolved
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uncertainty = Column(Text)
    next_step = Column(Text)


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id"), nullable=False)
    action = Column(String, nullable=False)  # accept|reject|note
    actor = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    note = Column(Text)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
