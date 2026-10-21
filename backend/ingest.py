"""
ingest.py — File parsing and DB storage for SoundDue uploads.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from database import Mapping, OwnershipClaim, Recording, UploadBatch, Work


# ---------------------------------------------------------------------------
# Column normalisation
# ---------------------------------------------------------------------------
def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip, replace spaces with underscores in column names."""
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # Strip whitespace from all string cells
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------
def parse_file(path: str | Path, file_type: str) -> pd.DataFrame:
    """
    Read CSV or Excel file, normalise columns, return DataFrame.

    Parameters
    ----------
    path      : path to the uploaded file
    file_type : one of 'recordings' | 'works' | 'ownership' | 'mappings'
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        raise ValueError(f"Unsupported file extension: {suffix!r}")

    df = _normalize_columns(df)
    return df


# ---------------------------------------------------------------------------
# store_batch
# ---------------------------------------------------------------------------
def store_batch(
    df: pd.DataFrame,
    file_type: str,
    filename: str,
    db_session,
) -> UploadBatch:
    """
    Persist a parsed DataFrame into the appropriate table.
    Returns the created UploadBatch record.

    Raises ValueError for invalid ownership share_pct values.
    """
    batch = UploadBatch(
        filename=filename,
        upload_time=datetime.utcnow(),
        row_count=len(df),
        file_type=file_type,
    )
    db_session.add(batch)
    db_session.flush()  # get batch.id

    if file_type == "recordings":
        for _, row in df.iterrows():
            raw = _row_to_dict(row)
            rec = Recording(
                batch_id=batch.id,
                isrc=row.get("isrc"),
                title=row.get("title"),
                artist=row.get("artist"),
                duration_secs=_int_or_none(row.get("duration_secs")),
                raw_json=raw,
            )
            db_session.add(rec)

    elif file_type == "works":
        for _, row in df.iterrows():
            raw = _row_to_dict(row)
            work = Work(
                batch_id=batch.id,
                iswc=row.get("iswc"),
                title=row.get("title"),
                composer=row.get("composer"),
                publisher=row.get("publisher"),
                raw_json=raw,
            )
            db_session.add(work)

    elif file_type == "ownership":
        for idx, row in df.iterrows():
            share_raw = row.get("share_pct")
            try:
                share_val = float(share_raw)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Row {idx}: share_pct must be numeric, got {share_raw!r}"
                )
            if not (0 < share_val <= 100):
                raise ValueError(
                    f"Row {idx}: share_pct must be between 0 (exclusive) and 100 (inclusive), got {share_val}"
                )
            raw = _row_to_dict(row)
            claim = OwnershipClaim(
                batch_id=batch.id,
                rights_holder=row.get("rights_holder"),
                work_iswc=row.get("work_iswc"),
                share_pct=share_val,
                rights_category=row.get("rights_category"),
                territory=row.get("territory"),
                period_start=row.get("period_start"),
                period_end=row.get("period_end"),
                raw_json=raw,
            )
            db_session.add(claim)

    elif file_type == "mappings":
        for _, row in df.iterrows():
            raw = _row_to_dict(row)
            mapping = Mapping(
                batch_id=batch.id,
                recording_isrc=row.get("recording_isrc"),
                work_iswc=row.get("work_iswc"),
                source_label=row.get("source_label"),
                raw_json=raw,
            )
            db_session.add(mapping)

    else:
        raise ValueError(f"Unknown file_type: {file_type!r}")

    db_session.commit()
    db_session.refresh(batch)
    return batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_to_dict(row: pd.Series) -> dict:
    """Convert a pandas Series row to a plain Python dict (JSON-safe)."""
    return {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}


def _int_or_none(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(float(str(val)))
    except (TypeError, ValueError):
        return None
