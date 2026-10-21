"""
app/fuzzy_matcher.py
====================
RapidFuzz-based candidate proposer for recording ↔ work pairs.

Design rules
------------
* Only runs on recordings that have no accepted or pending exact link already.
* Requires at LEAST ONE corroborating field besides title:
    - performer / writer name similarity ≥ 85
    - OR duration within ±3 seconds
  Without a corroborating field, no candidate is created — even at 100% title match.
* Version-aware: if EITHER record has a version token ("live", "remix", "acoustic",
  "demo", "radio edit", "instrumental") that the other does NOT share, apply a
  0.85 penalty multiplier to the final score (the match may still be proposed,
  but the score is lower and a reason note is added).
* Rejected pairs (status="rejected") are NEVER re-proposed on a re-run. The
  function loads all rejected pair IDs at the start and skips them.
* Score is a weighted composite:
    title_score     × 0.50
    name_score      × 0.30    (best of performer vs writer match)
    duration_score  × 0.20    (1.0 if |diff| ≤ 3s, linearly decreasing to 0.5 at 30s, else 0)
  Then × version_penalty if applicable.
  Only propose if composite ≥ 0.70.
* field_scores dict: {"title": float, "name": float, "duration": float}
* reasons list: human-readable, e.g.
    ["title 94% similar", "performer exact match", "duration 2s apart",
     "version mismatch (live vs studio) — score penalised"]
* Each candidate is saved as a MatchCandidate with status="pending".
* Returns list of saved MatchCandidate objects.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models import MatchCandidate
from app.normaliser import NormalisedRow

# ---------------------------------------------------------------------------
# Version token detection
# ---------------------------------------------------------------------------

VERSION_TOKENS = frozenset({
    "live", "remix", "acoustic", "demo",
    "radio edit", "instrumental", "extended",
})

# Minimum composite score to create a candidate
_MIN_SCORE = 0.70

# Minimum name similarity to count as corroboration
_NAME_CORROBORATION_THRESHOLD = 0.85

# Maximum duration diff (seconds) to count as corroboration
_DURATION_CORROBORATION_MAX_S = 3.0

# Version mismatch penalty multiplier
_VERSION_PENALTY = 0.85


def _extract_version_tokens(version_str: str) -> frozenset[str]:
    """Extract version tokens from a version/title string."""
    lower = version_str.lower()
    return frozenset(t for t in VERSION_TOKENS if t in lower)


def _title_score(t1: str, t2: str) -> float:
    """token_sort_ratio normalised to 0-1."""
    return fuzz.token_sort_ratio(t1, t2) / 100.0


def _name_score(rec_nr: NormalisedRow, wrk_nr: NormalisedRow) -> float:
    """Best of performer vs writer comparison."""
    performer = (
        rec_nr.normalised.get("performer", "")
        or rec_nr.normalised.get("contributor_name", "")
    )
    writer = (
        wrk_nr.normalised.get("writers", "")
        or wrk_nr.normalised.get("contributor_name", "")
    )
    if not performer or not writer:
        return 0.0
    return fuzz.token_sort_ratio(performer, writer) / 100.0


def _parse_duration(dur_val: Any) -> float | None:
    """
    Convert a duration value (Decimal, str, float, or None) to float seconds.
    Returns None when the value is missing or cannot be converted.
    """
    if dur_val is None:
        return None
    if isinstance(dur_val, Decimal):
        return float(dur_val)
    try:
        f = float(str(dur_val).strip())
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def _duration_score(dur1_val: Any, dur2_val: Any) -> tuple[float, str]:
    """
    Returns (score, reason_str).

    score:
      1.0 if |diff| ≤ 3s
      linearly from 1.0 → 0.5 between 3s and 30s
      0.0 beyond 30s or when either duration is missing
    reason_str: e.g. "duration 2s apart" or "duration too different (45s)"
    """
    d1 = _parse_duration(dur1_val)
    d2 = _parse_duration(dur2_val)

    if d1 is None or d2 is None:
        return 0.0, "duration unknown"

    diff = abs(d1 - d2)

    if diff <= 3.0:
        return 1.0, f"duration {int(round(diff))}s apart"

    if diff <= 30.0:
        # linear: at diff=3 → 1.0, at diff=30 → 0.5
        score = 1.0 - 0.5 * (diff - 3.0) / 27.0
        return score, f"duration {int(round(diff))}s apart"

    return 0.0, f"duration too different ({int(round(diff))}s)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def propose_fuzzy_candidates(
    db: Session,
    case_id: int,
    recording_nrows: list[NormalisedRow],
    work_nrows: list[NormalisedRow],
    already_linked_recording_ids: set[int],  # Record.id values already exact-linked
) -> list[MatchCandidate]:
    """
    Propose fuzzy MatchCandidate links for (recording, work) pairs that were
    NOT linked by the exact-match linker.

    Parameters
    ----------
    db : Session
        Active SQLAlchemy session.
    case_id : int
    recording_nrows : list[NormalisedRow]
        Each must have source_ref["record_id"] set.
    work_nrows : list[NormalisedRow]
        Each must have source_ref["record_id"] set.
    already_linked_recording_ids : set[int]
        Recording Record.id values that already have an exact link.
        These are skipped to avoid double-proposing.

    Returns
    -------
    list[MatchCandidate]
        All MatchCandidate rows created this run.
    """
    # ------------------------------------------------------------------
    # Load existing MatchCandidate metadata for this case from DB
    # ------------------------------------------------------------------
    existing_candidates = (
        db.query(MatchCandidate)
        .filter(MatchCandidate.case_id == case_id)
        .all()
    )

    # Build a set of recording IDs that ALREADY have any candidate
    # (to skip recordings already handled by the exact linker or prior runs)
    already_has_candidate: set[int] = {
        c.left_record_id for c in existing_candidates
    }

    # Build a set of rejected pairs (left_id, right_id) — never re-propose
    rejected_pairs: set[tuple[int, int]] = {
        (c.left_record_id, c.right_record_id)
        for c in existing_candidates
        if c.status == "rejected"
    }

    saved: list[MatchCandidate] = []

    for rec_nr in recording_nrows:
        rec_record_id: int = rec_nr.source_ref.get("record_id", 0)
        if not rec_record_id:
            continue

        # Skip recordings already linked by exact matcher
        if rec_record_id in already_linked_recording_ids:
            continue

        # Skip recordings that already have any candidate (any status)
        if rec_record_id in already_has_candidate:
            continue

        rec_title = rec_nr.normalised.get("title", "") or ""
        rec_version = rec_nr.normalised.get("version", "") or ""
        rec_duration_raw = rec_nr.normalised.get("duration_seconds")
        rec_tokens = _extract_version_tokens(rec_title + " " + rec_version)

        for wrk_nr in work_nrows:
            wrk_record_id: int = wrk_nr.source_ref.get("record_id", 0)
            if not wrk_record_id:
                continue

            # Skip rejected pairs
            if (rec_record_id, wrk_record_id) in rejected_pairs:
                continue

            wrk_title = wrk_nr.normalised.get("title", "") or ""
            wrk_version = wrk_nr.normalised.get("version", "") or ""
            wrk_duration_raw = wrk_nr.normalised.get("duration_seconds")
            wrk_tokens = _extract_version_tokens(wrk_title + " " + wrk_version)

            # --- Compute individual scores ---
            ts = _title_score(rec_title, wrk_title)
            ns = _name_score(rec_nr, wrk_nr)
            ds, dur_reason = _duration_score(rec_duration_raw, wrk_duration_raw)

            # --- Corroboration check ---
            # Need at least one corroborating field besides title.
            # Corroboration: name_score ≥ 0.85 OR duration within ±3s
            has_name_corroboration = ns >= _NAME_CORROBORATION_THRESHOLD
            has_duration_corroboration = ds == 1.0  # only exact (≤3s) counts

            if not has_name_corroboration and not has_duration_corroboration:
                continue  # no corroboration — skip even at 100% title match

            # --- Composite score ---
            composite = ts * 0.50 + ns * 0.30 + ds * 0.20

            # --- Version mismatch penalty ---
            version_penalised = False
            version_reason: str | None = None

            if rec_tokens or wrk_tokens:
                # Tokens present on at least one side
                rec_only = rec_tokens - wrk_tokens
                wrk_only = wrk_tokens - rec_tokens
                if rec_only or wrk_only:
                    composite *= _VERSION_PENALTY
                    version_penalised = True
                    rec_label = ", ".join(sorted(rec_only)) if rec_only else "studio"
                    wrk_label = ", ".join(sorted(wrk_only)) if wrk_only else "studio"
                    version_reason = (
                        f"version mismatch ({rec_label} vs {wrk_label}) — score penalised"
                    )

            # --- Threshold gate ---
            if composite < _MIN_SCORE:
                continue

            # --- Build reasons ---
            reasons: list[str] = []

            title_pct = int(round(ts * 100))
            if ts == 1.0:
                reasons.append("title exact match")
            else:
                reasons.append(f"title {title_pct}% similar")

            name_pct = int(round(ns * 100))
            if has_name_corroboration:
                if ns == 1.0:
                    reasons.append("performer exact match")
                else:
                    reasons.append(f"performer/writer {name_pct}% similar")

            if dur_reason != "duration unknown":
                reasons.append(dur_reason)

            if version_penalised and version_reason:
                reasons.append(version_reason)

            # --- Build field_scores ---
            field_scores: dict[str, float] = {
                "title": round(ts, 5),
                "name": round(ns, 5),
                "duration": round(ds, 5),
            }

            # --- Persist ---
            candidate = MatchCandidate(
                case_id=case_id,
                left_record_id=rec_record_id,
                right_record_id=wrk_record_id,
                score=float(composite),
                field_scores=field_scores,
                reasons=reasons,
                status="pending",
            )
            db.add(candidate)
            db.flush()  # populate candidate.id

            saved.append(candidate)

    return saved
