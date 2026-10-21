"""
app/analyzer.py
===============
Case-scoped analysis engine for SoundDue.

Pipeline
--------
1. For each uploaded file in the case, read its content through the confirmed
   ColumnMapping rows to produce normalised dicts (canonical field names).
2. Save each row as a ``Record`` (record_type = file_kind, version = 1).
   Rows that were already stored in a previous run are superseded.
3. Run four explicit rules against the normalised data:

   R1  possible_missing_claim
       An ownership row is explicitly labelled "unclaimed".  A named claimant
       may exist but was not supplied.

   R2  incomplete_ownership_info
       Shares for a (work_id, rights_category, territory, period) scope do not
       sum to 100 % and NO row in that scope is labelled "unclaimed".  The gap
       is silent — the source simply omitted data.

   R3  conflicting_shares
       Two or more rows for the same contributor in the same scope (work_id,
       rights_category, territory, period) report different share values.  This
       can happen when two ownership files are uploaded for the same case.

   R4  unlinked_recording
       A recording in the recordings file has no verified mapping row pointing
       to it (verified == "true" / True / 1).

Rules are purely symbolic — no statistics, no fuzzy matching of share values.
Each rule returns a list of finding dicts compatible with repository.save_findings().

Prototype note
--------------
Rule evaluation is always a full re-run.  Existing Finding rows for the case
are NOT deleted; the caller may choose to clear them before calling run_analysis()
if idempotency is required.  For the prototype a fresh run is additive.
"""

from __future__ import annotations

import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.column_mapper import REQUIRED_CANONICAL
from app.fuzzy_matcher import propose_fuzzy_candidates
from app.linker import generate_links
from app.models import ColumnMapping, Record, UploadedFile
from app.normaliser import NormalisedRow, normalise_rows
from app.repository import DEMO_USER, log_audit_event, save_findings, save_records

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_UNCLAIMED_LABELS: frozenset[str] = frozenset(
    {"unclaimed", "unregistered", "unknown", "pool"}
)

_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "y"})


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_file_bytes(uf: UploadedFile) -> bytes:
    with open(uf.storage_path, "rb") as fh:
        return fh.read()


def _parse_to_df(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV or XLSX as raw strings (preserve leading zeros)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
    else:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(df.notna(), "")  # replace NaN with empty string


def _apply_mapping(df: pd.DataFrame, mappings: list[ColumnMapping]) -> pd.DataFrame:
    """
    Rename source columns to canonical names using confirmed ColumnMapping rows.
    Only columns with a confirmed mapping are included in the result; extra
    columns are silently dropped.
    """
    rename = {cm.source_column: cm.canonical_field for cm in mappings if cm.confirmed}
    # Keep only mapped columns
    keep = [c for c in df.columns if c in rename]
    return df[keep].rename(columns=rename)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _to_decimal(val: str) -> Decimal | None:
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError):
        return None


def _is_unclaimed(status_val: str) -> bool:
    return status_val.strip().lower() in _UNCLAIMED_LABELS


def _is_verified(val: str) -> bool:
    return str(val).strip().lower() in _TRUE_STRINGS


# ---------------------------------------------------------------------------
# Record ingestion
# ---------------------------------------------------------------------------

def _ingest_file(
    db: Session,
    uf: UploadedFile,
    mappings: list[ColumnMapping],
) -> list[NormalisedRow]:
    """
    Read the file, apply column mapping, normalise rows via app.normaliser,
    persist Record rows, and return a list of NormalisedRow objects with
    source_ref["record_id"] populated.
    """
    content = _read_file_bytes(uf)
    df = _parse_to_df(content, uf.original_name)
    norm_df = _apply_mapping(df, mappings)

    canonical_rows = norm_df.to_dict(orient="records")   # [{canon_field: raw_str}]
    # Build original_cells: source column → raw cell value per row
    mapped_source_cols = [cm.source_column for cm in mappings if cm.confirmed]
    original_rows = [
        {col: str(df.iloc[i][col]) for col in df.columns if col in mapped_source_cols}
        for i in range(len(df))
    ]

    nrows = normalise_rows(
        canonical_rows=canonical_rows,
        original_rows=original_rows,
        source_ref_base={"file_name": uf.original_name, "file_id": uf.id},
    )

    # Build record_dicts for DB storage; convert Decimal to str for JSON
    record_dicts: list[dict[str, Any]] = []
    for nr in nrows:
        norm_json = {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in nr.normalised.items()
        }
        record_dicts.append({
            "normalised": norm_json,
            "raw": nr.raw,
            "source_row": nr.source_ref["row_number"],
        })

    saved_records = save_records(
        db,
        case_id=uf.case_id,
        records=record_dicts,
        record_type=uf.file_type.rstrip("s"),  # "recordings" → "recording"
        source_file_id=uf.id,
    )

    # Attach DB record IDs to source_ref so the linker can reference them
    for nr, rec in zip(nrows, saved_records):
        nr.source_ref["record_id"] = rec.id

    return nrows


# ---------------------------------------------------------------------------
# Rule R1 — possible_missing_claim
# ---------------------------------------------------------------------------

def _rule_r1(ownership_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fires when an ownership row is explicitly labelled 'unclaimed' (or
    equivalent).  A named claimant may exist but was not supplied.

    Finding type: possible_missing_claim
    Severity: warning
    """
    findings: list[dict[str, Any]] = []
    for row in ownership_rows:
        status = row.get("status", "")
        if _is_unclaimed(status):
            work_id = row.get("work_id", "?")
            share_raw = row.get("share", "")
            rights = row.get("rights_category", "")
            territory = row.get("territory", "")
            findings.append({
                "rule_id": "R1",
                "rule_version": "1.0",
                "finding_type": "possible_missing_claim",
                "severity": "warning",
                "summary": (
                    f"Explicit 'unclaimed' label for {work_id} / {rights} / {territory}: "
                    f"{share_raw} % marked unclaimed — a named claimant may exist."
                ),
                "uncertainty": (
                    "The source explicitly reserves this share as unclaimed. "
                    "A rights holder may exist but was not provided in this upload."
                ),
                "next_step": (
                    "Obtain the complete registration schedule from the relevant CMO "
                    "or publisher and verify whether a claimant should be named."
                ),
                "evidence": {
                    "work_id": work_id,
                    "share": share_raw,
                    "rights_category": rights,
                    "territory": territory,
                    "status": status,
                    "row_data": row,
                },
                "matched_conditions": [
                    f"status == '{status}' (unclaimed label detected)"
                ],
                "supporting_record_ids": [],
                "missing_information": [
                    "Identity of the rights holder who should hold this share"
                ],
                "conflicting_information": [],
            })
    return findings


# ---------------------------------------------------------------------------
# Rule R2 — incomplete_ownership_info
# ---------------------------------------------------------------------------

def _rule_r2(ownership_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fires when shares for a scope (work_id, rights_category, territory,
    effective_from, effective_to) sum to < 100 % AND no row in that scope
    carries an explicit 'unclaimed' label.

    Finding type: incomplete_ownership_info
    Severity: warning
    """
    # Group by scope
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in ownership_rows:
        scope = (
            row.get("work_id", ""),
            row.get("rights_category", ""),
            row.get("territory", ""),
            row.get("effective_from", ""),
            row.get("effective_to", ""),
        )
        groups[scope].append(row)

    findings: list[dict[str, Any]] = []
    for scope, rows in groups.items():
        work_id, rights, territory, eff_from, eff_to = scope

        # Skip scope if ANY row is explicitly unclaimed (that's R1's job)
        if any(_is_unclaimed(r.get("status", "")) for r in rows):
            continue

        total = Decimal("0")
        for r in rows:
            d = _to_decimal(r.get("share", "0"))
            if d is not None:
                total += d

        if total < Decimal("99.99"):
            findings.append({
                "rule_id": "R2",
                "rule_version": "1.0",
                "finding_type": "incomplete_ownership_info",
                "severity": "warning",
                "summary": (
                    f"Shares for {work_id} / {rights} / {territory} "
                    f"sum to {total:.4f} % — {100 - total:.4f} % not accounted for "
                    f"in the supplied records."
                ),
                "uncertainty": (
                    "The gap may reflect omitted rows rather than a genuine gap in "
                    "registered ownership.  No 'unclaimed' label was present to "
                    "indicate the source was aware of the missing share."
                ),
                "next_step": (
                    "Supply complete ownership schedules for this work, territory, "
                    "and rights category covering the relevant period."
                ),
                "evidence": {
                    "work_id": work_id,
                    "rights_category": rights,
                    "territory": territory,
                    "effective_from": eff_from,
                    "effective_to": eff_to,
                    "total_share": str(total),
                    "gap": str(Decimal("100") - total),
                    "row_count": len(rows),
                    "rows": rows,
                },
                "matched_conditions": [
                    f"sum(share) == {total:.4f} < 100",
                    "no row in scope has unclaimed status",
                ],
                "supporting_record_ids": [],
                "missing_information": [
                    f"Ownership rows accounting for the remaining {100 - total:.4f} %"
                ],
                "conflicting_information": [],
            })
    return findings


# ---------------------------------------------------------------------------
# Rule R3 — conflicting_shares
# ---------------------------------------------------------------------------

def _rule_r3(ownership_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fires when the same contributor (by contributor_id) in the same scope
    appears with two different share values.  This can arise when two
    ownership files report different figures for the same period.

    Scope key: (work_id, contributor_id, rights_category, territory,
                effective_from, effective_to)

    Finding type: conflicting_shares
    Severity: error
    """
    # Group by (scope + contributor)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in ownership_rows:
        cid = row.get("contributor_id", row.get("contributor_name", "?"))
        scope = (
            row.get("work_id", ""),
            cid,
            row.get("rights_category", ""),
            row.get("territory", ""),
            row.get("effective_from", ""),
            row.get("effective_to", ""),
        )
        groups[scope].append(row)

    findings: list[dict[str, Any]] = []
    for scope, rows in groups.items():
        if len(rows) < 2:
            continue
        work_id, cid, rights, territory, eff_from, eff_to = scope

        shares = []
        for r in rows:
            d = _to_decimal(r.get("share", ""))
            if d is not None:
                shares.append(d)

        unique_shares = set(shares)
        if len(unique_shares) <= 1:
            continue  # all sources agree

        share_strs = ", ".join(f"{s:.4f} %" for s in sorted(unique_shares))
        findings.append({
            "rule_id": "R3",
            "rule_version": "1.0",
            "finding_type": "conflicting_shares",
            "severity": "error",
            "summary": (
                f"Conflicting share figures for contributor '{cid}' on {work_id} / "
                f"{rights} / {territory}: reported as {share_strs} — "
                f"same scope, irreconcilable values."
            ),
            "uncertainty": (
                "Different source files may use different share conventions "
                "(e.g. publisher share vs. writer share).  Confirm the convention "
                "before concluding the figures are genuinely inconsistent."
            ),
            "next_step": (
                "Obtain the authoritative share schedule from the relevant CMO "
                "or publisher and confirm which figure is correct."
            ),
            "evidence": {
                "work_id": work_id,
                "contributor_id": cid,
                "rights_category": rights,
                "territory": territory,
                "effective_from": eff_from,
                "effective_to": eff_to,
                "reported_shares": [str(s) for s in sorted(unique_shares)],
                "source_rows": rows,
            },
            "matched_conditions": [
                f"contributor_id == '{cid}'",
                f"scope == ({work_id}, {rights}, {territory}, {eff_from}–{eff_to})",
                f"distinct share values: {share_strs}",
            ],
            "supporting_record_ids": [],
            "missing_information": [],
            "conflicting_information": [
                f"Share reported as {s:.4f} % in at least one source" for s in sorted(unique_shares)
            ],
        })
    return findings


# ---------------------------------------------------------------------------
# Rule R4 — unlinked_recording
# ---------------------------------------------------------------------------

def _rule_r4(
    recording_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Fires for each recording that has no verified mapping to a work.

    A mapping is considered verified only when its 'verified' field is
    truthy (see _is_verified).  Title similarity is NOT used as a link.

    Finding type: unlinked_recording
    Severity: warning
    """
    # Build set of recording_ids that have a verified mapping
    verified_rec_ids: set[str] = set()
    for m in mapping_rows:
        if _is_verified(m.get("verified", "")):
            rid = m.get("recording_id", "").strip()
            if rid:
                verified_rec_ids.add(rid)

    findings: list[dict[str, Any]] = []
    for rec in recording_rows:
        rec_id = rec.get("recording_id", "").strip()
        if not rec_id:
            continue
        if rec_id not in verified_rec_ids:
            title = rec.get("title", "?")
            findings.append({
                "rule_id": "R4",
                "rule_version": "1.0",
                "finding_type": "unlinked_recording",
                "severity": "warning",
                "summary": (
                    f"Recording '{rec_id}' ('{title}') has no verified mapping "
                    f"to any work in the supplied records."
                ),
                "uncertainty": (
                    "A mapping may exist in a file that was not uploaded, or the "
                    "recording may be a draft that has not yet been registered."
                ),
                "next_step": (
                    "Supply a mappings file containing a verified link between "
                    f"recording '{rec_id}' and its corresponding work, or confirm "
                    "that no such link should exist."
                ),
                "evidence": {
                    "recording_id": rec_id,
                    "title": title,
                    "recording_row": rec,
                    "verified_mapping_ids": sorted(verified_rec_ids),
                },
                "matched_conditions": [
                    f"recording_id == '{rec_id}' not in verified mapping rows"
                ],
                "supporting_record_ids": [],
                "missing_information": [
                    f"A verified mapping row for recording '{rec_id}'"
                ],
                "conflicting_information": [],
            })
    return findings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_analysis(db: Session, case_id: int) -> dict[str, Any]:
    """
    Run the full analysis pipeline for a case.

    Steps:
      1. Load all uploaded files and their confirmed mappings.
      2. Ingest each file → normalised rows → Record rows in DB.
      3. Run R1–R4 rules.
      4. Persist findings via repository.save_findings().
      5. Log audit event.
      6. Return a summary dict.

    Returns a dict with:
      - finding_count: total findings produced this run
      - findings_by_type: {type: count}
      - record_count: total records ingested this run
    """
    # -- Load files --
    files: list[UploadedFile] = (
        db.query(UploadedFile).filter(UploadedFile.case_id == case_id).all()
    )

    # Bucket files by kind
    by_kind: dict[str, list[tuple[UploadedFile, list[ColumnMapping]]]] = defaultdict(list)
    for uf in files:
        mappings: list[ColumnMapping] = (
            db.query(ColumnMapping)
            .filter(
                ColumnMapping.uploaded_file_id == uf.id,
                ColumnMapping.confirmed == True,  # noqa: E712
            )
            .all()
        )
        by_kind[uf.file_type].append((uf, mappings))

    # -- Ingest rows (now returns NormalisedRow lists) --
    recording_nrows: list[NormalisedRow] = []
    work_nrows: list[NormalisedRow] = []
    ownership_nrows: list[NormalisedRow] = []
    mapping_nrows: list[NormalisedRow] = []

    total_records = 0
    for kind, file_pairs in by_kind.items():
        for uf, mappings in file_pairs:
            if not mappings:
                continue
            nrows = _ingest_file(db, uf, mappings)
            total_records += len(nrows)
            if kind == "recordings":
                recording_nrows.extend(nrows)
            elif kind == "works":
                work_nrows.extend(nrows)
            elif kind == "ownership":
                ownership_nrows.extend(nrows)
            elif kind == "mappings":
                mapping_nrows.extend(nrows)

    db.flush()

    # -- Generate exact-match links (recording ↔ work) --
    links = generate_links(
        db=db,
        case_id=case_id,
        recording_nrows=recording_nrows,
        work_nrows=work_nrows,
        mapping_nrows=mapping_nrows,
    )

    # Build set of recording Record.id values already linked by exact matcher
    already_linked_ids = {lnk.recording_record_id for lnk in links}

    # -- Propose fuzzy candidates for recordings not yet exact-linked --
    fuzzy_candidates = propose_fuzzy_candidates(
        db=db,
        case_id=case_id,
        recording_nrows=recording_nrows,
        work_nrows=work_nrows,
        already_linked_recording_ids=already_linked_ids,
    )

    def _to_json_safe(d: dict) -> dict:
        """Convert Decimal values to str for JSON-safe rule input dicts."""
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}

    # -- Extract plain dicts for rules (Decimal share → str for JSON safety) --
    recording_rows = [_to_json_safe(nr.normalised) for nr in recording_nrows]
    ownership_rows = [_to_json_safe(nr.normalised) for nr in ownership_nrows]
    mapping_rows   = [_to_json_safe(nr.normalised) for nr in mapping_nrows]

    # -- Run rules --
    all_findings: list[dict] = []
    all_findings.extend(_rule_r1(ownership_rows))
    all_findings.extend(_rule_r2(ownership_rows))
    all_findings.extend(_rule_r3(ownership_rows))
    all_findings.extend(_rule_r4(recording_rows, mapping_rows))

    # -- Persist findings --
    saved = save_findings(db, case_id=case_id, findings=all_findings)

    log_audit_event(
        db,
        case_id=case_id,
        event_type="analysis.completed",
        actor=DEMO_USER,
        payload={
            "finding_count": len(saved),
            "record_count": total_records,
            "link_count": len(links),
            "fuzzy_candidate_count": len(fuzzy_candidates),
        },
    )
    db.commit()

    # Summary
    by_type: dict[str, int] = defaultdict(int)
    for fd in all_findings:
        by_type[fd["finding_type"]] += 1

    return {
        "finding_count": len(saved),
        "findings_by_type": dict(by_type),
        "record_count": total_records,
        "finding_ids": [f.id for f in saved],
        "link_count": len(links),
        "verified_link_count": sum(1 for lnk in links if lnk.verified),
        "fuzzy_candidate_count": len(fuzzy_candidates),
    }

