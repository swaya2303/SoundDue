"""
app/linker.py
=============
Exact-match candidate generator for SoundDue.

Design rules
------------
* Links are created ONLY by exact ID correspondence:
    1. Explicit mapping row  (recording_id + work_id, both non-empty)
    2. ISRC / ISWC exact match (recording.isrc == mapping.isrc AND
       work.iswc == mapping.iswc)

* Title similarity, comparison keys, and any other fuzzy heuristic are
  NEVER used to produce a MatchCandidate.  The comparison keys on
  NormalisedRow exist only so that later code *could* build lookup tables
  without case-sensitivity problems — this module does not use them.

* A mapping is "verified" only when its ``verified`` field is explicitly
  truthy ("true", "1", "yes", "y").

* Each generated MatchCandidate has a ``source_ref`` (file_name, row_number
  of the mapping row that created the link) attached to ``reasons``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import MatchCandidate
from app.normaliser import NormalisedRow

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RecordingLink:
    """
    Represents a confirmed exact-match link between a recording Record and a
    work Record.

    Attributes
    ----------
    recording_record_id : int
        DB id of the recording's Record row.
    work_record_id : int
        DB id of the work's Record row.
    case_id : int
    recording_id : str
        Canonical recording_id value from normalised data.
    work_id : str
        Canonical work_id value from normalised data.
    method : str
        "explicit_mapping" | "unverified_mapping" | "isrc_iswc"
    score : Decimal
        Always Decimal("1.0") for exact matches; Decimal("0.9") for unverified.
    verified : bool
        True only if the mapping row that created the link had verified=True.
    source_ref : dict
        Provenance: {file_name, file_id, row_number} from the mapping row.
    reasons : list[str]
        Human-readable explanation strings.
    """

    recording_record_id: int
    work_record_id: int
    case_id: int
    recording_id: str
    work_id: str
    method: str
    score: Decimal
    verified: bool
    source_ref: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_index(nrows: list[NormalisedRow], key_field: str) -> dict[str, NormalisedRow]:
    """
    Build a lookup dict from a canonical field value to the NormalisedRow.
    Rows with an empty value for key_field are skipped.
    If two rows share the same key, the last one wins (prototype behaviour).
    """
    idx: dict[str, NormalisedRow] = {}
    for nr in nrows:
        val = nr.normalised.get(key_field, "").strip()
        if val:
            idx[val] = nr
    return idx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_links(
    db: Session,
    case_id: int,
    recording_nrows: list[NormalisedRow],
    work_nrows: list[NormalisedRow],
    mapping_nrows: list[NormalisedRow],
) -> list[RecordingLink]:
    """
    Generate exact-match RecordingLink objects and persist them as
    MatchCandidate rows.

    Parameters
    ----------
    db : Session
        Active SQLAlchemy session.
    case_id : int
    recording_nrows : list[NormalisedRow]
        Normalised recording rows; each must have source_ref["record_id"] set.
    work_nrows : list[NormalisedRow]
        Normalised work rows; each must have source_ref["record_id"] set.
    mapping_nrows : list[NormalisedRow]
        Normalised mapping rows; each must have source_ref["record_id"] set.

    Returns
    -------
    list[RecordingLink]
        All links created this run.
    """
    # Build lookup indexes on recording_id and work_id
    rec_by_id: dict[str, NormalisedRow] = _build_index(recording_nrows, "recording_id")
    work_by_id: dict[str, NormalisedRow] = _build_index(work_nrows, "work_id")

    # ISRC → recording, ISWC → work (for rule 2 — ISRC/ISWC cross-match)
    rec_by_isrc: dict[str, NormalisedRow] = _build_index(recording_nrows, "isrc")
    work_by_iswc: dict[str, NormalisedRow] = _build_index(work_nrows, "iswc")

    links: list[RecordingLink] = []
    # Track pairs already linked to avoid duplicates from the same pass
    seen: set[tuple[int, int]] = set()

    for mapping_nr in mapping_nrows:
        mn = mapping_nr.normalised
        src = mapping_nr.source_ref

        m_rec_id = mn.get("recording_id", "").strip()
        m_work_id = mn.get("work_id", "").strip()
        m_verified: bool = bool(mn.get("verified", False))

        # ----------------------------------------------------------------
        # Rule 1 — explicit mapping by recording_id + work_id
        # ----------------------------------------------------------------
        if m_rec_id and m_work_id:
            rec_nr = rec_by_id.get(m_rec_id)
            wrk_nr = work_by_id.get(m_work_id)

            if rec_nr is not None and wrk_nr is not None:
                r_rec_id: int = rec_nr.source_ref.get("record_id", 0)
                w_rec_id: int = wrk_nr.source_ref.get("record_id", 0)

                if r_rec_id and w_rec_id and (r_rec_id, w_rec_id) not in seen:
                    seen.add((r_rec_id, w_rec_id))
                    method = "explicit_mapping" if m_verified else "unverified_mapping"
                    score = Decimal("1.0") if m_verified else Decimal("0.9")
                    reasons = [
                        f"recording_id '{m_rec_id}' matched exactly in recordings file",
                        f"work_id '{m_work_id}' matched exactly in works file",
                        f"mapping row: {src.get('file_name', '')} row {src.get('row_number', '?')}",
                    ]
                    if not m_verified:
                        reasons.append("mapping row verified=False — link is unverified")
                    link = RecordingLink(
                        recording_record_id=r_rec_id,
                        work_record_id=w_rec_id,
                        case_id=case_id,
                        recording_id=m_rec_id,
                        work_id=m_work_id,
                        method=method,
                        score=score,
                        verified=m_verified,
                        source_ref=dict(src),
                        reasons=reasons,
                    )
                    links.append(link)
                    continue  # first-match-wins per mapping row

        # ----------------------------------------------------------------
        # Rule 2 — ISRC + ISWC exact match via mapping row
        # (only when the mapping row carries both isrc and iswc)
        # ----------------------------------------------------------------
        m_isrc = mn.get("isrc", "").strip()
        m_iswc = mn.get("iswc", "").strip()

        if m_isrc and m_iswc:
            rec_nr = rec_by_isrc.get(m_isrc)
            wrk_nr = work_by_iswc.get(m_iswc)

            if rec_nr is not None and wrk_nr is not None:
                r_rec_id = rec_nr.source_ref.get("record_id", 0)
                w_rec_id = wrk_nr.source_ref.get("record_id", 0)

                if r_rec_id and w_rec_id and (r_rec_id, w_rec_id) not in seen:
                    seen.add((r_rec_id, w_rec_id))
                    method = "isrc_iswc"
                    score = Decimal("1.0")
                    reasons = [
                        f"ISRC '{m_isrc}' exact match between mapping and recordings",
                        f"ISWC '{m_iswc}' exact match between mapping and works",
                        f"mapping row: {src.get('file_name', '')} row {src.get('row_number', '?')}",
                    ]
                    link = RecordingLink(
                        recording_record_id=r_rec_id,
                        work_record_id=w_rec_id,
                        case_id=case_id,
                        recording_id=rec_nr.normalised.get("recording_id", ""),
                        work_id=wrk_nr.normalised.get("work_id", ""),
                        method=method,
                        score=score,
                        verified=m_verified,
                        source_ref=dict(src),
                        reasons=reasons,
                    )
                    links.append(link)

    # ----------------------------------------------------------------
    # Persist as MatchCandidate rows
    # ----------------------------------------------------------------
    for lnk in links:
        candidate = MatchCandidate(
            case_id=lnk.case_id,
            left_record_id=lnk.recording_record_id,
            right_record_id=lnk.work_record_id,
            score=lnk.score,
            field_scores={
                "recording_id": 1.0 if lnk.method != "unverified_mapping" else 0.9,
                "work_id": 1.0 if lnk.method != "unverified_mapping" else 0.9,
            },
            reasons=lnk.reasons,
            status="pending",
        )
        db.add(candidate)

    return links
