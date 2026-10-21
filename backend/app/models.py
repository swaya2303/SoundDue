"""
backend/app/models.py
=====================
SQLAlchemy ORM models for the full SoundDue data model.

Design decisions
----------------
- All new tables live here; the legacy ``database.py`` tables (recordings,
  works, etc.) are left intact so existing endpoints keep working.
- Every table that touches business data is scoped to a ``Case``.
- ``Record`` has an append-only versioning chain: ``supersedes_id`` points to
  the row being replaced.  Nothing is ever updated or deleted.
- ``AuditEvent`` is append-only by convention: no UPDATE/DELETE allowed on
  that table.  The repository enforces this; there is no DB-level constraint
  (prototype shortcut).
- Uploaded files are stored under ``./storage/{case_id}/{filename}`` and
  their SHA-256 hash is recorded so re-uploads can be detected.
- ``MatchCandidate.field_scores`` and ``.reasons`` are JSON columns so the
  rule engine can embed arbitrary per-field detail without a schema change.
- ``Finding``, ``Evidence``, and ``RuleTrace`` form a 1-to-many chain:
  one Finding owns many Evidence rows and one RuleTrace row.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Engine — separate DB file so legacy database.py is undisturbed
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_ROOT = os.path.join(BASE_DIR, "..", "storage")
DB_PATH = os.path.join(BASE_DIR, "..", "sounddue_cases.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    """UTC-aware now(); utcnow() is deprecated in Python 3.12+."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------
class Case(Base):
    """
    Top-level container for a reconciliation exercise.

    Every uploaded file, record, finding, and decision belongs to exactly
    one Case.  Cases are created by the demo user and never deleted.
    """

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False, default="demo-user")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    status = Column(
        String(30), nullable=False, default="open"
    )  # open | closed | archived

    uploaded_files = relationship("UploadedFile", back_populates="case", lazy="dynamic")
    records = relationship("Record", back_populates="case", lazy="dynamic")
    findings = relationship("Finding", back_populates="case", lazy="dynamic")
    audit_events = relationship("AuditEvent", back_populates="case", lazy="dynamic")


# ---------------------------------------------------------------------------
# UploadedFile
# ---------------------------------------------------------------------------
class UploadedFile(Base):
    """
    Tracks every file uploaded to a case.

    ``sha256`` allows the repository to skip re-ingestion when the same
    file is uploaded twice.  ``storage_path`` is relative to the repo root
    so the project can be moved without breaking references.
    """

    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    original_name = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)  # relative: storage/{case_id}/…
    sha256 = Column(String(64), nullable=False, index=True)
    file_type = Column(
        String(30), nullable=False
    )  # recordings | works | ownership | mappings
    uploaded_by = Column(String(100), nullable=False, default="demo-user")
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    row_count = Column(Integer, nullable=True)

    case = relationship("Case", back_populates="uploaded_files")
    column_mappings = relationship(
        "ColumnMapping", back_populates="uploaded_file", lazy="dynamic"
    )
    records = relationship("Record", back_populates="source_file", lazy="dynamic")


# ---------------------------------------------------------------------------
# ColumnMapping
# ---------------------------------------------------------------------------
class ColumnMapping(Base):
    """
    Records how a source-file column was mapped to a canonical schema field.

    ``confirmed`` is set to True once a human (or auto-mapper) has verified
    the mapping.  Unconfirmed mappings are applied tentatively and flagged in
    the UI.
    """

    __tablename__ = "column_mappings"
    __table_args__ = (
        UniqueConstraint(
            "uploaded_file_id", "source_column", name="uq_colmap_file_col"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uploaded_file_id = Column(
        Integer, ForeignKey("uploaded_files.id"), nullable=False, index=True
    )
    source_column = Column(String(255), nullable=False)  # e.g. "Songwriter %"
    canonical_field = Column(String(100), nullable=False)  # e.g. "share"
    confirmed = Column(Boolean, nullable=False, default=False)
    mapped_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    uploaded_file = relationship("UploadedFile", back_populates="column_mappings")


# ---------------------------------------------------------------------------
# Record  (versioned, append-only)
# ---------------------------------------------------------------------------
class Record(Base):
    """
    A single normalised data row from an uploaded file.

    Versioning is append-only: when a record is corrected, a new ``Record``
    row is inserted with ``supersedes_id`` pointing at the row being replaced.
    The old row is never touched.  The current version of any record is the
    one with no row pointing at it via ``supersedes_id``.

    ``normalised_json`` holds the canonical field values after synonym mapping
    and type coercion.  ``raw_json`` is the original cell values.
    """

    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    record_type = Column(
        String(30), nullable=False
    )  # recording | work | ownership | mapping
    normalised_json = Column(JSON, nullable=False)
    raw_json = Column(JSON, nullable=False)
    source_file_id = Column(
        Integer, ForeignKey("uploaded_files.id"), nullable=True, index=True
    )
    source_row = Column(Integer, nullable=True)  # 1-based row number in source file
    version = Column(Integer, nullable=False, default=1)
    supersedes_id = Column(
        Integer, ForeignKey("records.id"), nullable=True, index=True
    )  # NULL = first version
    created_by = Column(String(100), nullable=False, default="demo-user")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    case = relationship("Case", back_populates="records")
    source_file = relationship("UploadedFile", back_populates="records")
    supersedes = relationship("Record", remote_side="Record.id", foreign_keys=[supersedes_id])

    # Convenience: all records that supersede this one (0 or 1 in practice)
    superseded_by = relationship(
        "Record",
        foreign_keys="Record.supersedes_id",
        back_populates="supersedes",
    )


# ---------------------------------------------------------------------------
# MatchCandidate
# ---------------------------------------------------------------------------
class MatchCandidate(Base):
    """
    A proposed link between two Record rows (left ↔ right).

    ``field_scores`` is a JSON object with per-field fuzzy scores, e.g.
    ``{"title": 0.92, "isrc": 1.0}``.
    ``reasons`` is a list of human-readable strings explaining the match.
    ``status`` starts as "pending" and is set by a reviewer.
    Rejected candidates remain rejected on re-run (the engine checks this).
    """

    __tablename__ = "match_candidates"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    left_record_id = Column(
        Integer, ForeignKey("records.id"), nullable=False, index=True
    )
    right_record_id = Column(
        Integer, ForeignKey("records.id"), nullable=False, index=True
    )
    score = Column(Numeric(6, 5), nullable=False)  # 0.00000–1.00000
    field_scores = Column(JSON, nullable=True)      # {"title": 0.92, "isrc": 1.0}
    reasons = Column(JSON, nullable=True)           # ["ISRC exact match", …]
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending | accepted | rejected
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    left_record = relationship("Record", foreign_keys=[left_record_id])
    right_record = relationship("Record", foreign_keys=[right_record_id])


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------
class Finding(Base):
    """
    A single reconciliation issue produced by a rule.

    Each Finding has exactly one RuleTrace and zero-or-more Evidence rows.
    ``status`` lifecycle: open → resolved | rejected.
    """

    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    finding_type = Column(String(60), nullable=False)   # e.g. "share_gap"
    severity = Column(String(20), nullable=False)       # info | warning | error
    summary = Column(Text, nullable=False)
    uncertainty = Column(Text, nullable=True)
    next_step = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open|resolved|rejected
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    case = relationship("Case", back_populates="findings")
    evidence = relationship("Evidence", back_populates="finding", lazy="dynamic")
    rule_trace = relationship(
        "RuleTrace", back_populates="finding", uselist=False
    )
    review_decisions = relationship(
        "ReviewDecision", back_populates="finding", lazy="dynamic"
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
class Evidence(Base):
    """
    A single piece of supporting evidence attached to a Finding.

    ``source_record_id`` pins the evidence to a specific Record row so
    the reviewer can trace it back to the original file and row number.
    ``field_values`` is the specific field values that triggered the rule.
    """

    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(
        Integer, ForeignKey("findings.id"), nullable=False, index=True
    )
    source_record_id = Column(
        Integer, ForeignKey("records.id"), nullable=True, index=True
    )
    source_file_id = Column(
        Integer, ForeignKey("uploaded_files.id"), nullable=True
    )
    source_row = Column(Integer, nullable=True)
    field_values = Column(JSON, nullable=True)   # {"share_pct": "80.0", …}
    note = Column(Text, nullable=True)

    finding = relationship("Finding", back_populates="evidence")
    source_record = relationship("Record", foreign_keys=[source_record_id])


# ---------------------------------------------------------------------------
# RuleTrace
# ---------------------------------------------------------------------------
class RuleTrace(Base):
    """
    Full audit trail of the rule evaluation that produced a Finding.

    One-to-one with Finding.  Stored separately so the Finding table stays
    narrow while the trace can be arbitrarily detailed.
    """

    __tablename__ = "rule_traces"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(
        Integer, ForeignKey("findings.id"), nullable=False, unique=True, index=True
    )
    rule_id = Column(String(30), nullable=False)       # e.g. "RULE-001"
    rule_version = Column(String(10), nullable=False)  # e.g. "1.0"
    matched_conditions = Column(JSON, nullable=True)   # list[str]
    supporting_record_ids = Column(JSON, nullable=True)  # list[int]
    missing_information = Column(JSON, nullable=True)  # list[str]
    conflicting_information = Column(JSON, nullable=True)  # list[str]
    evaluated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    finding = relationship("Finding", back_populates="rule_trace")


# ---------------------------------------------------------------------------
# ReviewDecision
# ---------------------------------------------------------------------------
class ReviewDecision(Base):
    """
    A human reviewer's decision on a Finding or MatchCandidate.

    Append-only: corrections create a new row, never update the old one.
    ``target_type`` distinguishes what was reviewed: "finding" | "candidate".
    ``corrected_values`` stores the reviewer's corrections as JSON.
    """

    __tablename__ = "review_decisions"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(
        Integer, ForeignKey("findings.id"), nullable=True, index=True
    )
    candidate_id = Column(
        Integer, ForeignKey("match_candidates.id"), nullable=True, index=True
    )
    target_type = Column(String(20), nullable=False)   # finding | candidate
    decision = Column(String(20), nullable=False)      # accept | reject | correct
    actor = Column(String(100), nullable=False, default="demo-user")
    note = Column(Text, nullable=True)
    corrected_values = Column(JSON, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    finding = relationship("Finding", back_populates="review_decisions")
    candidate = relationship("MatchCandidate", foreign_keys=[candidate_id])


# ---------------------------------------------------------------------------
# AuditEvent  (append-only by convention)
# ---------------------------------------------------------------------------
class AuditEvent(Base):
    """
    Immutable log of every significant action in the system.

    ``event_type`` is a dot-separated string, e.g. "case.created",
    "record.superseded", "finding.reviewed".
    ``payload`` is a free-form JSON object with relevant IDs and values.
    This table must never be UPDATEd or DELETEd — enforced by repository
    convention, not by a DB constraint (prototype shortcut).
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    actor = Column(String(100), nullable=False, default="demo-user")
    payload = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    case = relationship("Case", back_populates="audit_events")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def create_all_tables() -> None:
    """Create all tables defined in this module (idempotent)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Return a new SQLAlchemy Session. Caller must close it."""
    return SessionLocal()


def get_db():
    """FastAPI dependency that yields a session and closes it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
