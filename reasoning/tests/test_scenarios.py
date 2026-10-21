"""
reasoning/tests/test_scenarios.py
==================================
Parametrised end-to-end scenario tests.

For every folder in data/synthetic/scenario_0*/:
  1. Load expected_findings.json.
  2. Read all CSVs; apply column synonym mapping to produce canonical dicts.
  3. Call reasoning.rule_runner.run_rules() (via MeTTa / hyperon 0.2.10).
  4. Assert every must_appear[*].type appears in the returned finding_type values.
  5. Assert no must_not_flag type appears.

Tests are SKIPPED (not failed) when hyperon is not importable, so the full
backend test suite (Python 3.13) continues to pass unmodified.

Run with the reasoning venv:
    reasoning\\.venv\\Scripts\\python.exe -m pytest reasoning\\tests\\test_scenarios.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip the whole module if hyperon is unavailable (e.g. running under Python 3.13)
# ---------------------------------------------------------------------------
try:
    import hyperon  # noqa: F401  # type: ignore[import]
    _HYPERON_AVAILABLE = True
except ImportError:
    _HYPERON_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _HYPERON_AVAILABLE,
    reason="hyperon not available in this Python environment — run from reasoning/.venv (Python 3.12)",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent  # sounddue/
_SYNTHETIC_DIR = _REPO_ROOT / "data" / "synthetic"

# ---------------------------------------------------------------------------
# Column synonym maps
# The test normalises whatever column names are in the CSV to canonical names
# before passing rows to run_rules().
# ---------------------------------------------------------------------------

# Ownership Format A  (Work Code, Writer Code, …)
_OWN_FORMAT_A: dict[str, str] = {
    "Work Code": "work_id",
    "Writer Code": "contributor_id",
    "Songwriter": "contributor_name",
    "Songwriter %": "share",
    "Convention": "share_convention",
    "Rights Type": "rights_category",
    "Territory": "territory",
    "Valid From": "effective_from",
    "Valid To": "effective_to",
    "Claim Status": "status",
}

# Ownership Format B  (Composition ID, Contributor ID, …)
_OWN_FORMAT_B: dict[str, str] = {
    "Composition ID": "work_id",
    "Contributor ID": "contributor_id",
    "Rights Holder": "contributor_name",
    "Share %": "share",
    "Share Type": "share_convention",
    "Rights Category": "rights_category",
    "Market": "territory",
    "Period Start": "effective_from",
    "Period End": "effective_to",
    "Status": "status",
}

# Recording Format A  (Track Code, Track Title, …)
_REC_FORMAT_A: dict[str, str] = {
    "Track Code": "recording_id",
    "Track Title": "title",
    "Main Artist": "performer",
    "Version": "version",
    "Secs": "duration_seconds",
    "ISRC Code": "isrc",
}

# Mapping CSV  — already canonical; identity map guards against stray renames
_MAP_IDENTITY: dict[str, str] = {
    "recording_id": "recording_id",
    "work_id": "work_id",
    "source_label": "source_label",
    "verified": "verified",
}


def _detect_ownership_map(columns: list[str]) -> dict[str, str]:
    """Return the right synonym map based on actual CSV column names."""
    if "Work Code" in columns:
        return _OWN_FORMAT_A
    if "Composition ID" in columns:
        return _OWN_FORMAT_B
    # Fall back: assume already canonical
    return {c: c for c in columns}


def _detect_recording_map(columns: list[str]) -> dict[str, str]:
    """Return recording synonym map."""
    if "Track Code" in columns:
        return _REC_FORMAT_A
    # Format B — already canonical
    return {c: c for c in columns}


def _apply_map(rows: list[dict], col_map: dict[str, str]) -> list[dict]:
    """Rename dict keys according to col_map; drop unknown keys."""
    out = []
    for row in rows:
        out.append({col_map[k]: v for k, v in row.items() if k in col_map})
    return out


def _csv_to_dicts(path: Path) -> list[dict]:
    """Read a CSV and return a list of row dicts (str values, stripped)."""
    import csv

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return [{k: (v.strip() if v else "") for k, v in row.items()} for row in reader]


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------

def _load_scenario(scenario_dir: Path) -> tuple[list[dict], list[dict], list[dict], dict]:
    """
    Returns (ownership_rows, recording_rows, mapping_rows, expected).

    ownership_rows: all ownership CSVs concatenated and normalised.
    recording_rows: all recording CSVs concatenated and normalised.
    mapping_rows:   all mapping CSVs concatenated and normalised.
    expected:       contents of expected_findings.json.
    """
    expected_path = scenario_dir / "expected_findings.json"
    with expected_path.open(encoding="utf-8") as fh:
        expected = json.load(fh)

    # --- Ownership ---
    ownership_rows: list[dict] = []
    for csv_path in sorted(scenario_dir.glob("ownership*.csv")):
        raw = _csv_to_dicts(csv_path)
        if not raw:
            continue
        col_map = _detect_ownership_map(list(raw[0].keys()))
        ownership_rows.extend(_apply_map(raw, col_map))

    # --- Recordings ---
    recording_rows: list[dict] = []
    for csv_path in sorted(scenario_dir.glob("recording*.csv")):
        raw = _csv_to_dicts(csv_path)
        if not raw:
            continue
        col_map = _detect_recording_map(list(raw[0].keys()))
        recording_rows.extend(_apply_map(raw, col_map))

    # --- Mappings ---
    mapping_rows: list[dict] = []
    for csv_path in sorted(scenario_dir.glob("mapping*.csv")):
        raw = _csv_to_dicts(csv_path)
        if not raw:
            continue
        # Mappings are already canonical; pass through identity map
        mapping_rows.extend(raw)

    return ownership_rows, recording_rows, mapping_rows, expected


# ---------------------------------------------------------------------------
# Collect scenarios
# ---------------------------------------------------------------------------

_SCENARIOS = sorted(_SYNTHETIC_DIR.glob("scenario_0*")) if _SYNTHETIC_DIR.exists() else []


# ---------------------------------------------------------------------------
# Parametrised test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_dir", _SCENARIOS, ids=lambda p: p.name)
def test_scenario(scenario_dir: Path) -> None:
    """
    Run all four MeTTa rules for one scenario and verify findings against
    expected_findings.json.
    """
    from reasoning.rule_runner import run_rules  # only import when hyperon available

    ownership_rows, recording_rows, mapping_rows, expected = _load_scenario(scenario_dir)

    findings = run_rules(
        ownership_rows=ownership_rows,
        recording_rows=recording_rows,
        mapping_rows=mapping_rows,
    )

    found_types = {f["finding_type"] for f in findings}
    scenario_name = scenario_dir.name

    # ---- must_appear assertions ----
    for entry in expected.get("must_appear", []):
        expected_type = entry["type"]
        assert expected_type in found_types, (
            f"[{scenario_name}] Expected finding type '{expected_type}' "
            f"(rule {entry.get('rule_id', '?')}) was NOT produced.\n"
            f"  Description: {entry.get('description', '')}\n"
            f"  Actual finding types: {sorted(found_types) or '(none)'}"
        )

    # ---- must_not_flag assertions ----
    for forbidden_type in expected.get("must_not_flag", []):
        assert forbidden_type not in found_types, (
            f"[{scenario_name}] Forbidden finding type '{forbidden_type}' "
            f"was produced but must NOT be flagged.\n"
            f"  Actual finding types: {sorted(found_types)}"
        )


# ---------------------------------------------------------------------------
# Extra targeted tests (non-parametrised) documenting specific invariants
# ---------------------------------------------------------------------------

class TestScenario03SameTitleNoLink:
    """S3: Two works sharing 'Golden Hour' must never be merged or linked."""

    def test_no_findings_at_all(self) -> None:
        """Same-title, different writers: zero findings expected."""
        from reasoning.rule_runner import run_rules

        s3 = _SYNTHETIC_DIR / "scenario_03_same_title_different_writers"
        own, rec, mpp, expected = _load_scenario(s3)

        findings = run_rules(own, rec, mpp)
        found_types = {f["finding_type"] for f in findings}

        assert not found_types, (
            "Scenario 3 must produce ZERO findings (two distinct works, "
            f"each 100% owned, no R1/R2/R3/R4 trigger).\n"
            f"Got: {sorted(found_types)}"
        )

    def test_title_match_never_creates_link(self) -> None:
        """'title_match_link' is not a valid finding_type — must never appear."""
        from reasoning.rule_runner import run_rules

        s3 = _SYNTHETIC_DIR / "scenario_03_same_title_different_writers"
        own, rec, mpp, _ = _load_scenario(s3)

        findings = run_rules(own, rec, mpp)
        found_types = {f["finding_type"] for f in findings}
        assert "title_match_link" not in found_types


class TestScenario04ConflictingShares:
    """S4: Conflicting share figures across two source files must be flagged."""

    def test_conflicting_shares_present(self) -> None:
        from reasoning.rule_runner import run_rules

        s4 = _SYNTHETIC_DIR / "scenario_04_conflicting_shares"
        own, rec, mpp, _ = _load_scenario(s4)

        findings = run_rules(own, rec, mpp)
        found_types = {f["finding_type"] for f in findings}
        assert "conflicting_shares" in found_types

    def test_no_incomplete_ownership(self) -> None:
        """S4 must not flag incomplete_ownership_info — sources conflict, they don't omit."""
        from reasoning.rule_runner import run_rules

        s4 = _SYNTHETIC_DIR / "scenario_04_conflicting_shares"
        own, rec, mpp, _ = _load_scenario(s4)

        findings = run_rules(own, rec, mpp)
        found_types = {f["finding_type"] for f in findings}
        assert "incomplete_ownership_info" not in found_types


class TestScenario05IncompatibleScopes:
    """S5: Different territory + rights_category + period must NOT trigger R3."""

    def test_no_conflicting_shares(self) -> None:
        from reasoning.rule_runner import run_rules

        s5 = _SYNTHETIC_DIR / "scenario_05_incompatible_scopes"
        own, rec, mpp, _ = _load_scenario(s5)

        findings = run_rules(own, rec, mpp)
        found_types = {f["finding_type"] for f in findings}
        assert "conflicting_shares" not in found_types, (
            "S5 scopes differ in territory AND rights_category — "
            "R3 must NOT fire. Found: " + str(sorted(found_types))
        )
