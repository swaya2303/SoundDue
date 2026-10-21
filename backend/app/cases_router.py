"""
app/cases_router.py
===================
Case-scoped REST endpoints:

  POST /cases                     Create a new reconciliation case
  GET  /cases                     List all cases
  POST /cases/{id}/files          Upload a CSV/XLSX file to a case
  GET  /files/{id}/preview        Return detected columns, first 10 rows, row count

All endpoints use the new case-scoped SQLAlchemy engine (sounddue_cases.db)
via app.models.get_db(), NOT the legacy get_db() in database.py.

Validation runs on every upload but never blocks it.  The full report is
returned in the response alongside the stored file's metadata.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.analyzer import run_analysis
from app.column_mapper import REQUIRED_CANONICAL, suggest_all_columns
from app.exporter import render_csv, render_html, render_json
from app.file_validator import validate_file
from app.models import Case, ColumnMapping, UploadedFile, get_db
from app.repository import add_file, create_case, log_audit_event, save_column_mapping, DEMO_USER

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependency — case-scoped DB session
# ---------------------------------------------------------------------------
CaseDbDep = Annotated[Session, Depends(get_db)]

_VALID_KINDS = frozenset({"recordings", "works", "ownership", "mappings"})


# ---------------------------------------------------------------------------
# POST /cases
# ---------------------------------------------------------------------------
@router.post("/cases", status_code=201)
def create_new_case(
    db: CaseDbDep,
    name: str = Form(...),
    description: str = Form(""),
):
    """Create a new reconciliation case."""
    if not name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")

    case = create_case(db, name=name.strip(), description=description.strip())
    log_audit_event(db, case_id=case.id, event_type="case.created",
                    payload={"name": case.name})
    db.commit()

    return {
        "id": case.id,
        "name": case.name,
        "description": case.description,
        "created_by": case.created_by,
        "created_at": case.created_at.isoformat(),
        "status": case.status,
    }


# ---------------------------------------------------------------------------
# GET /cases
# ---------------------------------------------------------------------------
@router.get("/cases")
def list_cases(db: CaseDbDep):
    """Return all cases (newest first)."""
    rows = db.query(Case).order_by(Case.id.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat(),
            "status": c.status,
            "file_count": db.query(UploadedFile)
                            .filter(UploadedFile.case_id == c.id)
                            .count(),
        }
        for c in rows
    ]


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/files
# ---------------------------------------------------------------------------
@router.post("/cases/{case_id}/files", status_code=201)
async def upload_case_file(
    case_id: int,
    db: CaseDbDep,
    file: UploadFile = File(...),
    file_kind: str = Form(...),
):
    """
    Upload a CSV or XLSX file to a case.

    - file_kind: recordings | works | ownership | mappings
    - Stores the raw bytes + SHA-256; validation runs but does not block.
    - Returns the file metadata and a validation report.
    """
    # Validate case exists
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Validate file_kind
    if file_kind not in _VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"file_kind must be one of {sorted(_VALID_KINDS)}",
        )

    # Validate file extension
    filename = file.filename or "upload.csv"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"
    if suffix not in ("csv", "xlsx", "xls"):
        raise HTTPException(
            status_code=400,
            detail="Only .csv and .xlsx files are accepted",
        )

    # Read content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Validate (non-blocking)
    report = validate_file(content, file_kind, filename)

    # Persist file on disk + DB row
    uf = add_file(
        db,
        case_id=case_id,
        original_name=filename,
        content_bytes=content,
        file_type=file_kind,
    )
    # Update row_count now we know it
    uf.row_count = report.row_count
    db.flush()

    log_audit_event(
        db,
        case_id=case_id,
        event_type="file.uploaded",
        payload={
            "file_id": uf.id,
            "file_name": filename,
            "file_kind": file_kind,
            "row_count": report.row_count,
            "issue_count": len(report.issues),
        },
    )
    db.commit()

    return {
        "file_id": uf.id,
        "case_id": case_id,
        "original_name": uf.original_name,
        "sha256": uf.sha256,
        "file_kind": file_kind,
        "row_count": report.row_count,
        "detected_columns": report.detected_columns,
        "validation": {
            "issue_count": len(report.issues),
            "has_errors": report.has_errors,
            "issues": [
                {
                    "row": issue.row,
                    "column": issue.column,
                    "code": issue.code,
                    "message": issue.message,
                    "value": issue.value,
                }
                for issue in report.issues
            ],
        },
    }


# ---------------------------------------------------------------------------
# GET /files/{file_id}/preview
# ---------------------------------------------------------------------------
@router.get("/files/{file_id}/preview")
def get_file_preview(file_id: int, db: CaseDbDep):
    """
    Return the file's detected columns, first 10 rows (raw strings),
    row count, and validation report.

    Re-runs validation from the stored file bytes on every request
    so the report is always fresh.
    """
    uf = db.get(UploadedFile, file_id)
    if uf is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    # Re-read bytes from disk
    try:
        with open(uf.storage_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read stored file: {exc}",
        )

    report = validate_file(content, uf.file_type, uf.original_name)

    return {
        "file_id": uf.id,
        "case_id": uf.case_id,
        "original_name": uf.original_name,
        "file_kind": uf.file_type,
        "sha256": uf.sha256,
        "row_count": report.row_count,
        "detected_columns": report.detected_columns,
        "preview_rows": report.preview_rows,
        "validation": {
            "issue_count": len(report.issues),
            "has_errors": report.has_errors,
            "issues": [
                {
                    "row": issue.row,
                    "column": issue.column,
                    "code": issue.code,
                    "message": issue.message,
                    "value": issue.value,
                }
                for issue in report.issues
            ],
        },
    }


# ---------------------------------------------------------------------------
# GET /files/{file_id}/mapping/suggestions
# ---------------------------------------------------------------------------
@router.get("/files/{file_id}/mapping/suggestions")
def get_mapping_suggestions(file_id: int, db: CaseDbDep):
    """
    Return per-column mapping suggestions for an uploaded file.

    Resolution order (column_mapper.suggest_column):
      1. Exact synonym dictionary lookup
      2. RapidFuzz token_sort_ratio (threshold 70)
      3. LLM stub — always None (future work)

    Also returns:
      - required_fields: canonical fields required for this file kind
      - confirmed_mappings: mappings already confirmed in the DB
      - all_confirmed: True when every required field has a confirmed mapping
    """
    uf = db.get(UploadedFile, file_id)
    if uf is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    # Re-read headers from disk
    try:
        with open(uf.storage_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read stored file: {exc}")

    report = validate_file(content, uf.file_type, uf.original_name)
    detected_columns = report.detected_columns

    # Generate suggestions for every detected column
    suggestions = suggest_all_columns(detected_columns, file_kind=uf.file_type)

    # Load existing confirmed mappings from DB
    existing: list[ColumnMapping] = (
        db.query(ColumnMapping)
        .filter(ColumnMapping.uploaded_file_id == file_id)
        .all()
    )
    confirmed_by_source: dict[str, str] = {
        cm.source_column: cm.canonical_field
        for cm in existing
        if cm.confirmed
    }

    # Auto-confirm exact synonym matches when no prior confirmations exist.
    # This avoids forcing the user to click "Confirm" for files whose columns
    # already have unambiguous exact matches in the synonym dictionary.
    if not existing:  # only auto-confirm on first load (no rows in DB yet)
        auto_confirmed: list[ColumnMapping] = []
        for sg in suggestions:
            if sg.confidence == "exact" and sg.best_canonical:
                auto_confirmed.append(
                    save_column_mapping(
                        db,
                        file_id=file_id,
                        source_column=sg.source_column,
                        canonical_field=sg.best_canonical,
                        confirmed=True,
                    )
                )
        if auto_confirmed:
            db.commit()
            confirmed_by_source = {
                cm.source_column: cm.canonical_field for cm in auto_confirmed
            }

    # Determine which required fields are already confirmed
    required = REQUIRED_CANONICAL.get(uf.file_type, [])
    confirmed_canonicals = set(confirmed_by_source.values())
    all_confirmed = all(f in confirmed_canonicals for f in required)

    return {
        "file_id": file_id,
        "file_kind": uf.file_type,
        "required_fields": required,
        "all_confirmed": all_confirmed,
        "confirmed_mappings": [
            {"source_column": src, "canonical_field": canon}
            for src, canon in confirmed_by_source.items()
        ],
        "suggestions": [
            {
                "source_column": s.source_column,
                "best_canonical": s.best_canonical,
                "confidence": s.confidence,
                "score": s.score,
                "method": s.method,
                "alternatives": s.alternatives,
            }
            for s in suggestions
        ],
    }


# ---------------------------------------------------------------------------
# PUT /files/{file_id}/mapping
# ---------------------------------------------------------------------------
class _MappingEntry(dict):
    """Thin typed alias — the body is validated inline below."""


from pydantic import BaseModel  # noqa: E402 (local to endpoint for simplicity)


class _MappingBody(BaseModel):
    mappings: list[dict]  # [{"source_column": "...", "canonical_field": "..."}]


@router.put("/files/{file_id}/mapping")
def confirm_mapping(file_id: int, body: _MappingBody, db: CaseDbDep):
    """
    Persist user-confirmed column mappings for a file.

    Each entry must supply source_column and canonical_field.
    Existing rows are updated in-place (upsert by source_column).
    All submitted mappings are set to confirmed=True.

    Returns the updated full mapping state and all_confirmed flag.
    """
    uf = db.get(UploadedFile, file_id)
    if uf is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    if not body.mappings:
        raise HTTPException(status_code=400, detail="mappings list must not be empty")

    for entry in body.mappings:
        source_col = entry.get("source_column", "").strip()
        canon_field = entry.get("canonical_field", "").strip()
        if not source_col or not canon_field:
            raise HTTPException(
                status_code=400,
                detail="Each mapping entry must have non-empty source_column and canonical_field",
            )

        # Upsert: update if exists, insert if not
        existing = (
            db.query(ColumnMapping)
            .filter(
                ColumnMapping.uploaded_file_id == file_id,
                ColumnMapping.source_column == source_col,
            )
            .first()
        )
        if existing:
            existing.canonical_field = canon_field
            existing.confirmed = True
        else:
            save_column_mapping(
                db,
                file_id=file_id,
                source_column=source_col,
                canonical_field=canon_field,
                confirmed=True,
            )

    db.flush()

    # Determine all_confirmed
    required = REQUIRED_CANONICAL.get(uf.file_type, [])
    confirmed_rows: list[ColumnMapping] = (
        db.query(ColumnMapping)
        .filter(
            ColumnMapping.uploaded_file_id == file_id,
            ColumnMapping.confirmed == True,  # noqa: E712
        )
        .all()
    )
    confirmed_canonicals = {cm.canonical_field for cm in confirmed_rows}
    all_confirmed = all(f in confirmed_canonicals for f in required)

    log_audit_event(
        db,
        case_id=uf.case_id,
        event_type="mapping.confirmed",
        actor=DEMO_USER,
        payload={
            "file_id": file_id,
            "file_name": uf.original_name,
            "mappings_count": len(body.mappings),
            "all_confirmed": all_confirmed,
        },
    )
    db.commit()

    return {
        "file_id": file_id,
        "file_kind": uf.file_type,
        "required_fields": required,
        "all_confirmed": all_confirmed,
        "confirmed_mappings": [
            {"source_column": cm.source_column, "canonical_field": cm.canonical_field}
            for cm in confirmed_rows
        ],
    }


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/analyze
# ---------------------------------------------------------------------------
@router.post("/cases/{case_id}/analyze", status_code=202)
def analyze_case(case_id: int, db: CaseDbDep):
    """
    Trigger analysis for a case.

    Gate: every uploaded file in the case must have confirmed ColumnMapping
    rows covering all required canonical fields for its file kind.

    If any file is missing confirmed mappings the endpoint returns 422 with a
    structured payload listing the unconfirmed files/fields.

    If the gate passes, runs the full rule engine (R1–R4) and returns a
    summary of findings produced.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    files: list[UploadedFile] = (
        db.query(UploadedFile).filter(UploadedFile.case_id == case_id).all()
    )

    if not files:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No files uploaded to this case",
                "unconfirmed": [],
            },
        )

    # Gate: check every file has confirmed mappings for all required fields
    unconfirmed_report: list[dict] = []
    for uf in files:
        required = REQUIRED_CANONICAL.get(uf.file_type, [])
        if not required:
            continue

        confirmed_rows: list[ColumnMapping] = (
            db.query(ColumnMapping)
            .filter(
                ColumnMapping.uploaded_file_id == uf.id,
                ColumnMapping.confirmed == True,  # noqa: E712
            )
            .all()
        )
        confirmed_canonicals = {cm.canonical_field for cm in confirmed_rows}
        missing = [f for f in required if f not in confirmed_canonicals]

        if missing:
            unconfirmed_report.append(
                {
                    "file_id": uf.id,
                    "file_name": uf.original_name,
                    "file_kind": uf.file_type,
                    "missing_fields": missing,
                }
            )

    if unconfirmed_report:
        log_audit_event(
            db,
            case_id=case_id,
            event_type="analysis.blocked",
            actor=DEMO_USER,
            payload={"unconfirmed_count": len(unconfirmed_report)},
        )
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Mappings must be confirmed before analysis",
                "unconfirmed": unconfirmed_report,
            },
        )

    # Run the analysis engine
    summary = run_analysis(db, case_id=case_id)

    return {
        "status": "completed",
        "case_id": case_id,
        "file_count": len(files),
        "record_count": summary["record_count"],
        "finding_count": summary["finding_count"],
        "findings_by_type": summary["findings_by_type"],
        "finding_ids": summary["finding_ids"],
    }


# ---------------------------------------------------------------------------
# GET /cases/{case_id}/findings
# ---------------------------------------------------------------------------
@router.get("/cases/{case_id}/findings")
def list_case_findings(case_id: int, db: CaseDbDep):
    """
    List all findings for a case, newest first.

    Returns a summary list — use GET /findings/{id} for full detail.
    """
    from app.models import Finding, RuleTrace  # local import avoids circular refs

    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    findings: list[Finding] = (
        db.query(Finding)
        .filter(Finding.case_id == case_id)
        .order_by(Finding.id.desc())
        .all()
    )

    result = []
    for f in findings:
        rt: RuleTrace | None = f.rule_trace
        result.append({
            "id": f.id,
            "finding_type": f.finding_type,
            "severity": f.severity,
            "summary": f.summary,
            "status": f.status,
            "created_at": f.created_at.isoformat(),
            "rule_id": rt.rule_id if rt else None,
            "rule_version": rt.rule_version if rt else None,
        })
    return result


# ---------------------------------------------------------------------------
# GET /findings/{finding_id}
# ---------------------------------------------------------------------------
@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, db: CaseDbDep):
    """
    Full detail for a single finding: summary, evidence, rule trace,
    uncertainty, next step, and review history.
    """
    from app.models import Evidence, Finding, ReviewDecision, RuleTrace

    f: Finding | None = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")

    rt: RuleTrace | None = f.rule_trace
    evidence_rows: list[Evidence] = list(f.evidence)
    decisions: list[ReviewDecision] = list(f.review_decisions)

    return {
        "id": f.id,
        "case_id": f.case_id,
        "finding_type": f.finding_type,
        "severity": f.severity,
        "summary": f.summary,
        "uncertainty": f.uncertainty,
        "next_step": f.next_step,
        "status": f.status,
        "created_at": f.created_at.isoformat(),
        "rule_trace": {
            "rule_id": rt.rule_id,
            "rule_version": rt.rule_version,
            "matched_conditions": rt.matched_conditions,
            "supporting_record_ids": rt.supporting_record_ids,
            "missing_information": rt.missing_information,
            "conflicting_information": rt.conflicting_information,
            "evaluated_at": rt.evaluated_at.isoformat(),
        } if rt else None,
        "evidence": [
            {
                "id": ev.id,
                "source_record_id": ev.source_record_id,
                "source_file_id": ev.source_file_id,
                "source_row": ev.source_row,
                "field_values": ev.field_values,
                "note": ev.note,
            }
            for ev in evidence_rows
        ],
        "review_decisions": [
            {
                "id": rd.id,
                "decision": rd.decision,
                "actor": rd.actor,
                "note": rd.note,
                "corrected_values": rd.corrected_values,
                "decided_at": rd.decided_at.isoformat(),
            }
            for rd in decisions
        ],
    }


# ---------------------------------------------------------------------------
# POST /findings/{finding_id}/review
# ---------------------------------------------------------------------------
class _ReviewBody(BaseModel):
    decision: str          # accept | reject | correct
    note: str = ""
    corrected_values: dict = {}


@router.post("/findings/{finding_id}/review", status_code=200)
def review_finding(finding_id: int, body: _ReviewBody, db: CaseDbDep):
    """
    Record a human review decision on a finding.

    decision : accept | reject | correct
    note     : free-text explanation (required when decision == 'correct')
    corrected_values : dict of canonical_field → corrected value (for 'correct')

    Status transitions:
      accept  → resolved
      reject  → rejected
      correct → resolved + a NEW Record version is created for every
                corrected record referenced by the finding.
                The old record is never modified (append-only).

    Rejections are permanent — the finding status stays 'rejected' on rerun.
    All actions are logged to audit_events.
    """
    from app.models import Finding, Record
    from app.repository import record_decision, supersede_record

    _VALID_DECISIONS = {"accept", "reject", "correct"}
    if body.decision not in _VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"decision must be one of {sorted(_VALID_DECISIONS)}",
        )
    if body.decision == "correct" and not body.note.strip():
        raise HTTPException(
            status_code=400,
            detail="note is required when decision is 'correct'",
        )

    f: Finding | None = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")

    # ------------------------------------------------------------------
    # For 'correct': create new Record versions from corrected_values.
    # corrected_values is a dict of canonical_field → corrected value.
    # We apply the corrections to each supporting record referenced in
    # the RuleTrace.  If no supporting_record_ids are stored we still
    # save the decision (corrections logged, no version bump possible).
    # ------------------------------------------------------------------
    new_record_ids: list[int] = []
    if body.decision == "correct" and body.corrected_values:
        rt = f.rule_trace
        supporting_ids: list[int] = rt.supporting_record_ids if rt else []

        for old_id in (supporting_ids or []):
            old_rec: Record | None = db.get(Record, old_id)
            if old_rec is None:
                continue
            # Build new normalised_json by merging corrections on top of old values
            new_normalised = dict(old_rec.normalised_json or {})
            new_normalised.update(body.corrected_values)

            new_raw = dict(old_rec.raw_json or {})
            new_raw["_corrected_by_review"] = finding_id
            new_raw["_corrections"] = body.corrected_values

            new_rec = supersede_record(
                db,
                old_record_id=old_id,
                new_normalised=new_normalised,
                new_raw=new_raw,
                actor=DEMO_USER,
            )
            new_record_ids.append(new_rec.id)

        log_audit_event(
            db,
            case_id=f.case_id,
            event_type="record.corrected",
            actor=DEMO_USER,
            payload={
                "finding_id": finding_id,
                "old_record_ids": supporting_ids,
                "new_record_ids": new_record_ids,
                "corrected_fields": list(body.corrected_values.keys()),
            },
        )

    # Persist the review decision
    rd = record_decision(
        db,
        decision=body.decision,
        actor=DEMO_USER,
        note=body.note,
        corrected_values=body.corrected_values or {},
        finding_id=finding_id,
    )

    # Update finding status
    if body.decision in ("accept", "correct"):
        f.status = "resolved"
    elif body.decision == "reject":
        f.status = "rejected"

    log_audit_event(
        db,
        case_id=f.case_id,
        event_type="finding.reviewed",
        actor=DEMO_USER,
        payload={
            "finding_id": finding_id,
            "decision": body.decision,
            "new_status": f.status,
            "new_record_ids": new_record_ids,
        },
    )
    db.commit()

    return {
        "finding_id": finding_id,
        "decision_id": rd.id,
        "new_status": f.status,
        "decision": body.decision,
        "new_record_versions": new_record_ids,
    }


# ---------------------------------------------------------------------------
# GET /cases/{case_id}/candidates
# ---------------------------------------------------------------------------
@router.get("/cases/{case_id}/candidates")
def list_candidates(case_id: int, db: CaseDbDep):
    """
    Return all MatchCandidate rows for a case.

    Includes fuzzy and exact-match candidates (all statuses).
    """
    from app.models import MatchCandidate

    candidates = db.query(MatchCandidate).filter(MatchCandidate.case_id == case_id).all()
    result = []
    for c in candidates:
        result.append({
            "id": c.id,
            "left_record_id": c.left_record_id,
            "right_record_id": c.right_record_id,
            "score": float(c.score),
            "field_scores": c.field_scores,
            "reasons": c.reasons,
            "status": c.status,
            "reviewed_by": c.reviewed_by,
            "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return result


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/candidates/{candidate_id}/review
# ---------------------------------------------------------------------------
class _CandidateReview(BaseModel):
    action: str   # "accept" | "reject"
    actor: str = "demo-user"


@router.post("/cases/{case_id}/candidates/{candidate_id}/review")
def review_candidate(
    case_id: int,
    candidate_id: int,
    body: _CandidateReview,
    db: CaseDbDep,
):
    """
    Accept or reject a MatchCandidate.

    action: "accept" | "reject"
    actor: reviewer identity (defaults to "demo-user")

    Rejected candidates are never re-proposed by the fuzzy matcher on
    subsequent analysis runs.
    """
    from app.models import MatchCandidate
    from datetime import datetime, timezone

    candidate = db.query(MatchCandidate).filter(
        MatchCandidate.id == candidate_id,
        MatchCandidate.case_id == case_id,
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if body.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    candidate.status = "accepted" if body.action == "accept" else "rejected"
    candidate.reviewed_by = body.actor
    candidate.reviewed_at = datetime.now(timezone.utc)

    log_audit_event(
        db,
        case_id=case_id,
        event_type=f"candidate.{body.action}",
        actor=body.actor,
        payload={"candidate_id": candidate_id},
    )
    db.commit()
    return {"id": candidate_id, "status": candidate.status}


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/rerun
# ---------------------------------------------------------------------------
@router.post("/cases/{case_id}/rerun", status_code=200)
def rerun_case(case_id: int, db: CaseDbDep):
    """
    Re-run the full analysis pipeline for a case and return a structured diff
    of findings compared to the previous run.

    Diff categories
    ---------------
    new        : fingerprint not seen in any previous finding
    unchanged  : same fingerprint, status still 'open'
    resolved   : previously open finding whose fingerprint no longer fires
                 (marked 'resolved' automatically)
    rejected   : findings that were manually rejected — carried forward as-is,
                 never re-opened by a rerun
    changed    : same fingerprint but summary text differs (rule output changed)

    Fingerprint
    -----------
    Computed by repository.finding_fingerprint():
      "{finding_type}|{work_id}|{contributor_id}|{rights_category}|{territory}"

    The diff is returned in the response AND logged to audit_events.
    """
    from app.models import Finding
    from app.repository import finding_fingerprint

    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # ------------------------------------------------------------------
    # 1. Load the PREVIOUS state of findings (before this run)
    # ------------------------------------------------------------------
    prev_findings: list[Finding] = (
        db.query(Finding)
        .filter(Finding.case_id == case_id)
        .order_by(Finding.id.asc())
        .all()
    )

    # Build fingerprint → (finding_id, status, summary) map from previous run.
    # Rejected findings are carried forward: we never reopen them.
    prev_by_fp: dict[str, dict] = {}
    for pf in prev_findings:
        fp = finding_fingerprint(pf)
        prev_by_fp[fp] = {
            "finding_id": pf.id,
            "status": pf.status,
            "summary": pf.summary,
            "finding_type": pf.finding_type,
            "severity": pf.severity,
        }

    # ------------------------------------------------------------------
    # 2. Run full analysis (always a fresh pass — additive by design)
    # ------------------------------------------------------------------
    summary = run_analysis(db, case_id=case_id)

    # ------------------------------------------------------------------
    # 3. Load the NEW findings (just created by run_analysis)
    # ------------------------------------------------------------------
    # run_analysis() returns finding_ids — fetch those rows
    new_finding_ids: list[int] = summary.get("finding_ids", [])
    new_findings: list[Finding] = (
        db.query(Finding)
        .filter(
            Finding.case_id == case_id,
            Finding.id.in_(new_finding_ids),
        )
        .all()
    )

    # ------------------------------------------------------------------
    # 4. Build the diff
    # ------------------------------------------------------------------
    diff: dict[str, list[dict]] = {
        "new": [],
        "unchanged": [],
        "changed": [],
        "resolved": [],
        "rejected": [],
    }

    new_fps: set[str] = set()
    for nf in new_findings:
        fp = finding_fingerprint(nf)
        new_fps.add(fp)

        entry = {
            "finding_id": nf.id,
            "finding_type": nf.finding_type,
            "severity": nf.severity,
            "summary": nf.summary,
            "status": nf.status,
            "fingerprint": fp,
        }

        if fp not in prev_by_fp:
            diff["new"].append(entry)
        else:
            prev = prev_by_fp[fp]
            if prev["status"] == "rejected":
                # Never re-open a rejected finding
                diff["rejected"].append({**entry, "prev_finding_id": prev["finding_id"]})
            elif prev["summary"] != nf.summary:
                diff["changed"].append({**entry, "prev_finding_id": prev["finding_id"],
                                        "prev_summary": prev["summary"]})
            else:
                diff["unchanged"].append({**entry, "prev_finding_id": prev["finding_id"]})

    # Findings from the previous run that did NOT reappear → resolved
    for fp, prev in prev_by_fp.items():
        if fp in new_fps:
            continue
        if prev["status"] in ("resolved", "rejected"):
            # Already handled — don't double-list
            if prev["status"] == "rejected":
                diff["rejected"].append({
                    "finding_id": prev["finding_id"],
                    "finding_type": prev["finding_type"],
                    "severity": prev["severity"],
                    "summary": prev["summary"],
                    "status": prev["status"],
                    "fingerprint": fp,
                    "note": "manually rejected — not re-evaluated",
                })
            continue
        # Was open, didn't refire → mark resolved
        gone_finding: Finding | None = db.get(Finding, prev["finding_id"])
        if gone_finding and gone_finding.status == "open":
            gone_finding.status = "resolved"
            db.flush()
        diff["resolved"].append({
            "finding_id": prev["finding_id"],
            "finding_type": prev["finding_type"],
            "summary": prev["summary"],
            "fingerprint": fp,
            "note": "did not fire on rerun — auto-resolved",
        })

    db.commit()

    # ------------------------------------------------------------------
    # 5. Log the rerun event
    # ------------------------------------------------------------------
    log_audit_event(
        db,
        case_id=case_id,
        event_type="analysis.rerun",
        actor=DEMO_USER,
        payload={
            "new_count": len(diff["new"]),
            "unchanged_count": len(diff["unchanged"]),
            "changed_count": len(diff["changed"]),
            "resolved_count": len(diff["resolved"]),
            "rejected_count": len(diff["rejected"]),
            "total_new_findings": summary["finding_count"],
        },
    )
    db.commit()

    return {
        "case_id": case_id,
        "status": "rerun_completed",
        "summary": {
            "new": len(diff["new"]),
            "unchanged": len(diff["unchanged"]),
            "changed": len(diff["changed"]),
            "resolved": len(diff["resolved"]),
            "rejected": len(diff["rejected"]),
        },
        "diff": diff,
        "analysis": {
            "finding_count": summary["finding_count"],
            "findings_by_type": summary["findings_by_type"],
            "record_count": summary["record_count"],
        },
    }


# ---------------------------------------------------------------------------
# GET /cases/{case_id}/export
# ---------------------------------------------------------------------------

from fastapi.responses import Response  # noqa: E402


@router.get("/cases/{case_id}/export")
def export_case_findings(
    case_id: int,
    format: str = "json",
    db: CaseDbDep = ...,
):
    """
    Export all findings for a case with evidence and rule traces.

    Query parameter:
      format = json | csv | html   (default: json)

    JSON  → findings.json  (full evidence + rule traces + plain-language explanation)
    CSV   → findings.csv   (one row per finding, evidence record IDs concatenated)
    HTML  → findings.html  (human-readable report with per-finding sections)

    The plain-language explanation is generated from the structured rule trace
    only — no values are invented.  Set env SOUNDDUE_LLM_REWRITE=1 to enable
    optional LLM rewriting (discarded if it introduces new identifiers or numbers).
    """
    from app.models import Finding, RuleTrace, Evidence, ReviewDecision  # noqa: E402

    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    findings_orm = (
        db.query(Finding)
        .filter(Finding.case_id == case_id)
        .order_by(Finding.created_at)
        .all()
    )

    # Build serialisable dicts matching GET /findings/{id} shape
    findings_data: list[dict] = []
    for f in findings_orm:
        trace_orm = db.query(RuleTrace).filter(RuleTrace.finding_id == f.id).first()
        evidence_orm = db.query(Evidence).filter(Evidence.finding_id == f.id).all()
        decisions_orm = (
            db.query(ReviewDecision).filter(ReviewDecision.finding_id == f.id).all()
        )

        trace_dict = None
        if trace_orm:
            trace_dict = {
                "rule_id": trace_orm.rule_id,
                "rule_version": trace_orm.rule_version,
                "matched_conditions": trace_orm.matched_conditions or [],
                "supporting_record_ids": trace_orm.supporting_record_ids or [],
                "missing_information": trace_orm.missing_information,
                "conflicting_information": trace_orm.conflicting_information,
                "evaluated_at": trace_orm.evaluated_at.isoformat()
                if trace_orm.evaluated_at
                else None,
            }

        evidence_list = [
            {
                "id": ev.id,
                "source_record_id": ev.source_record_id,
                "source_file_id": ev.source_file_id,
                "source_row": ev.source_row,
                "field_values": ev.field_values or {},
                "note": ev.note,
            }
            for ev in evidence_orm
        ]

        decisions_list = [
            {
                "id": d.id,
                "decision": d.decision,
                "actor": d.actor,
                "note": d.note,
                "corrected_values": d.corrected_values or {},
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            }
            for d in decisions_orm
        ]

        findings_data.append(
            {
                "id": f.id,
                "case_id": f.case_id,
                "finding_type": f.finding_type,
                "rule_id": f.rule_id,
                "rule_version": f.rule_version,
                "severity": f.severity,
                "summary": f.summary,
                "status": f.status,
                "uncertainty": f.uncertainty,
                "next_step": f.next_step,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "rule_trace": trace_dict,
                "evidence": evidence_list,
                "review_decisions": decisions_list,
            }
        )

    fmt = format.lower()
    case_name = case.name or f"Case {case_id}"

    if fmt == "csv":
        content = render_csv(findings_data)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="findings_case{case_id}.csv"'
            },
        )
    elif fmt == "html":
        content = render_html(findings_data, case_name=case_name)
        return Response(
            content=content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="findings_case{case_id}.html"'
            },
        )
    else:  # default: json
        content = render_json(findings_data)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="findings_case{case_id}.json"'
            },
        )
