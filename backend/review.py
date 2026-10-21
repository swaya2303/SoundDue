"""
review.py — Review workflow helpers for SoundDue.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from database import Finding, MatchCandidate, ReviewEvent
from metta_engine import MeTTaEngine


def add_review_event(
    db: Session,
    finding_id: int,
    action: str,
    actor: str,
    note: str | None = None,
) -> ReviewEvent:
    """Insert a review event for a finding."""
    event = ReviewEvent(
        finding_id=finding_id,
        action=action,
        actor=actor,
        timestamp=datetime.utcnow(),
        note=note,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def review_candidate(
    db: Session,
    candidate_id: int,
    action: str,
    actor: str,
) -> MatchCandidate:
    """
    Update match_candidates.status to action ('accepted' | 'rejected').
    If accepted, trigger a MeTTa re-run to update findings.
    """
    candidate = db.query(MatchCandidate).filter(MatchCandidate.id == candidate_id).first()
    if candidate is None:
        raise ValueError(f"MatchCandidate {candidate_id} not found")

    candidate.status = action
    candidate.reviewed_by = actor
    candidate.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(candidate)

    if action == "accepted":
        engine = MeTTaEngine()
        engine.run_all(db)

    return candidate
