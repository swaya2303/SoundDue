"""
data/synthetic/generate.py
==========================
Deterministic generator for SoundDue synthetic test scenarios.

ALL data is hardcoded as Python constants — no randomness, no runtime state,
no timestamps. Running this script twice always produces bit-for-bit identical
files.

Usage:
    python data/synthetic/generate.py

Output is written to data/synthetic/<scenario_name>/
"""

# ============================================================
# FICTIONAL DEMO DATA — for testing and demonstration only.
# No real persons, ISRCs, ISWCs, or organisations are depicted.
# ============================================================

import csv
import json
import hashlib
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Low-level writers (always utf-8, unix newlines for determinism)
# ---------------------------------------------------------------------------
def write_csv(path: Path, headers: list, rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(headers)
        for row in rows:
            w.writerow(row)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2, ensure_ascii=False))
        fh.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# Column-header styles
# Exercises the synonym mapping documented in docs/input-schema.md
# ---------------------------------------------------------------------------

# Style A — used in scenarios 1, 3, 5 and ownership_source_a in 4
OWNERSHIP_HEADERS_A = [
    "Work Code",        # -> work_id
    "Writer Code",      # -> contributor_id
    "Songwriter",       # -> contributor_name
    "Songwriter %",     # -> share
    "Convention",       # -> share_convention
    "Rights Type",      # -> rights_category
    "Territory",        # -> territory
    "Valid From",       # -> effective_from
    "Valid To",         # -> effective_to
    "Claim Status",     # -> status
]

# Style B — used in scenarios 2, 6 and ownership_source_b in 4, 5
OWNERSHIP_HEADERS_B = [
    "Composition ID",   # -> work_id
    "Contributor ID",   # -> contributor_id
    "Rights Holder",    # -> contributor_name
    "Share %",          # -> share
    "Share Type",       # -> share_convention
    "Rights Category",  # -> rights_category
    "Market",           # -> territory
    "Period Start",     # -> effective_from
    "Period End",       # -> effective_to
    "Status",           # -> status
]

# Recording headers — two styles
RECORDING_HEADERS_A = [
    "Track Code",       # -> recording_id
    "Track Title",      # -> title
    "Main Artist",      # -> performer
    "Version",          # -> version
    "Secs",             # -> duration_seconds
    "ISRC Code",        # -> isrc
]
RECORDING_HEADERS_B = [
    "recording_id",
    "title",
    "performer",
    "version",
    "duration_seconds",
    "isrc",
]

WORK_HEADERS = ["work_id", "title", "writers", "iswc"]
MAPPING_HEADERS = ["recording_id", "work_id", "source_label", "verified"]


# ---------------------------------------------------------------------------
# Helper: ownership row builders (returns list in header order)
# ---------------------------------------------------------------------------
def own_a(work_id, contrib_id, name, share, convention, category, territory,
          eff_from, eff_to, status):
    return [work_id, contrib_id, name, share, convention, category,
            territory, eff_from, eff_to, status]


def own_b(work_id, contrib_id, name, share, share_type, category, market,
          p_start, p_end, status):
    return [work_id, contrib_id, name, share, share_type, category,
            market, p_start, p_end, status]


# ===========================================================================
# SCENARIO 1 — midnight_train_unclaimed
# ===========================================================================
S1 = "scenario_01_midnight_train_unclaimed"

S1_RECORDINGS = [
    ["REC-S1-001", "Midnight Train", "Artist Alpha", "Original", "214", ""],
]
S1_WORKS = [
    ["WRK-S1-001", "Midnight Train", "Writer A, Writer B", ""],
]
S1_MAPPINGS = [
    ["REC-S1-001", "WRK-S1-001", "DemoRegistry", "true"],
]
# Source explicitly marks 40 % as "unclaimed" — triggers R1
S1_OWNERSHIP = [
    own_a("WRK-S1-001", "WRT-A-S1", "Writer A",
          "60.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "claimed"),
    own_a("WRK-S1-001", "POOL-S1", "Unclaimed Pool",
          "40.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "unclaimed"),   # EXPLICIT unclaimed
]
S1_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S1,
    "description": (
        "Writer A holds 60 %. The registration EXPLICITLY marks the remaining "
        "40 % as 'unclaimed'. Rule R1 must flag this as a possible missing claim. "
        "Rule R2 (incomplete_ownership_info) must NOT fire because the gap is "
        "declared, not silent."
    ),
    "must_appear": [
        {
            "type": "possible_missing_claim",
            "rule_id": "R1",
            "description": (
                "Source explicitly marks 40.0000 % as 'unclaimed' for "
                "WRK-S1-001 / mechanical / WW — a named claimant may exist."
            ),
        }
    ],
    "must_not_flag": ["incomplete_ownership_info"],
}
S1_README = """\
# FICTIONAL DEMO DATA — Scenario 01: midnight_train_unclaimed

Writers A (60 %) and B (40 %) co-wrote "Midnight Train".
The rights registration supplies Writer A's 60 % claim and **explicitly** marks
the remaining 40 % as "unclaimed", indicating a known gap with a named pool entry.
SoundDue must raise a `possible_missing_claim` finding (R1) for the unclaimed
portion and must **not** treat this as a silent omission.
"""


# ===========================================================================
# SCENARIO 2 — silent_omission
# ===========================================================================
S2 = "scenario_02_silent_omission"

S2_RECORDINGS = [
    ["REC-S2-001", "Midnight Train", "Artist Alpha", "Original", "214", ""],
]
S2_WORKS = [
    ["WRK-S2-001", "Midnight Train", "Writer A, Writer B", ""],
]
S2_MAPPINGS = [
    ["REC-S2-001", "WRK-S2-001", "DemoRegistry", "true"],
]
# B is simply absent — no "unclaimed" marker — triggers R2
# Uses OWNERSHIP_HEADERS_B to exercise synonym mapping
S2_OWNERSHIP = [
    own_b("WRK-S2-001", "WRT-A-S2", "Writer A",
          "60.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "claimed"),
    # Writer B row is intentionally absent; no unclaimed marker
]
S2_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S2,
    "description": (
        "Writer A holds 60 %. Writer B's 40 % share is simply absent from the "
        "supplied records — no 'unclaimed' label exists. Rule R2 must flag "
        "incomplete_ownership_info. Rule R1 (possible_missing_claim) must NOT "
        "fire because the source never explicitly marks any share as unclaimed."
    ),
    "must_appear": [
        {
            "type": "incomplete_ownership_info",
            "rule_id": "R2",
            "description": (
                "Shares for WRK-S2-001 / mechanical / WW sum to 60.0000 %, "
                "leaving 40 % missing from the supplied records."
            ),
        }
    ],
    "must_not_flag": ["possible_missing_claim"],
}
S2_README = """\
# FICTIONAL DEMO DATA — Scenario 02: silent_omission

Writers A and B co-wrote "Midnight Train". Only Writer A's 60 % claim appears
in the supplied ownership file; Writer B's share is simply absent with no label.
SoundDue must raise `incomplete_ownership_info` (R2) because the gap is a silent
omission, not an explicit declaration, and must **not** raise a missing-claim
finding (R1) since no source marks the share as "unclaimed".
"""


# ===========================================================================
# SCENARIO 3 — same_title_different_writers
# ===========================================================================
S3 = "scenario_03_same_title_different_writers"

# Uses recording Style A headers
S3_RECORDINGS = [
    ["REC-S3-001", "Golden Hour", "Artist X", "Studio", "195", ""],
    ["REC-S3-002", "Golden Hour", "Artist Y", "Studio", "208", ""],
]
S3_WORKS = [
    ["WRK-S3-001", "Golden Hour", "Writer X", ""],
    ["WRK-S3-002", "Golden Hour", "Writer Y", ""],
]
S3_MAPPINGS = [
    ["REC-S3-001", "WRK-S3-001", "LabelX", "true"],
    ["REC-S3-002", "WRK-S3-002", "LabelY", "true"],
]
# Both works have complete 100 % ownership — no gaps
S3_OWNERSHIP = [
    own_a("WRK-S3-001", "WRT-X-S3", "Writer X",
          "100.0000", "publisher-share", "mechanical", "WW",
          "2021-01-01", "2031-12-31", "claimed"),
    own_a("WRK-S3-002", "WRT-Y-S3", "Writer Y",
          "100.0000", "publisher-share", "mechanical", "WW",
          "2021-01-01", "2031-12-31", "claimed"),
]
S3_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S3,
    "description": (
        "Two distinct works share the title 'Golden Hour' but have different "
        "writers and IDs. SoundDue must never merge them. No ownership gaps exist. "
        "No findings expected."
    ),
    "must_appear": [],
    "must_not_flag": [
        "works_merged",
        "title_match_link",
        "incomplete_ownership_info",
        "conflicting_shares",
    ],
}
S3_README = """\
# FICTIONAL DEMO DATA — Scenario 03: same_title_different_writers

Two entirely different musical works both happen to be titled "Golden Hour".
Writer X authored one; Writer Y authored the other — they are separate compositions
with distinct IDs, separate recordings, and separate verified mappings.
SoundDue must never merge them on the basis of title alone, and no ownership or
match findings should be raised.
"""


# ===========================================================================
# SCENARIO 4 — conflicting_shares
# ===========================================================================
S4 = "scenario_04_conflicting_shares"

# Uses recording Style B headers
S4_RECORDINGS = [
    ["REC-S4-001", "River Crossing", "Artist Delta", "Album", "241", ""],
]
S4_WORKS = [
    ["WRK-S4-001", "River Crossing", "Writer A, Writer B", ""],
]
S4_MAPPINGS = [
    ["REC-S4-001", "WRK-S4-001", "SourceAlpha", "true"],
]
# Source A says 60/40; Source B says 50/50 — same scope, different figures
S4_OWNERSHIP_A = [   # Style A headers
    own_a("WRK-S4-001", "WRT-A-S4", "Writer A",
          "60.0000", "publisher-share", "mechanical", "WW",
          "2019-01-01", "2029-12-31", "claimed"),
    own_a("WRK-S4-001", "WRT-B-S4", "Writer B",
          "40.0000", "publisher-share", "mechanical", "WW",
          "2019-01-01", "2029-12-31", "claimed"),
]
S4_OWNERSHIP_B = [   # Style B headers — different column names, same scope
    own_b("WRK-S4-001", "WRT-A-S4", "Writer A",
          "50.0000", "publisher-share", "mechanical", "WW",
          "2019-01-01", "2029-12-31", "claimed"),
    own_b("WRK-S4-001", "WRT-B-S4", "Writer B",
          "50.0000", "publisher-share", "mechanical", "WW",
          "2019-01-01", "2029-12-31", "claimed"),
]
S4_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S4,
    "description": (
        "Two sources supply ownership data for WRK-S4-001 under the same scope "
        "(mechanical / WW / 2019-2029). Source A reports 60/40; Source B reports "
        "50/50. SoundDue must flag conflicting_shares (R3)."
    ),
    "must_appear": [
        {
            "type": "conflicting_shares",
            "rule_id": "R3",
            "description": (
                "Writer A's share for WRK-S4-001 / mechanical / WW is reported as "
                "60.0000 % by ownership_source_a.csv and 50.0000 % by "
                "ownership_source_b.csv — same scope, irreconcilable figures."
            ),
        }
    ],
    "must_not_flag": ["incomplete_ownership_info", "incompatible_comparison"],
}
S4_README = """\
# FICTIONAL DEMO DATA — Scenario 04: conflicting_shares

Two independent ownership sources report different splits for the same work
under an identical scope (mechanical rights, worldwide, 2019–2029).
Source A says Writer A holds 60 % and Writer B 40 %; Source B says each holds
50 %. SoundDue must raise a `conflicting_shares` finding (R3) because the figures
are irreconcilable within a single compatible scope.
"""


# ===========================================================================
# SCENARIO 5 — incompatible_scopes
# ===========================================================================
S5 = "scenario_05_incompatible_scopes"

S5_RECORDINGS = [
    ["REC-S5-001", "Desert Bloom", "Artist Epsilon", "Original", "187", ""],
]
S5_WORKS = [
    ["WRK-S5-001", "Desert Bloom", "Writer C, Writer D", ""],
]
S5_MAPPINGS = [
    ["REC-S5-001", "WRK-S5-001", "GlobalCMO", "true"],
]
# Source A: WW / all-rights / 2020-2025   →  Style A headers
S5_OWNERSHIP_A = [
    own_a("WRK-S5-001", "WRT-C-S5", "Writer C",
          "70.0000", "publisher-share", "all-rights", "WW",
          "2020-01-01", "2025-12-31", "claimed"),
    own_a("WRK-S5-001", "WRT-D-S5", "Writer D",
          "30.0000", "publisher-share", "all-rights", "WW",
          "2020-01-01", "2025-12-31", "claimed"),
]
# Source B: US / mechanical / 2019-2023   →  Style B headers
S5_OWNERSHIP_B = [
    own_b("WRK-S5-001", "WRT-C-S5", "Writer C",
          "60.0000", "publisher-share", "mechanical", "US",
          "2019-01-01", "2023-12-31", "claimed"),
    own_b("WRK-S5-001", "WRT-D-S5", "Writer D",
          "40.0000", "publisher-share", "mechanical", "US",
          "2019-01-01", "2023-12-31", "claimed"),
]
S5_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S5,
    "description": (
        "Source A covers WW / all-rights / 2020-2025; Source B covers "
        "US / mechanical / 2019-2023. Scopes differ in territory, rights category, "
        "and period — shares must NOT be compared. No conflict finding expected."
    ),
    "must_appear": [],
    "must_not_flag": ["conflicting_shares"],
}
S5_README = """\
# FICTIONAL DEMO DATA — Scenario 05: incompatible_scopes

One work has ownership data from two sources, but the scopes are incompatible:
Source A covers worldwide all-rights for 2020–2025, while Source B covers US
mechanical rights for 2019–2023. Different territory, different rights category,
and different period mean the figures cannot be directly compared, so SoundDue
must raise **no** conflict finding for this pair of sources.
"""


# ===========================================================================
# SCENARIO 6 — unmapped_recording
# ===========================================================================
S6 = "scenario_06_unmapped_recording"

# Uses recording Style A headers
S6_RECORDINGS = [
    ["REC-S6-001", "Ghost Signal", "Artist Zeta", "Demo", "163", ""],
    ["REC-S6-002", "Ghost Signal", "Artist Zeta", "Album", "171", ""],
]
S6_WORKS = [
    ["WRK-S6-001", "Ghost Signal", "Writer E", ""],
]
S6_MAPPINGS = [
    # REC-S6-002 is mapped (verified); REC-S6-001 is intentionally absent
    ["REC-S6-002", "WRK-S6-001", "LabelZeta", "true"],
]
S6_OWNERSHIP = [
    own_a("WRK-S6-001", "WRT-E-S6", "Writer E",
          "100.0000", "publisher-share", "mechanical", "WW",
          "2022-01-01", "2032-12-31", "claimed"),
]
S6_FINDINGS = {
    "_label": "FICTIONAL DEMO DATA",
    "scenario": S6,
    "description": (
        "REC-S6-001 ('Ghost Signal' demo) has no verified mapping to any work. "
        "REC-S6-002 (album version) IS mapped. SoundDue must flag R4 for the "
        "unmapped recording. A title match between REC-S6-001 and WRK-S6-001 "
        "must NOT be used as a link."
    ),
    "must_appear": [
        {
            "type": "unlinked_recording",
            "rule_id": "R4",
            "description": (
                "REC-S6-001 has no verified mapping to any work in the supplied "
                "records. Title similarity to WRK-S6-001 is insufficient."
            ),
        }
    ],
    "must_not_flag": ["title_match_link"],
}
S6_README = """\
# FICTIONAL DEMO DATA — Scenario 06: unmapped_recording

Two recordings of "Ghost Signal" exist: a demo (REC-S6-001) and an album version
(REC-S6-002). Only the album version has a verified mapping to the work WRK-S6-001.
The demo recording has no mapping entry at all. SoundDue must raise an
`unlinked_recording` finding (R4) for the demo; a title-based link must never
be used as a substitute for an explicit mapping.
"""


# ===========================================================================
# BROKEN FILE — validation demo
# ===========================================================================
BROKEN_DIR = "broken_file"

BROKEN_OWNERSHIP_HEADERS = OWNERSHIP_HEADERS_A
BROKEN_OWNERSHIP_ROWS = [
    # Bad: share = 150 % (exceeds 100)
    own_a("WRK-X-001", "WRT-A", "Writer A",
          "150.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "claimed"),
    # Bad: duplicate of the next row (same contributor, same scope)
    own_a("WRK-X-001", "WRT-B", "Writer B",
          "30.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "claimed"),
    own_a("WRK-X-001", "WRT-B", "Writer B",
          "30.0000", "publisher-share", "mechanical", "WW",
          "2020-01-01", "2030-12-31", "claimed"),   # exact duplicate
    # Bad: negative share
    own_a("WRK-X-002", "WRT-C", "Writer C",
          "-5.0000", "publisher-share", "performance", "US",
          "2023-01-01", "2028-12-31", "claimed"),
    # Bad: effective_to before effective_from
    own_a("WRK-X-002", "WRT-D", "Writer D",
          "50.0000", "publisher-share", "performance", "US",
          "2025-01-01", "2020-12-31", "claimed"),   # dates reversed
    # Bad: invalid status
    own_a("WRK-X-003", "WRT-E", "Writer E",
          "100.0000", "publisher-share", "sync", "WW",
          "2020-01-01", "2030-12-31", "approved"),  # not in vocabulary
]
BROKEN_README = """\
# FICTIONAL DEMO DATA — Broken File: validation demo

This file is intentionally malformed to demonstrate SoundDue input validation.
The following errors are present (all data is fictional):

| Row | Error |
|-----|-------|
| 1   | `share` = 150.0000 — exceeds 100 % |
| 2–3 | Exact duplicate rows for WRT-B (same contributor, scope, and values) |
| 4   | `share` = -5.0000 — below 0 % |
| 5   | `effective_to` (2020-12-31) is before `effective_from` (2025-01-01) |
| 6   | `status` = "approved" — not in allowed vocabulary |

None of these rows should be accepted by the `OwnershipClaim` Pydantic model.
"""


# ===========================================================================
# Generator
# ===========================================================================
def generate() -> None:
    print("SoundDue synthetic data generator")
    print("FICTIONAL DEMO DATA — not real persons, ISRCs, or organisations.")
    print()

    # -- Scenario 1 ----------------------------------------------------------
    d = BASE_DIR / S1
    write_csv(d / "recordings.csv", RECORDING_HEADERS_A, S1_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S1_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S1_MAPPINGS)
    write_csv(d / "ownership.csv", OWNERSHIP_HEADERS_A, S1_OWNERSHIP)
    write_json(d / "expected_findings.json", S1_FINDINGS)
    write_text(d / "README.md", S1_README)
    print(f"  [OK] {S1}")

    # -- Scenario 2 ----------------------------------------------------------
    d = BASE_DIR / S2
    write_csv(d / "recordings.csv", RECORDING_HEADERS_A, S2_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S2_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S2_MAPPINGS)
    write_csv(d / "ownership.csv", OWNERSHIP_HEADERS_B, S2_OWNERSHIP)
    write_json(d / "expected_findings.json", S2_FINDINGS)
    write_text(d / "README.md", S2_README)
    print(f"  [OK] {S2}")

    # -- Scenario 3 ----------------------------------------------------------
    d = BASE_DIR / S3
    write_csv(d / "recordings.csv", RECORDING_HEADERS_A, S3_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S3_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S3_MAPPINGS)
    write_csv(d / "ownership.csv", OWNERSHIP_HEADERS_A, S3_OWNERSHIP)
    write_json(d / "expected_findings.json", S3_FINDINGS)
    write_text(d / "README.md", S3_README)
    print(f"  [OK] {S3}")

    # -- Scenario 4 ----------------------------------------------------------
    d = BASE_DIR / S4
    write_csv(d / "recordings.csv", RECORDING_HEADERS_B, S4_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S4_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S4_MAPPINGS)
    write_csv(d / "ownership_source_a.csv", OWNERSHIP_HEADERS_A, S4_OWNERSHIP_A)
    write_csv(d / "ownership_source_b.csv", OWNERSHIP_HEADERS_B, S4_OWNERSHIP_B)
    write_json(d / "expected_findings.json", S4_FINDINGS)
    write_text(d / "README.md", S4_README)
    print(f"  [OK] {S4}")

    # -- Scenario 5 ----------------------------------------------------------
    d = BASE_DIR / S5
    write_csv(d / "recordings.csv", RECORDING_HEADERS_A, S5_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S5_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S5_MAPPINGS)
    write_csv(d / "ownership_worldwide.csv", OWNERSHIP_HEADERS_A, S5_OWNERSHIP_A)
    write_csv(d / "ownership_us.csv", OWNERSHIP_HEADERS_B, S5_OWNERSHIP_B)
    write_json(d / "expected_findings.json", S5_FINDINGS)
    write_text(d / "README.md", S5_README)
    print(f"  [OK] {S5}")

    # -- Scenario 6 ----------------------------------------------------------
    d = BASE_DIR / S6
    write_csv(d / "recordings.csv", RECORDING_HEADERS_A, S6_RECORDINGS)
    write_csv(d / "works.csv", WORK_HEADERS, S6_WORKS)
    write_csv(d / "mappings.csv", MAPPING_HEADERS, S6_MAPPINGS)
    write_csv(d / "ownership.csv", OWNERSHIP_HEADERS_A, S6_OWNERSHIP)
    write_json(d / "expected_findings.json", S6_FINDINGS)
    write_text(d / "README.md", S6_README)
    print(f"  [OK] {S6}")

    # -- Broken file ---------------------------------------------------------
    d = BASE_DIR / BROKEN_DIR
    write_csv(d / "bad_ownership.csv",
              BROKEN_OWNERSHIP_HEADERS, BROKEN_OWNERSHIP_ROWS)
    write_text(d / "README.md", BROKEN_README)
    print(f"  [OK] {BROKEN_DIR}")


def verify_determinism() -> None:
    """
    Hash every generated file, run generate() again, re-hash, compare.
    Raises SystemExit if any file differs.
    """
    def hash_tree(base: Path) -> dict[str, str]:
        out = {}
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.name != "generate.py":
                out[str(p.relative_to(base))] = (
                    hashlib.sha256(p.read_bytes()).hexdigest()
                )
        return out

    before = hash_tree(BASE_DIR)
    generate()
    after = hash_tree(BASE_DIR)

    changed = [k for k in after if before.get(k) != after[k]]
    added   = [k for k in after if k not in before]
    removed = [k for k in before if k not in after]

    if changed or added or removed:
        print("\nDETERMINISM CHECK FAILED")
        for f in changed:  print(f"  CHANGED : {f}")
        for f in added:    print(f"  ADDED   : {f}")
        for f in removed:  print(f"  REMOVED : {f}")
        sys.exit(1)
    else:
        print("\nDeterminism check passed — second run produced identical files.")


if __name__ == "__main__":
    generate()
    print()
    verify_determinism()
