"""
app/normaliser.py
=================
Convert a raw row dict (canonical field names, all string values) into a
structured NormalisedRow that separates:

  - ``normalised``     Typed canonical values (Decimal for share, strings for
                       IDs/text, "unknown" for missing scope fields).  This is
                       what rules and the linker operate on.

  - ``raw``            The original string values from the source file,
                       completely unmodified.  Used for display and audit.

  - ``comparison_keys`` Derived values used ONLY for candidate generation —
                        casefolded, accent-stripped, whitespace-collapsed
                        versions of title and contributor_name.  These are
                        never written to finding evidence or display text.

Design rules
------------
* Shares are always Decimal.  If the cell can't be parsed, ``share`` is None.
* Scope fields (rights_category, territory, effective_from, effective_to,
  share_convention) default to the sentinel string "unknown" when the source
  cell is missing or blank.  We NEVER guess or infer their values.
* ``verified`` is True only when the source cell is an explicit truthy string
  ("true", "1", "yes", "y").  Any other value, including absence, is False.
* Comparison keys are not stored as canonical values — they exist only to drive
  candidate generation so that two IDs can be looked up regardless of minor
  capitalisation differences.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sentinel value for scope fields that are absent in the source data
UNKNOWN = "unknown"

# Truthy strings recognised for boolean-ish fields like "verified"
_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "y"})

# Scope fields that default to UNKNOWN rather than ""
_SCOPE_FIELDS: tuple[str, ...] = (
    "rights_category",
    "territory",
    "effective_from",
    "effective_to",
    "share_convention",
)


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class NormalisedRow:
    """
    A single data row after normalisation.

    Attributes
    ----------
    normalised : dict
        Typed canonical values.  All string fields that were blank/missing
        remain "".  Scope fields default to UNKNOWN.  share is Decimal or None.
    raw : dict
        Original source-column → cell-value mapping.  Never mutated.
    comparison_keys : dict
        Title/name fields casefolded + accent-stripped.  Used ONLY for
        candidate generation.  Never used as canonical values.
    source_ref : dict
        {"file_name": str, "file_id": int | None, "row_number": int}
    """

    normalised: dict[str, Any]
    raw: dict[str, Any]
    comparison_keys: dict[str, str]
    source_ref: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Remove combining diacritical marks (e.g. é → e, ñ → n)."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def make_comparison_key(text: str) -> str:
    """
    Produce a normalised comparison key from a raw text value.

    Steps:
      1. Strip leading/trailing whitespace
      2. Casefold (Unicode-aware lowercase)
      3. Remove combining accent characters
      4. Collapse internal whitespace runs to a single space

    The result is used ONLY for candidate generation — never as a canonical
    field value or in evidence/display text.
    """
    if not text:
        return ""
    s = text.strip().casefold()
    s = _strip_accents(s)
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------------------
# Type coercions
# ---------------------------------------------------------------------------

def _coerce_decimal(raw_val: str) -> Optional[Decimal]:
    """Return Decimal or None; never raise."""
    v = str(raw_val).strip()
    if not v:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        return None


def _coerce_bool_verified(raw_val: str) -> bool:
    """True only for explicit truthy strings. Absence → False."""
    return str(raw_val).strip().lower() in _TRUE_STRINGS


def _coerce_scope(raw_val: str, field_name: str) -> str:
    """Scope fields: return value if non-blank, else UNKNOWN. Never guess."""
    v = str(raw_val).strip()
    return v if v else UNKNOWN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalise_row(
    raw_canonical: dict[str, str],   # canonical field names → raw cell strings
    original_cells: dict[str, str],  # source column names → raw cell strings
    source_ref: dict[str, Any] | None = None,
) -> NormalisedRow:
    """
    Convert one row from the apply-mapping stage into a NormalisedRow.

    Parameters
    ----------
    raw_canonical : dict
        Keys are canonical field names (after column mapping), values are the
        raw cell strings from the source file.
    original_cells : dict
        Keys are *source* column names, values are raw cell strings.
        Stored verbatim in NormalisedRow.raw.
    source_ref : dict, optional
        Provenance metadata for the row.
    """
    n: dict[str, Any] = {}

    # -- Identifiers (strip, keep as-is) --
    for id_field in ("recording_id", "work_id", "isrc", "iswc",
                     "contributor_id", "contributor_name",
                     "title", "writers", "performer", "version",
                     "source", "status", "source_label"):
        v = raw_canonical.get(id_field, "")
        n[id_field] = str(v).strip()

    # -- Numeric fields --
    n["share"] = _coerce_decimal(raw_canonical.get("share", ""))
    n["duration_seconds"] = _coerce_decimal(raw_canonical.get("duration_seconds", ""))

    # -- Boolean fields --
    n["verified"] = _coerce_bool_verified(raw_canonical.get("verified", ""))

    # -- Scope fields (default to UNKNOWN, never "") --
    for sf in _SCOPE_FIELDS:
        n[sf] = _coerce_scope(raw_canonical.get(sf, ""), sf)

    # -- Comparison keys (derived, never stored as canonical values) --
    ck: dict[str, str] = {
        "title_key":            make_comparison_key(n.get("title", "")),
        "contributor_name_key": make_comparison_key(n.get("contributor_name", "")),
        "performer_key":        make_comparison_key(n.get("performer", "")),
        "writers_key":          make_comparison_key(n.get("writers", "")),
    }

    return NormalisedRow(
        normalised=n,
        raw=dict(original_cells),          # verbatim copy
        comparison_keys=ck,
        source_ref=source_ref or {},
    )


def normalise_rows(
    canonical_rows: list[dict[str, str]],
    original_rows: list[dict[str, str]],
    source_ref_base: dict[str, Any] | None = None,
) -> list[NormalisedRow]:
    """
    Normalise a batch of rows from one file.

    ``canonical_rows``  — list of {canonical_field: raw_string} dicts
    ``original_rows``   — list of {source_column: raw_string} dicts, same length
    ``source_ref_base`` — base dict merged with row_number for each row's source_ref
    """
    base = dict(source_ref_base or {})
    return [
        normalise_row(
            raw_canonical=c,
            original_cells=o,
            source_ref={**base, "row_number": i},
        )
        for i, (c, o) in enumerate(zip(canonical_rows, original_rows), start=1)
    ]
