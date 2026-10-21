"""
backend/app/schemas/inputs.py
=============================
Pydantic v2 models for every *input* row type SoundDue can ingest.

Design notes
------------
- ``RecordingRow`` and ``WorkRow`` are separate models because recordings and
  works are distinct entities in music rights administration.  A recording
  (phonogram) is a specific sound capture; a work (musical composition) is the
  underlying song.  One work can have many recordings; the link between them
  must be explicit, not inferred from a title match.

- ``share`` is validated as ``Decimal`` (not float) so that arithmetic on
  ownership totals is exact. Floats cannot represent fractions like 33.333...
  without rounding error.

- Every row model carries a ``source`` field (``SourceRef``) so every datum
  can be traced back to the exact file name and row number it came from.

- ``status`` on ``OwnershipClaim`` uses a controlled vocabulary.  "Missing
  from the supplied records" is the default reading of an absent share; only a
  source that *explicitly* marks a share "unclaimed" warrants that label.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# SourceRef -- provenance anchor carried by every row model
# ---------------------------------------------------------------------------
class SourceRef(BaseModel):
    """Tracks where a data row came from so every field is fully traceable."""

    model_config = ConfigDict(frozen=True)

    file_name: str = Field(..., description="Original file name as uploaded.")
    row_number: int = Field(..., ge=1, description="1-based row number in the source file.")
    raw_values: dict[str, Any] = Field(
        default_factory=dict,
        description="The raw cell values from the source row, keyed by header name.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_EMPTY_RE = re.compile(r"^\s*$")


def _require_nonempty(v: str | None, field_name: str) -> str:
    if v is None or _EMPTY_RE.match(v):
        raise ValueError(f"{field_name} must not be empty or whitespace-only.")
    return v.strip()


def _parse_decimal_share(v: Any) -> Decimal:
    """
    Accept int, float, str, or Decimal and return a Decimal.
    Floats are converted via their string representation to preserve intent
    (e.g. 33.33) rather than introducing binary floating-point noise.
    """
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        v = str(v)
    try:
        return Decimal(str(v))
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse share as Decimal: {v!r}") from exc


# ---------------------------------------------------------------------------
# RecordingRow
# ---------------------------------------------------------------------------
class RecordingRow(BaseModel):
    """
    A single row from a *recordings* input file.

    A recording is a phonogram -- the specific audio capture of a performance.
    It is identified by an ISRC and is distinct from the underlying musical
    work (composition).
    """

    model_config = ConfigDict(frozen=True)

    recording_id: str = Field(..., description="Unique identifier for this recording.")
    title: str = Field(..., description="Title of the recording.")
    performer: str | None = Field(None, description="Performing artist or group.")
    version: str | None = Field(None, description="Version label, e.g. 'Radio Edit'.")
    duration_seconds: int | None = Field(
        None, ge=0, description="Track duration in whole seconds."
    )
    isrc: str | None = Field(
        None,
        pattern=r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$",
        description="International Standard Recording Code (12-char).",
    )
    source: SourceRef = Field(..., description="Provenance of this row.")

    @field_validator("recording_id", mode="before")
    @classmethod
    def validate_recording_id(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "recording_id")

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "title")


# ---------------------------------------------------------------------------
# WorkRow
# ---------------------------------------------------------------------------
class WorkRow(BaseModel):
    """
    A single row from a *works* input file.

    A work is a musical composition -- the song itself, independent of any
    particular recording.  Works are administered by publishers and CMOs
    separately from recordings.  Linking a recording to a work requires an
    explicit mapping (see ``Mapping``); title similarity alone is insufficient.
    """

    model_config = ConfigDict(frozen=True)

    work_id: str = Field(..., description="Unique identifier for this work.")
    title: str = Field(..., description="Title of the work.")
    writers: list[str] = Field(
        default_factory=list,
        description="List of composer/lyricist names.",
    )
    iswc: str | None = Field(
        None,
        pattern=r"^T-\d{9}-\d$",
        description="International Standard Musical Work Code (T-XXXXXXXXX-C).",
    )
    source: SourceRef = Field(..., description="Provenance of this row.")

    @field_validator("work_id", mode="before")
    @classmethod
    def validate_work_id(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "work_id")

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "title")

    @field_validator("writers", mode="before")
    @classmethod
    def coerce_writers(cls, v: Any) -> list[str]:
        """Accept a plain string (comma-separated) or a list."""
        if isinstance(v, str):
            return [w.strip() for w in v.split(",") if w.strip()]
        if v is None:
            return []
        return list(v)


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
class Mapping(BaseModel):
    """
    An explicit recording -> work link supplied by a data source.

    A title match alone never constitutes a mapping.  This record must come
    from an authoritative source (e.g. a DSP, CMO, or rights-holder file).
    """

    model_config = ConfigDict(frozen=True)

    recording_id: str = Field(..., description="References RecordingRow.recording_id.")
    work_id: str = Field(..., description="References WorkRow.work_id.")
    source: SourceRef = Field(..., description="Provenance of this row.")
    source_label: str | None = Field(
        None, description="Name of the organisation that supplied this mapping."
    )
    verified: bool = Field(
        False,
        description="True only if the source explicitly marks this link as verified.",
    )

    @field_validator("recording_id", "work_id", mode="before")
    @classmethod
    def validate_ids(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "id field")


# ---------------------------------------------------------------------------
# Module-level constant for OwnershipClaim status vocabulary.
#
# IMPORTANT: do NOT move this inside the OwnershipClaim class body.
# Pydantic v2 treats any underscore-prefixed class attribute as a
# ModelPrivateAttr, which makes it non-iterable inside field_validators.
# Keeping it at module level avoids that interception entirely.
# ---------------------------------------------------------------------------
_ALLOWED_CLAIM_STATUS: frozenset[str] = frozenset(
    {"claimed", "unclaimed", "disputed", "pending", "unknown"}
)


# ---------------------------------------------------------------------------
# OwnershipClaim
# ---------------------------------------------------------------------------
class OwnershipClaim(BaseModel):
    """
    A single ownership/share claim from a rights-holder or CMO.

    Shares are stored as ``Decimal`` to avoid floating-point rounding.
    Two claims can only be compared when their ``rights_category``,
    ``territory``, ``share_convention``, ``effective_from``, and
    ``effective_to`` are all compatible -- enforced by RULE-004.
    """

    model_config = ConfigDict(frozen=True)

    work_id: str = Field(..., description="The work this claim relates to.")
    contributor_id: str = Field(..., description="Unique ID of the rights holder.")
    contributor_name: str = Field(..., description="Human-readable name of the rights holder.")
    share: Decimal = Field(
        ...,
        description="Ownership share as a percentage (0 < share <= 100). Must be Decimal.",
    )
    share_convention: str = Field(
        ...,
        description=(
            "The share convention used, e.g. 'publisher-share', 'writer-share', "
            "'100-percent-scale'. Shares in different conventions are not addable."
        ),
    )
    rights_category: str = Field(
        ...,
        description="Rights type, e.g. 'mechanical', 'performance', 'sync'.",
    )
    territory: str = Field(
        ...,
        description="Territory code, e.g. 'WW' (worldwide), 'US', 'GB'.",
    )
    effective_from: date = Field(..., description="Start date of the claim period (inclusive).")
    effective_to: date = Field(..., description="End date of the claim period (inclusive).")
    status: str = Field(
        ...,
        description=(
            "Claim status. Allowed values: claimed, unclaimed, disputed, pending, unknown.\n"
            "Use 'unclaimed' only when the source file *explicitly* marks the share as such. "
            "Absent data should be treated as 'missing from the supplied records', not 'unclaimed'."
        ),
    )
    source: SourceRef = Field(..., description="Provenance of this row.")

    @field_validator("work_id", "contributor_id", mode="before")
    @classmethod
    def validate_ids(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "id field")

    @field_validator("contributor_name", mode="before")
    @classmethod
    def validate_name(cls, v: Any) -> str:
        return _require_nonempty(str(v) if v is not None else None, "contributor_name")

    @field_validator("share", mode="before")
    @classmethod
    def validate_share(cls, v: Any) -> Decimal:
        d = _parse_decimal_share(v)
        if d <= Decimal("0") or d > Decimal("100"):
            raise ValueError(
                f"share must be > 0 and <= 100, got {d}. "
                "Note: use Decimal strings like '33.3333', not floats."
            )
        return d

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> str:
        s = str(v).strip().lower()
        if s not in _ALLOWED_CLAIM_STATUS:
            raise ValueError(
                f"status must be one of {sorted(_ALLOWED_CLAIM_STATUS)}, got {s!r}."
            )
        return s

    @model_validator(mode="after")
    def effective_dates_in_order(self) -> "OwnershipClaim":
        if self.effective_to < self.effective_from:
            raise ValueError(
                f"effective_to ({self.effective_to}) must not be before "
                f"effective_from ({self.effective_from})."
            )
        return self
