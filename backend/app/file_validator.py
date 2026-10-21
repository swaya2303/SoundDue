"""
app/file_validator.py
=====================
Validate an uploaded CSV or XLSX file and return a structured report.

Design notes
------------
* Everything is read as plain strings so leading zeros are preserved.
* Cells starting with = + - @ are sanitised to plain text (formula-injection
  guard) — no error is raised; a note is added to the report.
* Validation reports problems but does NOT block the upload.
* Required-field lists and ID-pattern rules live here; they mirror the
  canonical fields from docs/input-schema.md.
* Duplicate detection uses the full row after stripping; exact duplicates
  only (case-sensitive).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single problem found during validation."""
    file: str
    row: int | None        # 1-based data row (header = row 0); None = file-level
    column: str | None     # column name; None = row-level
    code: str              # machine-readable tag
    message: str
    value: str | None = None  # the offending raw value


@dataclass
class ValidationReport:
    file_name: str
    file_kind: str
    row_count: int
    detected_columns: list[str]
    preview_rows: list[dict[str, str]]   # first ≤10 rows as raw strings
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.code not in {"formula_injection", "note"} for i in self.issues)


# ---------------------------------------------------------------------------
# Per-kind schema rules
# ---------------------------------------------------------------------------

# Required canonical columns for each file kind.
# Values are (canonical_name, list[accepted_header_synonyms])
_SCHEMA: dict[str, list[tuple[str, list[str]]]] = {
    "recordings": [
        ("recording_id", ["recording_id", "track code", "track_code", "isrc"]),
        ("title",        ["title", "track title", "track_title", "song title"]),
    ],
    "works": [
        ("work_id",  ["work_id", "work code", "work_code", "iswc", "composition id"]),
        ("title",    ["title", "work title", "work_title", "song title"]),
    ],
    "ownership": [
        ("work_id",  ["work_id", "work code", "work_code", "composition id",
                      "composition_id", "iswc"]),
        ("share",    ["share", "songwriter %", "songwriter_pct", "share %",
                      "share_pct", "pct", "percentage"]),
    ],
    "mappings": [
        ("recording_id", ["recording_id", "track code", "track_code", "isrc",
                          "recording isrc"]),
        ("work_id",      ["work_id", "work code", "work_code", "iswc",
                          "composition id", "composition_id"]),
    ],
}

# Columns that should look like non-empty IDs (no-empty check)
_ID_COLS: dict[str, list[str]] = {
    "recordings": ["recording_id"],
    "works":      ["work_id"],
    "ownership":  ["work_id"],
    "mappings":   ["recording_id", "work_id"],
}

# Date column pairs (start, end) — end must not be before start
_DATE_PAIRS: dict[str, list[tuple[str, str]]] = {
    "ownership": [("effective_from", "valid_from", "start_date", "period_start",
                   "valid from"),
                  ("effective_to",   "valid_to",   "end_date",   "period_end",
                   "valid to")],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORMULA_CHARS = frozenset("=@")   # + and - are valid numeric prefixes, not injections

_DATE_FMT = "%Y-%m-%d"


def _normalise_header(h: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", h.strip().lower())


def _find_column(df_cols: list[str], synonyms: list[str]) -> str | None:
    """Return the first df column whose normalised name matches any synonym."""
    norm = {_normalise_header(c): c for c in df_cols}
    for syn in synonyms:
        if syn in norm:
            return norm[syn]
    return None


def _sanitise_formula(val: str) -> tuple[str, bool]:
    """
    If val starts with a formula character prefix it with a single-quote
    (CSV formula-injection defence).  Returns (clean_val, was_sanitised).
    """
    if val and val[0] in _FORMULA_CHARS:
        return "'" + val, True
    return val, False


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def _is_valid_share(s: str) -> tuple[bool, float | None]:
    """Return (is_valid, numeric_value_or_None)."""
    try:
        v = float(s.strip().rstrip("%"))
        return 0 < v <= 100, v
    except (ValueError, AttributeError):
        return False, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_file(
    content_bytes: bytes,
    file_kind: str,
    file_name: str,
) -> ValidationReport:
    """
    Parse *content_bytes* (CSV or XLSX) entirely as strings and return a
    ValidationReport.  Never raises — all problems go into the report.

    Parameters
    ----------
    content_bytes : raw file bytes
    file_kind     : "recordings" | "works" | "ownership" | "mappings"
    file_name     : original filename (used in issue messages)
    """
    issues: list[ValidationIssue] = []

    # ------------------------------------------------------------------
    # 1. Parse into a DataFrame — all cells as str, preserve leading zeros
    # ------------------------------------------------------------------
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "csv"
    try:
        if suffix in ("xlsx", "xls"):
            df = pd.read_excel(
                io.BytesIO(content_bytes),
                dtype=str,
                keep_default_na=False,
            )
        else:
            df = pd.read_csv(
                io.BytesIO(content_bytes),
                dtype=str,
                keep_default_na=False,
            )
    except Exception as exc:  # noqa: BLE001
        return ValidationReport(
            file_name=file_name,
            file_kind=file_kind,
            row_count=0,
            detected_columns=[],
            preview_rows=[],
            issues=[
                ValidationIssue(
                    file=file_name,
                    row=None,
                    column=None,
                    code="parse_error",
                    message=f"Could not parse file: {exc}",
                )
            ],
        )

    # Strip whitespace from all string cells
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    raw_columns = list(df.columns)
    row_count = len(df)

    # ------------------------------------------------------------------
    # 2. Formula-injection scan (every cell)
    # ------------------------------------------------------------------
    for col in df.columns:
        for idx, val in df[col].items():
            _, was_sanitised = _sanitise_formula(val)
            if was_sanitised:
                issues.append(ValidationIssue(
                    file=file_name,
                    row=int(idx) + 1,      # idx is 0-based; +1 → data row
                    column=col,
                    code="formula_injection",
                    message=(
                        f"Cell value starts with formula character "
                        f"'{val[0]}' — treated as plain text."
                    ),
                    value=val,
                ))
                df.at[idx, col] = "'" + val   # neutralise in-place

    # ------------------------------------------------------------------
    # 3. Required columns present?
    # ------------------------------------------------------------------
    schema_rules = _SCHEMA.get(file_kind, [])
    canonical_to_actual: dict[str, str | None] = {}
    for canon, synonyms in schema_rules:
        actual = _find_column(raw_columns, synonyms)
        canonical_to_actual[canon] = actual
        if actual is None:
            issues.append(ValidationIssue(
                file=file_name,
                row=None,
                column=canon,
                code="missing_required_column",
                message=(
                    f"Required column '{canon}' not found. "
                    f"Accepted headers: {synonyms}"
                ),
            ))

    # ------------------------------------------------------------------
    # 4. Per-row checks  (only for columns we found)
    # ------------------------------------------------------------------
    norm_cols_lower = {_normalise_header(c): c for c in df.columns}

    # Helper: find actual column by any of these synonyms
    def _actual(synonyms: list[str]) -> str | None:
        for s in synonyms:
            if s in norm_cols_lower:
                return norm_cols_lower[s]
        return None

    for row_idx, row in df.iterrows():
        data_row = int(row_idx) + 1   # 1-based

        # ---- 4a. ID non-empty check ----
        for id_col_canon in _ID_COLS.get(file_kind, []):
            # find actual col name
            synonyms_for_id = next(
                (syns for can, syns in schema_rules if can == id_col_canon),
                [id_col_canon],
            )
            actual_col = canonical_to_actual.get(id_col_canon)
            if actual_col is None:
                continue
            val = str(row.get(actual_col, "")).strip()
            if not val or val.lower() in ("nan", "none", ""):
                issues.append(ValidationIssue(
                    file=file_name,
                    row=data_row,
                    column=actual_col,
                    code="missing_required_field",
                    message=f"Required field '{id_col_canon}' is empty.",
                    value=val or "",
                ))

        # ---- 4b. Share range check (ownership only) ----
        if file_kind == "ownership":
            share_col = canonical_to_actual.get("share")
            if share_col is not None:
                val = str(row.get(share_col, "")).strip()
                valid, numeric = _is_valid_share(val)
                if val and not valid:
                    if numeric is not None:
                        issues.append(ValidationIssue(
                            file=file_name,
                            row=data_row,
                            column=share_col,
                            code="share_out_of_range",
                            message=(
                                f"Share value {val!r} is outside the valid "
                                "range (0, 100]."
                            ),
                            value=val,
                        ))
                    else:
                        issues.append(ValidationIssue(
                            file=file_name,
                            row=data_row,
                            column=share_col,
                            code="share_not_numeric",
                            message=f"Share value {val!r} is not numeric.",
                            value=val,
                        ))

    # ---- 4c. Date-range check (ownership only) ----
    if file_kind == "ownership":
        # Find start and end date columns by any synonym
        start_synonyms = [
            "effective_from", "valid_from", "start_date",
            "period_start", "valid from",
        ]
        end_synonyms = [
            "effective_to", "valid_to", "end_date",
            "period_end", "valid to",
        ]
        start_col = _actual(start_synonyms)
        end_col   = _actual(end_synonyms)

        if start_col and end_col:
            for row_idx, row in df.iterrows():
                data_row = int(row_idx) + 1
                s_raw = str(row.get(start_col, "")).strip()
                e_raw = str(row.get(end_col, "")).strip()
                if not s_raw or not e_raw:
                    continue
                s_date = _parse_date(s_raw)
                e_date = _parse_date(e_raw)
                if s_date is None:
                    issues.append(ValidationIssue(
                        file=file_name,
                        row=data_row,
                        column=start_col,
                        code="bad_date_format",
                        message=f"Cannot parse date {s_raw!r} (expected YYYY-MM-DD).",
                        value=s_raw,
                    ))
                elif e_date is None:
                    issues.append(ValidationIssue(
                        file=file_name,
                        row=data_row,
                        column=end_col,
                        code="bad_date_format",
                        message=f"Cannot parse date {e_raw!r} (expected YYYY-MM-DD).",
                        value=e_raw,
                    ))
                elif e_date < s_date:
                    issues.append(ValidationIssue(
                        file=file_name,
                        row=data_row,
                        column=end_col,
                        code="date_range_invalid",
                        message=(
                            f"End date {e_raw!r} is before start date {s_raw!r}."
                        ),
                        value=e_raw,
                    ))

    # ------------------------------------------------------------------
    # 5. Duplicate-row check (exact match on all columns, after stripping)
    # ------------------------------------------------------------------
    seen: dict[tuple, int] = {}   # row_tuple → first-seen data_row
    for row_idx, row in df.iterrows():
        data_row = int(row_idx) + 1
        key = tuple(str(v) for v in row.values)
        if key in seen:
            issues.append(ValidationIssue(
                file=file_name,
                row=data_row,
                column=None,
                code="duplicate_row",
                message=(
                    f"Row {data_row} is an exact duplicate of row {seen[key]}."
                ),
            ))
        else:
            seen[key] = data_row

    # ------------------------------------------------------------------
    # 6. Build preview (first ≤10 rows, raw strings)
    # ------------------------------------------------------------------
    preview_df = df.head(10)
    preview_rows = preview_df.to_dict(orient="records")

    return ValidationReport(
        file_name=file_name,
        file_kind=file_kind,
        row_count=row_count,
        detected_columns=raw_columns,
        preview_rows=preview_rows,
        issues=issues,
    )
