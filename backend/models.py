"""
models.py — Pydantic v2 response models for SoundDue API.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class RecordingOut(BaseModel):
    id: int
    batch_id: int
    isrc: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    duration_secs: Optional[int] = None
    raw_json: Optional[dict] = None

    model_config = {"from_attributes": True}


class WorkOut(BaseModel):
    id: int
    batch_id: int
    iswc: Optional[str] = None
    title: Optional[str] = None
    composer: Optional[str] = None
    publisher: Optional[str] = None
    raw_json: Optional[dict] = None

    model_config = {"from_attributes": True}


class OwnershipClaimOut(BaseModel):
    id: int
    batch_id: int
    rights_holder: Optional[str] = None
    work_iswc: Optional[str] = None
    share_pct: Optional[float] = None
    rights_category: Optional[str] = None
    territory: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    raw_json: Optional[dict] = None

    model_config = {"from_attributes": True}


class MappingOut(BaseModel):
    id: int
    batch_id: int
    recording_isrc: Optional[str] = None
    work_iswc: Optional[str] = None
    source_label: Optional[str] = None
    raw_json: Optional[dict] = None

    model_config = {"from_attributes": True}


class MatchCandidateOut(BaseModel):
    id: int
    recording_id: int
    work_id: int
    score: float
    method: str
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FindingOut(BaseModel):
    id: int
    rule_id: str
    rule_version: str
    severity: str
    summary: str
    evidence: dict
    status: str
    created_at: datetime
    uncertainty: Optional[str] = None
    next_step: Optional[str] = None

    model_config = {"from_attributes": True}


class ReviewEventOut(BaseModel):
    id: int
    finding_id: int
    action: str
    actor: str
    timestamp: datetime
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    action: str  # accept | reject | note
    actor: str
    note: Optional[str] = None


class CandidateReviewRequest(BaseModel):
    action: str  # accept | reject
    actor: str
