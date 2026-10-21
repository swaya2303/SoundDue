"""
reasoning/rule_runner.py
========================
Runs the four SoundDue reconciliation rules (R1–R4) via MeTTa and returns
structured finding dicts.

SEPARATION OF CONCERNS
-----------------------
* Python builds MeTTa facts (from normalised row dicts) and DERIVED facts
  (scope-gap, share-conflict, unlinked-recording) that require arithmetic or
  set operations MeTTa 0.2.10 cannot perform natively.
* MeTTa DECIDES whether each rule fires by pattern-matching those facts.
  If the match returns atoms → rule fires.  Empty list → rule does not fire.
* Python FORMATS the returned atoms into Finding / RuleTrace / Evidence dicts.
  It does NOT apply any further if/else logic on the data.

EXPERIMENTAL RUNTIME
--------------------
Requires hyperon==0.2.10 in the reasoning/.venv (Python 3.12).
See docs/reasoning-runtime.md.

INJECTION SAFETY
----------------
All user-supplied strings are passed through reasoning.wrapper.quote() before
being embedded in MeTTa facts.  No raw string concatenation.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from reasoning.engine import MettaEngine, get_engine
from reasoning.wrapper import load_facts, quote

# ---------------------------------------------------------------------------
# Paths to rule files (relative to this file's location)
# ---------------------------------------------------------------------------
_RULES_DIR = Path(__file__).parent / "rules"

_RULE_FILES = {
    "R1": _RULES_DIR / "r1_possible_missing_claim.metta",
    "R2": _RULES_DIR / "r2_incomplete_ownership_info.metta",
    "R3": _RULES_DIR / "r3_conflicting_shares.metta",
    "R4": _RULES_DIR / "r4_unlinked_recording.metta",
}

# Rule queries — the expression passed to metta.run("!(<expr>)")
_RULE_QUERIES = {
    "R1": "match &self (unclaimed $w $share $rc $t $ef $et) (r1-fires $w $share $rc $t $ef $et)",
    "R2": "match &self (scope-gap $w $rc $t $ef $et $sum) (r2-fires $w $rc $t $ef $et $sum)",
    "R3": "match &self (share-conflict $w $cid $rc $t $ef $et $s1 $s2) (r3-fires $w $cid $rc $t $ef $et $s1 $s2)",
    "R4": "match &self (unlinked-recording $rec $title) (r4-fires $rec $title)",
}

_UNCLAIMED_LABELS: frozenset[str] = frozenset(
    {"unclaimed", "unregistered", "unknown", "pool"}
)
_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "y"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_unclaimed(status: str) -> bool:
    return str(status).strip().lower() in _UNCLAIMED_LABELS


def _is_verified(val: str) -> bool:
    return str(val).strip().lower() in _TRUE_STRINGS


def _to_decimal(val: Any) -> Decimal | None:
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError):
        return None


def _parse_atom_args(atom_str: str) -> list[str]:
    """
    Parse the argument strings from a MeTTa result atom like:
      (r1-fires "WRK-001" "40.0" "mechanical" "WW" "2020-01-01" "2030-12-31")

    Returns a list of unquoted argument strings.
    Each argument is a MeTTa string literal: "..." — strip the outer quotes.
    """
    # Strip outer parens and leading predicate name
    s = atom_str.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    # Remove predicate name (first token)
    parts = []
    i = 0
    n = len(s)
    # skip predicate name
    while i < n and not s[i].isspace():
        i += 1
    # collect quoted string args
    while i < n:
        if s[i] == '"':
            j = i + 1
            while j < n:
                if s[j] == '\\':
                    j += 2
                    continue
                if s[j] == '"':
                    parts.append(s[i + 1: j].replace('\\"', '"').replace('\\\\', '\\'))
                    i = j + 1
                    break
                j += 1
            else:
                parts.append(s[i + 1:])
                break
        elif not s[i].isspace():
            # bare atom (e.g. a number)
            j = i
            while j < n and not s[j].isspace():
                j += 1
            parts.append(s[i:j])
            i = j
        else:
            i += 1
    return parts


# ---------------------------------------------------------------------------
# Fact builders
# ---------------------------------------------------------------------------

def _build_ownership_facts(
    ownership_rows: list[dict],
    record_ids: list[int | None] | None = None,
) -> tuple[list[str], dict[tuple, list[int]]]:
    """
    Convert normalised ownership dicts to MeTTa facts.

    Returns:
        facts: list of MeTTa fact strings
        scope_record_map: maps (work_id, rc, territory, eff_from, eff_to) →
                          list of DB record IDs in that scope
    """
    facts: list[str] = []
    scope_record_map: dict[tuple, list[int]] = defaultdict(list)

    for i, row in enumerate(ownership_rows):
        wid = row.get("work_id", "")
        cid = row.get("contributor_id", "") or row.get("contributor_name", "")
        cname = row.get("contributor_name", "")
        share = str(row.get("share", "")).strip()
        rc = row.get("rights_category", "unknown")
        terr = row.get("territory", "unknown")
        ef = row.get("effective_from", "unknown")
        et = row.get("effective_to", "unknown")
        sc = row.get("share_convention", "unknown")
        status = str(row.get("status", "")).strip()

        rid = (record_ids[i] if record_ids and i < len(record_ids) else None)
        scope_key = (wid, rc, terr, ef, et)
        if rid is not None:
            scope_record_map[scope_key].append(rid)

        if _is_unclaimed(status):
            facts.append(
                f"(unclaimed {quote(wid)} {quote(share)} {quote(rc)} "
                f"{quote(terr)} {quote(ef)} {quote(et)})"
            )
        else:
            facts.append(
                f"(claim {quote(wid)} {quote(cid)} {quote(cname)} {quote(share)} "
                f"{quote(rc)} {quote(terr)} {quote(ef)} {quote(et)} {quote(sc)})"
            )

    return facts, dict(scope_record_map)


def _build_scope_gap_facts(
    ownership_rows: list[dict],
) -> list[str]:
    """
    Python computes per-scope share sums (MeTTa cannot aggregate).
    Emits (scope-gap ...) facts for scopes where:
      - NO row is unclaimed
      - sum of shares < 99.99

    MeTTa decides R2 fires by matching these facts.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in ownership_rows:
        key = (
            row.get("work_id", ""),
            row.get("rights_category", "unknown"),
            row.get("territory", "unknown"),
            row.get("effective_from", "unknown"),
            row.get("effective_to", "unknown"),
        )
        groups[key].append(row)

    facts: list[str] = []
    for (wid, rc, terr, ef, et), rows in groups.items():
        # Skip if any row in scope is unclaimed (that's R1's domain)
        if any(_is_unclaimed(r.get("status", "")) for r in rows):
            continue
        total = Decimal("0")
        for r in rows:
            d = _to_decimal(r.get("share", ""))
            if d is not None:
                total += d
        if total < Decimal("99.99"):
            facts.append(
                f"(scope-gap {quote(wid)} {quote(rc)} {quote(terr)} "
                f"{quote(ef)} {quote(et)} {quote(str(total))})"
            )
    return facts


def _build_share_conflict_facts(
    ownership_rows: list[dict],
) -> list[str]:
    """
    Python groups rows by (work_id, contributor_id, rc, territory, eff_from, eff_to).
    Emits (share-conflict ...) facts when the same contributor+scope has
    two or more DIFFERENT Decimal share values across the group.

    MeTTa decides R3 fires by matching these facts.
    Incompatible scopes (different territory/rc/period) produce different
    group keys → no conflict fact → R3 does NOT fire. ✓
    """
    groups: dict[tuple, list[Decimal]] = defaultdict(list)
    for row in ownership_rows:
        cid = row.get("contributor_id", "") or row.get("contributor_name", "")
        key = (
            row.get("work_id", ""),
            cid,
            row.get("rights_category", "unknown"),
            row.get("territory", "unknown"),
            row.get("effective_from", "unknown"),
            row.get("effective_to", "unknown"),
        )
        d = _to_decimal(row.get("share", ""))
        if d is not None:
            groups[key].append(d)

    facts: list[str] = []
    for (wid, cid, rc, terr, ef, et), shares in groups.items():
        unique = sorted(set(shares))
        if len(unique) < 2:
            continue  # all sources agree
        # Emit one fact per conflicting pair (using min/max for determinism)
        s1, s2 = str(unique[0]), str(unique[-1])
        facts.append(
            f"(share-conflict {quote(wid)} {quote(cid)} {quote(rc)} {quote(terr)} "
            f"{quote(ef)} {quote(et)} {quote(s1)} {quote(s2)})"
        )
    return facts


def _build_recording_and_unlinked_facts(
    recording_rows: list[dict],
    mapping_rows: list[dict],
    record_ids: list[int | None] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """
    Emits (recording ...) and (unlinked-recording ...) facts.

    unlinked-recording is emitted for recordings that have NO verified mapping.
    Title similarity is NEVER used.

    Returns:
        facts: list of MeTTa fact strings
        rec_id_map: recording_id → DB record ID
    """
    verified_rec_ids: set[str] = set()
    for m in mapping_rows:
        if _is_verified(m.get("verified", "")):
            rid = m.get("recording_id", "").strip()
            if rid:
                verified_rec_ids.add(rid)

    facts: list[str] = []
    rec_id_map: dict[str, int] = {}

    for i, rec in enumerate(recording_rows):
        rec_id = rec.get("recording_id", "").strip()
        title = rec.get("title", "")
        if not rec_id:
            continue
        db_id = record_ids[i] if record_ids and i < len(record_ids) else None
        if db_id is not None:
            rec_id_map[rec_id] = db_id
        facts.append(f"(recording {quote(rec_id)} {quote(title)})")
        if rec_id not in verified_rec_ids:
            facts.append(f"(unlinked-recording {quote(rec_id)} {quote(title)})")

    return facts, rec_id_map


def _build_mapping_facts(mapping_rows: list[dict]) -> list[str]:
    """Emit (verified-mapping ...) facts for verified mapping rows."""
    facts: list[str] = []
    for m in mapping_rows:
        if _is_verified(m.get("verified", "")):
            rec_id = m.get("recording_id", "").strip()
            wid = m.get("work_id", "").strip()
            src = m.get("source_label", "")
            if rec_id and wid:
                facts.append(
                    f"(verified-mapping {quote(rec_id)} {quote(wid)} {quote(src)})"
                )
    return facts


# ---------------------------------------------------------------------------
# Finding formatters  (Python formats, never decides)
# ---------------------------------------------------------------------------

def _format_r1(atom_str: str, scope_record_map: dict) -> dict[str, Any]:
    """Format one R1 result atom into a finding dict."""
    args = _parse_atom_args(atom_str)
    wid  = args[0] if len(args) > 0 else "?"
    share = args[1] if len(args) > 1 else "?"
    rc   = args[2] if len(args) > 2 else "?"
    terr = args[3] if len(args) > 3 else "?"
    ef   = args[4] if len(args) > 4 else "?"
    et   = args[5] if len(args) > 5 else "?"
    scope_key = (wid, rc, terr, ef, et)
    return {
        "rule_id": "R1",
        "rule_version": "1.0",
        "finding_type": "possible_missing_claim",
        "severity": "warning",
        "summary": (
            f"Explicit 'unclaimed' label for {wid} / {rc} / {terr}: "
            f"{share} % marked unclaimed — a named claimant may exist."
        ),
        "uncertainty": (
            "The source explicitly reserves this share as unclaimed. "
            "A rights holder may exist but was not provided in this upload."
        ),
        "next_step": (
            "Verify the ownership agreement and registration status "
            "before requesting a correction."
        ),
        "evidence": {
            "work_id": wid, "share": share, "rights_category": rc,
            "territory": terr, "effective_from": ef, "effective_to": et,
        },
        "matched_conditions": [
            f"status in unclaimed labels",
            f"share = {share} %",
            f"work_id = {wid}, scope = {rc} / {terr} / {ef}–{et}",
        ],
        "supporting_record_ids": scope_record_map.get(scope_key, []),
        "missing_information": ["Identity of the rights holder for this share"],
        "conflicting_information": [],
    }


def _format_r2(atom_str: str, scope_record_map: dict) -> dict[str, Any]:
    args = _parse_atom_args(atom_str)
    wid  = args[0] if len(args) > 0 else "?"
    rc   = args[1] if len(args) > 1 else "?"
    terr = args[2] if len(args) > 2 else "?"
    ef   = args[3] if len(args) > 3 else "?"
    et   = args[4] if len(args) > 4 else "?"
    s    = args[5] if len(args) > 5 else "?"
    try:
        total = Decimal(s)
        gap = Decimal("100") - total
        gap_str = f"{gap:.4f}"
        total_str = f"{total:.4f}"
    except InvalidOperation:
        gap_str = "?"
        total_str = s
    scope_key = (wid, rc, terr, ef, et)
    return {
        "rule_id": "R2",
        "rule_version": "1.0",
        "finding_type": "incomplete_ownership_info",
        "severity": "warning",
        "summary": (
            f"Incomplete or inconsistent ownership information. "
            f"Additional evidence is required. "
            f"Shares for {wid} / {rc} / {terr} sum to {total_str} %, "
            f"leaving {gap_str} % missing from the supplied records."
        ),
        "uncertainty": (
            "The gap may reflect omitted rows rather than a genuine gap in "
            "registered ownership. No 'unclaimed' label was present to indicate "
            "the source was aware of the missing share."
        ),
        "next_step": (
            "Supply complete ownership schedules for this work, territory, "
            "and rights category covering the relevant period."
        ),
        "evidence": {
            "work_id": wid, "rights_category": rc, "territory": terr,
            "effective_from": ef, "effective_to": et,
            "total_share": total_str, "gap": gap_str,
        },
        "matched_conditions": [
            f"sum(share) = {total_str} < 100",
            "no unclaimed row in scope",
        ],
        "supporting_record_ids": scope_record_map.get(scope_key, []),
        "missing_information": [
            f"{gap_str} % of shares missing from the supplied records"
        ],
        "conflicting_information": [],
    }


def _format_r3(atom_str: str, scope_record_map: dict) -> dict[str, Any]:
    args = _parse_atom_args(atom_str)
    wid  = args[0] if len(args) > 0 else "?"
    cid  = args[1] if len(args) > 1 else "?"
    rc   = args[2] if len(args) > 2 else "?"
    terr = args[3] if len(args) > 3 else "?"
    ef   = args[4] if len(args) > 4 else "?"
    et   = args[5] if len(args) > 5 else "?"
    s1   = args[6] if len(args) > 6 else "?"
    s2   = args[7] if len(args) > 7 else "?"
    scope_key = (wid, rc, terr, ef, et)
    return {
        "rule_id": "R3",
        "rule_version": "1.0",
        "finding_type": "conflicting_shares",
        "severity": "error",
        "summary": (
            f"Conflicting share figures for contributor '{cid}' on {wid} / "
            f"{rc} / {terr}: reported as {s1} % and {s2} % — "
            f"same scope, irreconcilable figures."
        ),
        "uncertainty": (
            "Different source files may use different share conventions "
            "(e.g. publisher share vs. writer share). Confirm the convention "
            "before concluding the figures are genuinely inconsistent."
        ),
        "next_step": (
            "Obtain the authoritative share schedule from the relevant CMO "
            "or publisher and confirm which figure is correct."
        ),
        "evidence": {
            "work_id": wid, "contributor_id": cid,
            "rights_category": rc, "territory": terr,
            "effective_from": ef, "effective_to": et,
            "reported_shares": sorted([s1, s2]),
        },
        "matched_conditions": [
            f"contributor_id = {cid}",
            f"scope = ({wid} / {rc} / {terr} / {ef}–{et})",
            f"distinct share values: {s1} %, {s2} %",
        ],
        "supporting_record_ids": scope_record_map.get(scope_key, []),
        "missing_information": [],
        "conflicting_information": [
            f"Share {s1} % in one source",
            f"Share {s2} % in another source",
        ],
    }


def _format_r4(atom_str: str, rec_id_map: dict) -> dict[str, Any]:
    args = _parse_atom_args(atom_str)
    rec_id = args[0] if len(args) > 0 else "?"
    title  = args[1] if len(args) > 1 else "?"
    db_id = rec_id_map.get(rec_id)
    return {
        "rule_id": "R4",
        "rule_version": "1.0",
        "finding_type": "unlinked_recording",
        "severity": "warning",
        "summary": (
            f"Recording '{rec_id}' ('{title}') has no verified mapping "
            f"to any work in the supplied records. "
            f"Title similarity to any work is insufficient."
        ),
        "uncertainty": (
            "A mapping may exist in a file that was not uploaded, or the "
            "recording may be a draft that has not yet been registered."
        ),
        "next_step": (
            f"Supply a mappings file containing a verified link between "
            f"recording '{rec_id}' and its corresponding work, or confirm "
            "that no such link should exist."
        ),
        "evidence": {"recording_id": rec_id, "title": title},
        "matched_conditions": [
            f"recording_id = {rec_id} not in verified mapping rows"
        ],
        "supporting_record_ids": [db_id] if db_id is not None else [],
        "missing_information": [f"A verified mapping row for recording '{rec_id}'"],
        "conflicting_information": [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_rules(
    ownership_rows: list[dict],
    recording_rows: list[dict],
    mapping_rows: list[dict],
    ownership_record_ids: list[int | None] | None = None,
    recording_record_ids: list[int | None] | None = None,
    engine: MettaEngine | None = None,
) -> list[dict[str, Any]]:
    """
    Run rules R1–R4 via MeTTa and return a list of finding dicts.

    Each call uses a fresh engine (or the provided one).
    Python builds facts and derived facts; MeTTa decides whether each rule fires.

    Parameters
    ----------
    ownership_rows : list[dict]
        Normalised ownership dicts (canonical field names, str/Decimal values).
    recording_rows : list[dict]
        Normalised recording dicts.
    mapping_rows : list[dict]
        Normalised mapping dicts.
    ownership_record_ids : list[int | None], optional
        DB record IDs parallel to ownership_rows (for RuleTrace.supporting_record_ids).
    recording_record_ids : list[int | None], optional
        DB record IDs parallel to recording_rows.
    engine : MettaEngine, optional
        Existing engine to use.  If None, a fresh InProcessEngine is created.

    Returns
    -------
    list[dict]
        Finding dicts compatible with repository.save_findings().
    """
    eng = engine or get_engine()

    # -- Build all facts --
    ownership_facts, scope_record_map = _build_ownership_facts(
        ownership_rows, ownership_record_ids
    )
    mapping_facts = _build_mapping_facts(mapping_rows)
    scope_gap_facts = _build_scope_gap_facts(ownership_rows)
    conflict_facts = _build_share_conflict_facts(ownership_rows)
    recording_facts, rec_id_map = _build_recording_and_unlinked_facts(
        recording_rows, mapping_rows, recording_record_ids
    )

    all_facts = (
        ownership_facts
        + mapping_facts
        + scope_gap_facts
        + conflict_facts
        + recording_facts
    )

    program = "\n".join(all_facts)

    findings: list[dict[str, Any]] = []

    # -- R1: possible_missing_claim --
    eng.reset()
    eng.load_facts(all_facts)
    for atom in eng.query(_RULE_QUERIES["R1"]):
        findings.append(_format_r1(atom, scope_record_map))

    # -- R2: incomplete_ownership_info --
    eng.reset()
    eng.load_facts(all_facts)
    for atom in eng.query(_RULE_QUERIES["R2"]):
        findings.append(_format_r2(atom, scope_record_map))

    # -- R3: conflicting_shares --
    eng.reset()
    eng.load_facts(all_facts)
    for atom in eng.query(_RULE_QUERIES["R3"]):
        findings.append(_format_r3(atom, scope_record_map))

    # -- R4: unlinked_recording --
    eng.reset()
    eng.load_facts(all_facts)
    for atom in eng.query(_RULE_QUERIES["R4"]):
        findings.append(_format_r4(atom, rec_id_map))

    eng.reset()
    return findings
