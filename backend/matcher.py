"""
matcher.py — Fuzzy / ISRC-based match candidate generation for SoundDue.
"""

from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from database import MatchCandidate, Mapping, Recording, Work


def generate_candidates(db_session: Session) -> list[dict]:
    """
    Generate match candidates between recordings and works.

    Strategy:
    1. If ISRC appears in a mapping row → score=1.0, method='isrc_mapping'
    2. Otherwise fuzzy title match (token_sort_ratio). If score >= 0.7 →
       method='fuzzy_title'
    3. Skip pairs already stored (any status).
    4. Insert new candidates as 'pending'.
    5. Return list of inserted candidate dicts.
    """
    recordings = db_session.query(Recording).all()
    works = db_session.query(Work).all()
    mappings = db_session.query(Mapping).all()

    # Build ISRC → work_iswc lookup from mappings
    isrc_to_iswc: dict[str, str] = {}
    for m in mappings:
        if m.recording_isrc and m.work_iswc:
            isrc_to_iswc[m.recording_isrc] = m.work_iswc

    # Build work iswc → work_id lookup
    iswc_to_work_id: dict[str, int] = {w.iswc: w.id for w in works if w.iswc}

    # Load already-existing candidate pairs to avoid duplicates
    existing_pairs: set[tuple[int, int]] = set(
        db_session.query(MatchCandidate.recording_id, MatchCandidate.work_id).all()
    )

    inserted: list[dict] = []

    for rec in recordings:
        for work in works:
            if (rec.id, work.id) in existing_pairs:
                continue

            score: float | None = None
            method: str | None = None

            # --- ISRC mapping match ---
            if rec.isrc and rec.isrc in isrc_to_iswc:
                mapped_iswc = isrc_to_iswc[rec.isrc]
                if work.iswc == mapped_iswc:
                    score = 1.0
                    method = "isrc_mapping"

            # --- Fuzzy title match (fallback) ---
            if score is None:
                rec_title = rec.title or ""
                work_title = work.title or ""
                ratio = fuzz.token_sort_ratio(rec_title, work_title) / 100.0
                if ratio >= 0.7:
                    score = ratio
                    method = "fuzzy_title"

            if score is not None and method is not None:
                candidate = MatchCandidate(
                    recording_id=rec.id,
                    work_id=work.id,
                    score=Decimal(str(round(score, 4))),
                    method=method,
                    status="pending",
                )
                db_session.add(candidate)
                db_session.flush()
                inserted.append(
                    {
                        "id": candidate.id,
                        "recording_id": rec.id,
                        "work_id": work.id,
                        "score": float(score),
                        "method": method,
                        "status": "pending",
                    }
                )
                existing_pairs.add((rec.id, work.id))

    db_session.commit()
    return inserted
