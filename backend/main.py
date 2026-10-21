"""
main.py — FastAPI application for SoundDue music-record reconciliation prototype.
"""

import os
import shutil
import tempfile
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import ingest as ingest_module
import matcher as matcher_module
from database import (
    Finding,
    MatchCandidate,
    Mapping,
    OwnershipClaim,
    Recording,
    ReviewEvent,
    Work,
    create_tables,
    get_db,
)
from app.cases_router import router as cases_router
from app.models import create_all_tables
from metta_engine import MeTTaEngine
from models import (
    CandidateReviewRequest,
    FindingOut,
    MatchCandidateOut,
    MappingOut,
    OwnershipClaimOut,
    RecordingOut,
    ReviewEventOut,
    ReviewRequest,
    WorkOut,
)
from review import add_review_event, review_candidate as _review_candidate

# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="SoundDue API", version="0.1.0")

allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_env:
    origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)


@app.on_event("startup")
def on_startup():
    create_tables()        # legacy sounddue.db
    create_all_tables()    # case-scoped sounddue_cases.db


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Liveness check — returns {status: ok} when the API is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------
DbDep = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload_file(
    db: DbDep,
    file: UploadFile = File(...),
    file_type: str = Form(...),
):
    """
    Accept a multipart CSV or XLSX file plus a file_type form field.
    Valid file_type values: recordings | works | ownership | mappings
    """
    valid_types = {"recordings", "works", "ownership", "mappings"}
    if file_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"file_type must be one of {sorted(valid_types)}",
        )

    suffix = os.path.splitext(file.filename or "upload")[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        df = ingest_module.parse_file(tmp_path, file_type)
        batch = ingest_module.store_batch(df, file_type, file.filename or "upload", db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        os.unlink(tmp_path)

    return {"batch_id": batch.id, "row_count": batch.row_count, "file_type": file_type}


# ---------------------------------------------------------------------------
# GET /recordings
# ---------------------------------------------------------------------------
@app.get("/recordings", response_model=list[RecordingOut])
def list_recordings(db: DbDep):
    return db.query(Recording).all()


# ---------------------------------------------------------------------------
# GET /works
# ---------------------------------------------------------------------------
@app.get("/works", response_model=list[WorkOut])
def list_works(db: DbDep):
    return db.query(Work).all()


# ---------------------------------------------------------------------------
# GET /ownership
# ---------------------------------------------------------------------------
@app.get("/ownership", response_model=list[OwnershipClaimOut])
def list_ownership(db: DbDep):
    return db.query(OwnershipClaim).all()


# ---------------------------------------------------------------------------
# GET /mappings
# ---------------------------------------------------------------------------
@app.get("/mappings", response_model=list[MappingOut])
def list_mappings(db: DbDep):
    return db.query(Mapping).all()


# ---------------------------------------------------------------------------
# POST /run-matching
# ---------------------------------------------------------------------------
@app.post("/run-matching")
def run_matching(db: DbDep):
    """Run the matcher and MeTTa rule engine. Returns findings."""
    new_candidates = matcher_module.generate_candidates(db)
    engine = MeTTaEngine()
    findings = engine.run_all(db)
    return {
        "new_candidates": len(new_candidates),
        "findings_generated": len(findings),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# GET /findings
# ---------------------------------------------------------------------------
@app.get("/findings", response_model=list[FindingOut])
def list_findings(db: DbDep):
    rows = db.query(Finding).all()
    return [_finding_to_out(f) for f in rows]


# ---------------------------------------------------------------------------
# GET /findings/{id}
# ---------------------------------------------------------------------------
@app.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: int, db: DbDep):
    f = db.query(Finding).filter(Finding.id == finding_id).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _finding_to_out(f)


# ---------------------------------------------------------------------------
# POST /findings/{id}/review
# ---------------------------------------------------------------------------
@app.post("/findings/{finding_id}/review", response_model=ReviewEventOut)
def review_finding(finding_id: int, body: ReviewRequest, db: DbDep):
    f = db.query(Finding).filter(Finding.id == finding_id).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    valid_actions = {"accept", "reject", "note"}
    if body.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(valid_actions)}",
        )
    event = add_review_event(db, finding_id, body.action, body.actor, body.note)
    return event


# ---------------------------------------------------------------------------
# GET /findings/{id}/history
# ---------------------------------------------------------------------------
@app.get("/findings/{finding_id}/history", response_model=list[ReviewEventOut])
def finding_history(finding_id: int, db: DbDep):
    events = (
        db.query(ReviewEvent).filter(ReviewEvent.finding_id == finding_id).all()
    )
    return events


# ---------------------------------------------------------------------------
# GET /candidates
# ---------------------------------------------------------------------------
@app.get("/candidates", response_model=list[MatchCandidateOut])
def list_candidates(db: DbDep):
    return db.query(MatchCandidate).all()


# ---------------------------------------------------------------------------
# POST /candidates/{id}/review
# ---------------------------------------------------------------------------
@app.post("/candidates/{candidate_id}/review", response_model=MatchCandidateOut)
def review_candidate_endpoint(
    candidate_id: int, body: CandidateReviewRequest, db: DbDep
):
    valid_actions = {"accept", "reject"}
    if body.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(valid_actions)}",
        )
    try:
        candidate = _review_candidate(db, candidate_id, body.action, body.actor)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return candidate


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _finding_to_out(f: Finding) -> FindingOut:
    return FindingOut(
        id=f.id,
        rule_id=f.rule_id,
        rule_version=f.rule_version,
        severity=f.severity,
        summary=f.summary,
        evidence=f.evidence_json or {},
        status=f.status,
        created_at=f.created_at,
        uncertainty=f.uncertainty,
        next_step=f.next_step,
    )
