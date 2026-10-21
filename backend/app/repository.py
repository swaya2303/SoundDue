"""
repository.py — Simple data-access helpers for the case-scoped data model.

All functions accept a SQLAlchemy Session as their first argument.
The caller is responsible for committing (or rolling back) the session.

Prototype shortcut: a single hard-coded demo user is used throughout.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Case,
    ColumnMapping,
    Evidence,
    Finding,
    Record,
    ReviewDecision,
    RuleTrace,
    UploadedFile,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_USER = "demo-user"

# Storage root relative to the backend/ working directory.
# Each case gets its own sub-folder: ./storage/{case_id}/
_STORAGE_ROOT = Path("storage")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _storage_dir(case_id: int) -> Path:
    """Return (and create) the storage directory for a case."""
    p = _STORAGE_ROOT / str(case_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def create_case(db: Session, name: str, description: str = "") -> Case:
    """Create a new reconciliation case and return it (not yet committed)."""
    case = Case(
        name=name,
        description=description,
        created_by=DEMO_USER,
        created_at=_now(),
        status="active",
    )
    db.add(case)
    db.flush()  # populate case.id without committing
    return case


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def add_file(
    db: Session,
    case_id: int,
    original_name: str,
    content_bytes: bytes,
    file_type: str,
) -> UploadedFile:
    """
    Persist *content_bytes* to disk under ./storage/{case_id}/,
    record its SHA-256, and insert an UploadedFile row.
    """
    dest_dir = _storage_dir(case_id)
    dest_path = dest_dir / original_name
    dest_path.write_bytes(content_bytes)

    uf = UploadedFile(
        case_id=case_id,
        original_name=original_name,
        storage_path=str(dest_path),
        sha256=_sha256(content_bytes),
        file_type=file_type,
        uploaded_by=DEMO_USER,
        uploaded_at=_now(),
    )
    db.add(uf)
    db.flush()
    return uf


# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------


def save_column_mapping(
    db: Session,
    file_id: int,
    source_column: str,
    canonical_field: str,
    confirmed: bool = False,
) -> ColumnMapping:
    """Record how a source column maps to a canonical field name."""
    cm = ColumnMapping(
        uploaded_file_id=file_id,
        source_column=source_column,
        canonical_field=canonical_field,
        confirmed=confirmed,
    )
    db.add(cm)
    db.flush()
    return cm


# ---------------------------------------------------------------------------
# Records (versioned)
# ---------------------------------------------------------------------------


def save_records(
    db: Session,
    case_id: int,
    records: list[dict[str, Any]],
    record_type: str,
    source_file_id: int,
) -> list[Record]:
    """
    Bulk-insert normalised records for a case.

    Each dict in *records* should carry:
      - 'normalised': the canonicalised field dict
      - 'raw': the original row dict (stored verbatim)
      - 'source_row': the 1-based row number in the source file
    """
    saved: list[Record] = []
    for item in records:
        rec = Record(
            case_id=case_id,
            record_type=record_type,
            normalised_json=item.get("normalised", {}),
            raw_json=item.get("raw", {}),
            source_file_id=source_file_id,
            source_row=item.get("source_row"),
            version=1,
            supersedes_id=None,
            created_by=DEMO_USER,
            created_at=_now(),
        )
        db.add(rec)
        saved.append(rec)
    db.flush()
    return saved


def supersede_record(
    db: Session,
    old_record_id: int,
    new_normalised: dict[str, Any],
    new_raw: dict[str, Any],
    actor: str = DEMO_USER,
) -> Record:
    """
    Create a new version of an existing record.

    The old record is NEVER modified (append-only by convention).
    The new record has version = old.version + 1 and supersedes_id = old.id.
    """
    old = db.get(Record, old_record_id)
    if old is None:
        raise ValueError(f"Record {old_record_id} not found")

    new_rec = Record(
        case_id=old.case_id,
        record_type=old.record_type,
        normalised_json=new_normalised,
        raw_json=new_raw,
        source_file_id=old.source_file_id,
        source_row=old.source_row,
        version=old.version + 1,
        supersedes_id=old.id,
        created_by=actor,
        created_at=_now(),
    )
    db.add(new_rec)
    db.flush()
    return new_rec


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def save_findings(
    db: Session,
    case_id: int,
    findings: list[dict[str, Any]],
) -> list[Finding]:
    """
    Persist a list of finding dicts produced by the MeTTa engine.

    Each dict should contain:
      rule_id, rule_version, severity, summary, uncertainty, next_step,
      evidence (dict), and optionally:
        matched_conditions (list), supporting_record_ids (list),
        missing_information (str), conflicting_information (str)

    Note: Finding rows store severity/summary/status.
    rule_id and rule_version are stored in RuleTrace (one per finding).
    Evidence fields go into the Evidence table via field_values JSON.
    """
    saved: list[Finding] = []
    for fd in findings:
        finding = Finding(
            case_id=case_id,
            # finding_type comes from the rule-runner dict; fall back to rule_id
            finding_type=fd.get("finding_type") or fd.get("rule_id", "unknown"),
            severity=fd["severity"],
            summary=fd["summary"],
            uncertainty=fd.get("uncertainty", ""),
            next_step=fd.get("next_step", ""),
            status="open",
            created_at=_now(),
        )
        db.add(finding)
        db.flush()  # populate finding.id

        # RuleTrace — stores rule metadata and matched conditions
        rt = RuleTrace(
            finding_id=finding.id,
            rule_id=fd["rule_id"],
            rule_version=fd["rule_version"],
            matched_conditions=fd.get("matched_conditions", []),
            supporting_record_ids=fd.get("supporting_record_ids", []),
            missing_information=fd.get("missing_information", ""),
            conflicting_information=fd.get("conflicting_information", ""),
            evaluated_at=_now(),
        )
        db.add(rt)

        # Evidence — store the evidence payload as field_values JSON
        ev_data = fd.get("evidence", {})
        if ev_data:
            ev = Evidence(
                finding_id=finding.id,
                # source_record_id and source_file_id can be populated from
                # supporting_record_ids when available; NULL is fine for prototype
                source_record_id=None,
                source_file_id=None,
                source_row=ev_data.get("row_number"),
                field_values=ev_data,
                note=fd.get("uncertainty", ""),
            )
            db.add(ev)

        db.flush()
        saved.append(finding)

    return saved


# ---------------------------------------------------------------------------
# Review decisions
# ---------------------------------------------------------------------------


def record_decision(
    db: Session,
    decision: str,  # 'accept' | 'reject' | 'correct'
    actor: str = DEMO_USER,
    note: str = "",
    corrected_values: dict[str, Any] | None = None,
    finding_id: int | None = None,
    candidate_id: int | None = None,
) -> ReviewDecision:
    """
    Record a human review decision on a Finding or a MatchCandidate.

    At least one of *finding_id* or *candidate_id* must be supplied.
    """
    if finding_id is None and candidate_id is None:
        raise ValueError("Supply at least one of finding_id or candidate_id")

    target_type = "finding" if finding_id is not None else "candidate"

    rd = ReviewDecision(
        finding_id=finding_id,
        candidate_id=candidate_id,
        target_type=target_type,
        decision=decision,
        actor=actor,
        note=note,
        corrected_values=corrected_values or {},
        decided_at=_now(),
    )
    db.add(rd)
    db.flush()
    return rd


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def log_audit_event(
    db: Session,
    case_id: int,
    event_type: str,
    actor: str = DEMO_USER,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """
    Append an immutable audit event.  Never call UPDATE on this table.
    """
    evt = AuditEvent(
        case_id=case_id,
        event_type=event_type,
        actor=actor,
        payload=payload or {},
        occurred_at=_now(),
    )
    db.add(evt)
    db.flush()
    return evt


# ---------------------------------------------------------------------------
# Rerun diffing helpers
# ---------------------------------------------------------------------------


def finding_fingerprint(finding: "Finding") -> str:
    """
    A short, stable identifier for a finding used to match it across reruns.

    Fingerprint = "{finding_type}|{work_id}|{contributor_id}"

    Only uses fields present in the evidence dict.  If those fields are absent
    the fingerprint falls back to a wider string so at worst we get a new
    finding rather than a spurious match.

    The fingerprint is NOT stored in the DB — it is computed at query time
    from the evidence JSON, so it survives schema changes without a migration.
    """
    ev: dict = {}
    if finding.evidence:
        # evidence is a dynamic relationship; iterate to get the first Evidence row
        for e in finding.evidence:
            ev = e.field_values or {}
            break

    ftype = finding.finding_type or ""
    work = ev.get("work_id", "")
    contrib = ev.get("contributor_id", ev.get("recording_id", ""))
    rc = ev.get("rights_category", "")
    terr = ev.get("territory", "")
    return f"{ftype}|{work}|{contrib}|{rc}|{terr}"
