"""
reasoning/facts.py
==================
Convert SoundDue DB records for a case into MeTTa fact strings.

All user-supplied text is passed through ``reasoning.wrapper.quote()`` before
being embedded in MeTTa source.  This prevents any field value -- however
hostile -- from being interpreted as a MeTTa symbol, directive, or expression.

Facts produced
--------------

``(verified-mapping <recording_id> <work_id> <source_label>)``
    One per accepted-or-verified mapping Record.
    A mapping is "verified" when its normalised_json["verified"] is truthy.

``(claim <work_id> <contributor> <share_str> <rights_category>
         <territory> <effective_from> <effective_to> <share_convention>)``
    One per ownership Record.
    ``share_str`` is the exact decimal string from the source (e.g. "60.0000").
    Scope fields that are missing default to the sentinel string "unknown"
    (never empty string, never guessed).

``(unclaimed <work_id> <share_str> <rights_category>
             <territory> <effective_from> <effective_to>)``
    One per ownership Record explicitly labelled unclaimed (status in
    {"unclaimed", "unregistered", "unknown", "pool"}).

``(scope-compatible <work_id_a> <work_id_b>
                    <rights_category> <territory>
                    <effective_from> <effective_to>)``
    Computed in Python between all pairs of ownership records that share the
    same work_id and are in a compatible scope.  See _scopes_compatible() for
    the documented logic.  Self-pairs and duplicates are omitted.

Scope-compatible logic
----------------------
Two ownership records A and B are scope-compatible when ALL of the following
hold:

1. rights_category: A == B, OR at least one is "unknown".
2. territory:       A == B, OR at least one is "unknown".
3. Period overlap:  A.effective_from <= B.effective_to
                    AND B.effective_from <= A.effective_to.
                    If either date is "unknown", the periods are assumed to
                    be compatible (we cannot rule out overlap).
4. share_convention: A == B, OR at least one is "unknown".

Only compatible pairs are emitted (we do NOT generate negatives).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from reasoning.wrapper import quote

# Unclaimed labels (matches analyzer._UNCLAIMED_LABELS)
_UNCLAIMED_LABELS: frozenset[str] = frozenset(
    {"unclaimed", "unregistered", "unknown", "pool"}
)

_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Scope-compatible helper
# ---------------------------------------------------------------------------

def _periods_overlap(from_a: str, to_a: str, from_b: str, to_b: str) -> bool:
    """
    Return True if [from_a, to_a] and [from_b, to_b] overlap.

    "unknown" dates are treated as maximally inclusive -- we cannot rule
    out overlap, so we conservatively assume compatible.

    Date strings are compared lexicographically (ISO 8601 format ensures
    this is correct for year/month/day).
    """
    if _UNKNOWN in (from_a, to_a, from_b, to_b):
        return True
    try:
        return from_a <= to_b and from_b <= to_a
    except TypeError:
        return True  # defensive


def _scopes_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """
    Return True when ownership records *a* and *b* are scope-compatible.

    See module docstring for the four conditions.
    """
    def _compat(ka: str, kb: str) -> bool:
        va, vb = a.get(ka, _UNKNOWN), b.get(kb, _UNKNOWN)
        return va == vb or va == _UNKNOWN or vb == _UNKNOWN

    if not _compat("rights_category", "rights_category"):
        return False
    if not _compat("territory", "territory"):
        return False
    if not _periods_overlap(
        a.get("effective_from", _UNKNOWN), a.get("effective_to", _UNKNOWN),
        b.get("effective_from", _UNKNOWN), b.get("effective_to", _UNKNOWN),
    ):
        return False
    if not _compat("share_convention", "share_convention"):
        return False
    return True


# ---------------------------------------------------------------------------
# Fact constructors
# ---------------------------------------------------------------------------

def _make_verified_mapping(recording_id: str, work_id: str, source_label: str) -> str:
    return (
        f"(verified-mapping "
        f"{quote(recording_id)} "
        f"{quote(work_id)} "
        f"{quote(source_label)})"
    )


def _make_claim(
    work_id: str,
    contributor: str,
    share_str: str,
    rights_category: str,
    territory: str,
    effective_from: str,
    effective_to: str,
    share_convention: str,
) -> str:
    return (
        f"(claim "
        f"{quote(work_id)} "
        f"{quote(contributor)} "
        f"{quote(share_str)} "
        f"{quote(rights_category)} "
        f"{quote(territory)} "
        f"{quote(effective_from)} "
        f"{quote(effective_to)} "
        f"{quote(share_convention)})"
    )


def _make_unclaimed(
    work_id: str,
    share_str: str,
    rights_category: str,
    territory: str,
    effective_from: str,
    effective_to: str,
) -> str:
    return (
        f"(unclaimed "
        f"{quote(work_id)} "
        f"{quote(share_str)} "
        f"{quote(rights_category)} "
        f"{quote(territory)} "
        f"{quote(effective_from)} "
        f"{quote(effective_to)})"
    )


def _make_scope_compatible(
    work_id_a: str,
    work_id_b: str,
    rights_category: str,
    territory: str,
    effective_from: str,
    effective_to: str,
) -> str:
    return (
        f"(scope-compatible "
        f"{quote(work_id_a)} "
        f"{quote(work_id_b)} "
        f"{quote(rights_category)} "
        f"{quote(territory)} "
        f"{quote(effective_from)} "
        f"{quote(effective_to)})"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def records_to_facts(case_id: int, db: "Session") -> list[str]:
    """
    Query DB records for *case_id* and return a list of MeTTa fact strings.

    All user-supplied text is escaped via ``quote()`` -- safe to pass
    directly to MeTTa without risk of injection.

    Parameters
    ----------
    case_id : int
    db : sqlalchemy.orm.Session

    Returns
    -------
    list[str]
        Each element is a complete MeTTa expression, e.g.::

            '(verified-mapping "REC-001" "WRK-001" "LabelX")'
    """
    # Import inside function to avoid circular imports when reasoning/
    # is used standalone (without the full backend installed).
    from app.models import Record

    records = (
        db.query(Record)
        .filter(Record.case_id == case_id)
        .order_by(Record.id)
        .all()
    )

    facts: list[str] = []
    ownership_records: list[dict[str, Any]] = []  # for scope-compatible computation

    for rec in records:
        n: dict[str, Any] = rec.normalised_json or {}
        rt: str = rec.record_type or ""

        # --- Mapping records ---
        if rt == "mapping":
            rec_id = n.get("recording_id", "")
            wrk_id = n.get("work_id", "")
            src = n.get("source_label", "")
            verified_raw = n.get("verified", "")
            # Only emit verified-mapping when explicitly verified
            verified = str(verified_raw).strip().lower() in {"true", "1", "yes", "y"}
            if verified and rec_id and wrk_id:
                facts.append(_make_verified_mapping(rec_id, wrk_id, src))

        # --- Ownership / claim records ---
        elif rt == "ownership":
            wrk_id = n.get("work_id", "")
            contributor = (
                n.get("contributor_name", "")
                or n.get("contributor_id", "")
            )
            share_raw = n.get("share", "")
            share_str = str(share_raw).strip() if share_raw is not None else ""
            rights_cat = n.get("rights_category", _UNKNOWN) or _UNKNOWN
            territory = n.get("territory", _UNKNOWN) or _UNKNOWN
            eff_from = n.get("effective_from", _UNKNOWN) or _UNKNOWN
            eff_to = n.get("effective_to", _UNKNOWN) or _UNKNOWN
            share_conv = n.get("share_convention", _UNKNOWN) or _UNKNOWN
            status = str(n.get("status", "")).strip().lower()

            if wrk_id:
                if status in _UNCLAIMED_LABELS:
                    facts.append(_make_unclaimed(
                        wrk_id, share_str, rights_cat,
                        territory, eff_from, eff_to,
                    ))
                else:
                    facts.append(_make_claim(
                        wrk_id, contributor, share_str,
                        rights_cat, territory, eff_from, eff_to, share_conv,
                    ))

                ownership_records.append({
                    "work_id": wrk_id,
                    "rights_category": rights_cat,
                    "territory": territory,
                    "effective_from": eff_from,
                    "effective_to": eff_to,
                    "share_convention": share_conv,
                })

    # --- Scope-compatible (computed in Python, not inferred by MeTTa) ---
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(ownership_records):
        for b in ownership_records[i + 1 :]:
            if a["work_id"] != b["work_id"]:
                continue
            key = (a["work_id"], b["work_id"])
            if key in seen:
                continue
            if _scopes_compatible(a, b):
                facts.append(_make_scope_compatible(
                    a["work_id"], b["work_id"],
                    a["rights_category"], a["territory"],
                    a["effective_from"], a["effective_to"],
                ))
                seen.add(key)

    return facts


# ---------------------------------------------------------------------------
# Convenience: build a standalone list of facts from raw dicts (for tests)
# ---------------------------------------------------------------------------

def dicts_to_facts(
    mappings: list[dict] | None = None,
    claims: list[dict] | None = None,
) -> list[str]:
    """
    Build MeTTa fact strings from plain Python dicts (no DB required).

    Useful for unit tests and ``make check-metta``.

    Each mapping dict: {recording_id, work_id, source_label, verified}
    Each claim dict:   {work_id, contributor, share, rights_category,
                        territory, effective_from, effective_to,
                        share_convention, status}
    """
    facts: list[str] = []
    ownership_records: list[dict] = []

    for m in mappings or []:
        if str(m.get("verified", "")).strip().lower() in {"true", "1", "yes", "y"}:
            facts.append(_make_verified_mapping(
                m.get("recording_id", ""),
                m.get("work_id", ""),
                m.get("source_label", ""),
            ))

    for c in claims or []:
        wrk_id = c.get("work_id", "")
        status = str(c.get("status", "")).strip().lower()
        share_str = str(c.get("share", "")).strip()
        rights_cat = c.get("rights_category", _UNKNOWN) or _UNKNOWN
        territory = c.get("territory", _UNKNOWN) or _UNKNOWN
        eff_from = c.get("effective_from", _UNKNOWN) or _UNKNOWN
        eff_to = c.get("effective_to", _UNKNOWN) or _UNKNOWN
        share_conv = c.get("share_convention", _UNKNOWN) or _UNKNOWN

        if status in _UNCLAIMED_LABELS:
            facts.append(_make_unclaimed(wrk_id, share_str, rights_cat, territory, eff_from, eff_to))
        else:
            facts.append(_make_claim(
                wrk_id, c.get("contributor", ""), share_str,
                rights_cat, territory, eff_from, eff_to, share_conv,
            ))
        ownership_records.append({
            "work_id": wrk_id,
            "rights_category": rights_cat,
            "territory": territory,
            "effective_from": eff_from,
            "effective_to": eff_to,
            "share_convention": share_conv,
        })

    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(ownership_records):
        for b in ownership_records[i + 1:]:
            if a["work_id"] != b["work_id"]:
                continue
            key = (a["work_id"], b["work_id"])
            if key in seen:
                continue
            if _scopes_compatible(a, b):
                facts.append(_make_scope_compatible(
                    a["work_id"], b["work_id"],
                    a["rights_category"], a["territory"],
                    a["effective_from"], a["effective_to"],
                ))
                seen.add(key)

    return facts
