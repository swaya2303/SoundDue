"""
app/column_mapper.py
====================
Map source-file column headers to canonical SoundDue field names.

Resolution order (first match wins)
------------------------------------
1. Exact synonym dictionary lookup (case-insensitive, stripped)
2. RapidFuzz token-sort-ratio on synonym keys (threshold 70)
3. suggest_with_llm() stub — always returns None; marked for future work

The synonym dictionary is the authoritative source of truth; it mirrors the
accepted-header tables in docs/input-schema.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process

# ---------------------------------------------------------------------------
# Synonym dictionary
# ---------------------------------------------------------------------------
# canonical field name → list of accepted source-header aliases (lowercased)

SYNONYMS: dict[str, list[str]] = {
    # -- recordings --
    "recording_id": [
        "recording_id", "recording id", "track code", "track_code",
        "isrc", "track id", "track_id", "rec id", "rec_id",
    ],
    "title": [
        "title", "track title", "track_title", "song title", "song_title",
        "work title", "work_title", "name",
    ],
    "performer": [
        "performer", "artist", "artist name", "artist_name",
        "main artist", "main_artist", "band", "act",
    ],
    "version": [
        "version", "mix", "version label", "version_label", "variant",
    ],
    "duration_seconds": [
        "duration_seconds", "duration", "duration secs", "duration_secs",
        "length", "length_seconds", "length secs", "runtime",
    ],
    "isrc": [
        "isrc", "isrc code", "isrc_code",
    ],

    # -- works --
    "work_id": [
        "work_id", "work id", "work code", "work_code",
        "iswc", "composition id", "composition_id",
        "work ref", "work_ref",
    ],
    "writers": [
        "writers", "writer", "composer", "composers",
        "songwriter", "songwriters", "author", "authors",
    ],
    "iswc": [
        "iswc", "iswc code", "iswc_code",
    ],

    # -- ownership --
    "contributor_id": [
        "contributor_id", "contributor id", "writer code", "writer_code",
        "writer id", "writer_id", "rights holder id", "rights_holder_id",
        "party id", "party_id",
    ],
    "contributor_name": [
        "contributor_name", "contributor name", "rights holder",
        "rights_holder", "songwriter name", "songwriter_name",
        "writer name", "writer_name", "party name", "party_name",
    ],
    "share": [
        "share", "songwriter %", "songwriter_pct", "share %", "share_pct",
        "pct", "percentage", "ownership %", "ownership_pct",
        "royalty %", "royalty_pct", "split", "split %",
    ],
    "share_convention": [
        "share_convention", "convention", "share convention",
        "share type", "share_type", "basis",
    ],
    "rights_category": [
        "rights_category", "rights category", "rights type", "rights_type",
        "right type", "right_type", "category", "rights",
    ],
    "territory": [
        "territory", "territories", "region", "market", "country",
    ],
    "effective_from": [
        "effective_from", "effective from", "valid from", "valid_from",
        "start date", "start_date", "period start", "period_start",
        "from date", "from_date",
    ],
    "effective_to": [
        "effective_to", "effective to", "valid to", "valid_to",
        "end date", "end_date", "period end", "period_end",
        "to date", "to_date",
    ],
    "status": [
        "status", "claim status", "claim_status", "ownership status",
        "ownership_status",
    ],

    # -- mappings --
    # recording_id and work_id covered above
    "source": [
        "source", "source label", "source_label", "origin",
        "data source", "data_source", "provided by", "provided_by",
    ],
    "verified": [
        "verified", "confirmed", "is verified", "is_verified",
    ],
}

# Required canonical fields per file kind (used by the analyze gate)
REQUIRED_CANONICAL: dict[str, list[str]] = {
    "recordings": ["recording_id", "title"],
    "works":      ["work_id", "title"],
    "ownership":  ["work_id", "share"],
    "mappings":   ["recording_id", "work_id"],
}

# Flat alias → canonical lookup (built once at import time)
_ALIAS_TO_CANON: dict[str, str] = {
    alias: canon
    for canon, aliases in SYNONYMS.items()
    for alias in aliases
}

# All known aliases as a flat list for fuzzy matching
_ALL_ALIASES: list[str] = list(_ALIAS_TO_CANON.keys())


# ---------------------------------------------------------------------------
# Public data structure
# ---------------------------------------------------------------------------

@dataclass
class ColumnSuggestion:
    source_column: str
    best_canonical: Optional[str]   # top suggestion (None = no confident match)
    confidence: str                 # "exact" | "fuzzy" | "none"
    score: float                    # 1.0 for exact, 0.0–1.0 for fuzzy
    alternatives: list[dict]        # [{"canonical": ..., "score": ...}, ...]
    method: str                     # "synonym_exact" | "rapidfuzz" | "none"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _canon_for(alias: str) -> str:
    """Return canonical field name for a (lowercased) alias."""
    return _ALIAS_TO_CANON.get(alias, alias)


# ---------------------------------------------------------------------------
# LLM stub  (stretch goal — intentionally inert)
# ---------------------------------------------------------------------------

def suggest_with_llm(source_column: str, file_kind: str) -> Optional[str]:  # noqa: ARG001
    """
    STUB — LLM-based column suggestion.

    Always returns None.  A future implementation would send the source
    column name, the file kind, and the canonical schema to an LLM and
    return its best-guess canonical field name for human review.

    Constraint: this must never invent share values, amounts, or record
    matches — it may only name a canonical field.

    To activate: replace the body with an LLM API call.
    """
    return None  # LLM integration: stretch goal only


# ---------------------------------------------------------------------------
# Core mapping logic
# ---------------------------------------------------------------------------

def suggest_column(
    source_column: str,
    file_kind: str = "",
    fuzzy_threshold: float = 70.0,
    max_alternatives: int = 3,
) -> ColumnSuggestion:
    """
    Suggest a canonical field name for one source column header.

    Resolution order:
      1. Exact match in synonym dictionary (case-insensitive)
      2. RapidFuzz token_sort_ratio ≥ fuzzy_threshold
      3. suggest_with_llm() stub → always None
    """
    norm = _norm(source_column)

    # 1. Exact synonym lookup
    if norm in _ALIAS_TO_CANON:
        return ColumnSuggestion(
            source_column=source_column,
            best_canonical=_ALIAS_TO_CANON[norm],
            confidence="exact",
            score=1.0,
            alternatives=[],
            method="synonym_exact",
        )

    # 2. RapidFuzz fuzzy match
    results = fuzz_process.extract(
        norm,
        _ALL_ALIASES,
        scorer=fuzz.token_sort_ratio,
        limit=max_alternatives + 5,   # fetch extra so dedup has room
    )
    # results: list of (matched_alias, score, index)
    above = [(alias, score) for alias, score, _ in results if score >= fuzzy_threshold]

    if above:
        best_alias, best_score = above[0]
        best_canon = _canon_for(best_alias)

        seen: set[str] = {best_canon}
        alts: list[dict] = []
        for alias, score in above[1:]:
            c = _canon_for(alias)
            if c not in seen:
                alts.append({"canonical": c, "score": round(score / 100, 3)})
                seen.add(c)
            if len(alts) >= max_alternatives:
                break

        return ColumnSuggestion(
            source_column=source_column,
            best_canonical=best_canon,
            confidence="fuzzy",
            score=round(best_score / 100, 3),
            alternatives=alts,
            method="rapidfuzz",
        )

    # 3. LLM stub (always None for now)
    _ = suggest_with_llm(source_column, file_kind)

    return ColumnSuggestion(
        source_column=source_column,
        best_canonical=None,
        confidence="none",
        score=0.0,
        alternatives=[],
        method="none",
    )


def suggest_all_columns(
    source_columns: list[str],
    file_kind: str = "",
    fuzzy_threshold: float = 70.0,
) -> list[ColumnSuggestion]:
    """Return a ColumnSuggestion for every column in the source file."""
    return [
        suggest_column(col, file_kind=file_kind, fuzzy_threshold=fuzzy_threshold)
        for col in source_columns
    ]
