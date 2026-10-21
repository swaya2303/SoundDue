"""
reasoning/tests/test_wrapper.py
================================
Tests for reasoning.wrapper, reasoning.engine, and reasoning.facts.

Run with the Python 3.12 venv:
    reasoning\\.venv\\Scripts\\python.exe -m pytest reasoning/tests/ -v

These tests require ``hyperon`` to be installed (reasoning/.venv).
They are automatically skipped if the import fails (e.g. running from the
backend Python 3.13 environment where hyperon is not available).
"""
from __future__ import annotations

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Check hyperon availability; skip all tests if it is not importable.
# ---------------------------------------------------------------------------
_hyperon_available: bool
try:
    import hyperon  # noqa: F401
    _hyperon_available = True
except ImportError:
    _hyperon_available = False

pytestmark = pytest.mark.skipif(
    not _hyperon_available,
    reason=(
        "hyperon not importable in this Python environment. "
        "Run tests with: reasoning\\.venv\\Scripts\\python.exe -m pytest reasoning/tests/ -v"
    ),
)


# ---------------------------------------------------------------------------
# Imports (inside functions where possible to support the skip guard above)
# ---------------------------------------------------------------------------
if _hyperon_available:
    from reasoning.wrapper import quote, load_facts, query
    from reasoning.facts import dicts_to_facts
    from reasoning.engine import get_engine


# ===========================================================================
# TestLoadAndQuery
# ===========================================================================

class TestLoadAndQuery:
    """Basic round-trip: load facts → run query → get results back to Python."""

    def test_trivial_query_returns_results(self):
        """Load a verified-mapping fact and retrieve the recording_id."""
        facts = load_facts([
            '(verified-mapping "REC-001" "WRK-001" "LabelX")',
        ])
        results = query(facts, 'match &self (verified-mapping $r $w $s) $r')
        assert len(results) == 1
        assert '"REC-001"' in results[0]

    def test_claim_fact_queryable(self):
        """A claim fact can be retrieved by work_id."""
        facts = load_facts([
            '(claim "WRK-001" "Writer A" "60.0000" "mechanical" "WW" "2020-01-01" "2030-12-31" "writer-share")',
        ])
        results = query(facts, 'match &self (claim $w $c $s $rc $t $f $to $sc) $w')
        assert len(results) == 1
        assert '"WRK-001"' in results[0]

    def test_multiple_facts_all_returned(self):
        """Multiple facts of the same type are all matchable."""
        facts = load_facts([
            '(verified-mapping "REC-001" "WRK-001" "LabelA")',
            '(verified-mapping "REC-002" "WRK-002" "LabelB")',
        ])
        results = query(facts, 'match &self (verified-mapping $r $w $s) $r')
        result_str = " ".join(results)
        assert '"REC-001"' in result_str
        assert '"REC-002"' in result_str

    def test_no_match_returns_empty(self):
        """Querying for a non-existent predicate returns an empty list."""
        facts = load_facts(['(verified-mapping "R1" "W1" "L1")'])
        results = query(facts, 'match &self (claim $w $c $s $rc $t $f $to $sc) $w')
        assert results == []

    def test_empty_program_empty_result(self):
        """An empty program produces no results."""
        results = query("", 'match &self (verified-mapping $r $w $s) $r')
        assert results == []


# ===========================================================================
# TestFreshSpacePerCall
# ===========================================================================

class TestFreshSpacePerCall:
    """Each query() call must use a fresh MeTTa space — no state leaks."""

    def test_two_calls_do_not_share_state(self):
        """State from the first call must not appear in the second call."""
        r1 = query(
            '(verified-mapping "R1" "W1" "L")',
            'match &self (verified-mapping $r $w $s) $r',
        )
        r2 = query(
            '(verified-mapping "R2" "W2" "L")',
            'match &self (verified-mapping $r $w $s) $r',
        )
        assert any('"R1"' in x for x in r1)
        assert any('"R2"' in x for x in r2)
        # R1 must NOT appear in the second call's results
        assert not any('"R1"' in x for x in r2)

    def test_independent_calls_have_isolated_namespaces(self):
        """Facts from call A cannot leak into call B's results."""
        _r1 = query(
            '(claim "W-LEAKY" "Artist" "50.0" "mechanical" "WW" "unknown" "unknown" "unknown")',
            'match &self (claim $w $c $s $rc $t $f $to $sc) $w',
        )
        r2 = query(
            '(verified-mapping "R-CLEAN" "W-CLEAN" "L")',
            'match &self (claim $w $c $s $rc $t $f $to $sc) $w',
        )
        assert r2 == [], f"Expected empty, got: {r2}"


# ===========================================================================
# TestInjectionSafety
# ===========================================================================

class TestInjectionSafety:
    """Hostile user strings must be inert data, not executable MeTTa."""

    def test_quote_returns_metta_string_literal(self):
        hostile = 'inject") (! rm -rf /)  ; "'
        quoted = quote(hostile)
        assert quoted.startswith('"'), f"Must start with quote: {quoted!r}"
        assert quoted.endswith('"'), f"Must end with quote: {quoted!r}"

    def test_hostile_string_has_no_unquoted_exclamation(self):
        hostile = 'inject") (! rm -rf /)  ; "'
        quoted = quote(hostile)
        # Strip the outer quotes and unescape to verify no raw '!' outside strings
        # The quoted form itself should not have a bare '!'
        # Remove the outer surrounding quotes
        inner = quoted[1:-1]
        # Any '!' must be inside the escaped sequence — the outer wrapping already
        # ensures this, but we double-check by confirming load_facts does not raise
        facts = load_facts([
            f'(claim "WRK-HOSTILE" {quoted} "50.0" "mechanical" "WW" "unknown" "unknown" "unknown")'
        ])
        assert facts  # no exception raised

    def test_hostile_string_data_not_executed(self):
        """The hostile string is stored as data and can be retrieved intact."""
        hostile = 'inject") (! rm -rf /)  ; "'
        quoted = quote(hostile)
        facts = load_facts([
            f'(claim "WRK-001" {quoted} "50.0" "mechanical" "WW" "unknown" "unknown" "unknown")'
        ])
        results = query(facts, 'match &self (claim $w $c $s $rc $t $f $to $sc) $c')
        assert len(results) == 1, f"Expected 1 result, got: {results}"
        # The result must contain the hostile text as a data value
        assert "rm -rf" in results[0]

    def test_load_facts_validates_no_injection(self):
        """load_facts() raises ValueError if an unquoted '!' is present."""
        from reasoning.wrapper import _validate_no_injection
        import pytest as _pytest
        with _pytest.raises(ValueError, match="Unquoted '!'"):
            _validate_no_injection("(do-bad !(rm -rf /))")

    def test_backslash_in_user_text_escaped(self):
        """Backslashes in user data are doubled before wrapping."""
        text_with_backslash = r"path\to\file"
        quoted = quote(text_with_backslash)
        assert "\\\\" in quoted  # backslash is doubled

    def test_double_quote_in_user_text_escaped(self):
        """Double-quotes in user data are backslash-escaped."""
        text_with_dquote = 'say "hello"'
        quoted = quote(text_with_dquote)
        assert '\\"' in quoted


# ===========================================================================
# TestDictsToFacts
# ===========================================================================

class TestDictsToFacts:
    """Tests for reasoning.facts.dicts_to_facts (no DB required)."""

    def test_verified_mapping_fact_generated(self):
        facts = dicts_to_facts(
            mappings=[{
                "recording_id": "R1",
                "work_id": "W1",
                "source_label": "LabelX",
                "verified": "true",
            }]
        )
        assert any("verified-mapping" in f for f in facts), f"No verified-mapping in {facts}"
        assert any('"R1"' in f for f in facts)

    def test_unverified_mapping_not_emitted(self):
        facts = dicts_to_facts(
            mappings=[{
                "recording_id": "R1",
                "work_id": "W1",
                "source_label": "LabelX",
                "verified": "false",
            }]
        )
        assert not any("verified-mapping" in f for f in facts)

    def test_claim_fact_generated(self):
        facts = dicts_to_facts(
            claims=[{
                "work_id": "W1",
                "contributor": "Writer A",
                "share": "60.0000",
                "status": "",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "2020-01-01",
                "effective_to": "2030-12-31",
                "share_convention": "unknown",
            }]
        )
        assert any("claim" in f for f in facts)
        assert any('"W1"' in f and '"Writer A"' in f for f in facts)

    def test_unclaimed_fact_generated(self):
        facts = dicts_to_facts(
            claims=[{
                "work_id": "W1",
                "contributor": "Pool",
                "share": "40.0",
                "status": "unclaimed",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "unknown",
                "effective_to": "unknown",
                "share_convention": "unknown",
            }]
        )
        assert any("unclaimed" in f for f in facts), f"No unclaimed in {facts}"

    def test_scope_compatible_emitted_for_overlapping_scopes(self):
        claims = [
            {
                "work_id": "W1",
                "contributor": "A",
                "share": "60.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "2020-01-01",
                "effective_to": "2030-12-31",
                "share_convention": "unknown",
            },
            {
                "work_id": "W1",
                "contributor": "B",
                "share": "40.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "2020-01-01",
                "effective_to": "2030-12-31",
                "share_convention": "unknown",
            },
        ]
        facts = dicts_to_facts(claims=claims)
        assert any("scope-compatible" in f for f in facts), f"No scope-compatible in {facts}"

    def test_scope_compatible_not_emitted_for_different_territory(self):
        """Two claims with different territories are NOT scope-compatible."""
        claims = [
            {
                "work_id": "W1",
                "contributor": "A",
                "share": "60.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "US",
                "effective_from": "2020-01-01",
                "effective_to": "2030-12-31",
                "share_convention": "unknown",
            },
            {
                "work_id": "W1",
                "contributor": "B",
                "share": "40.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "UK",
                "effective_from": "2020-01-01",
                "effective_to": "2030-12-31",
                "share_convention": "unknown",
            },
        ]
        facts = dicts_to_facts(claims=claims)
        assert not any("scope-compatible" in f for f in facts), \
            f"scope-compatible should not be emitted for different territories: {facts}"

    def test_unknown_scope_fields_default_correctly(self):
        """Missing scope fields default to 'unknown', not empty string."""
        claims = [
            {
                "work_id": "W1",
                "contributor": "A",
                "share": "50.0",
                "status": "",
                # No rights_category, territory, effective_from/to, share_convention
            }
        ]
        facts = dicts_to_facts(claims=claims)
        claim_fact = next((f for f in facts if "claim" in f), None)
        assert claim_fact is not None
        # All scope fields should be the quoted "unknown" sentinel
        assert claim_fact.count('"unknown"') >= 4  # territory, eff_from, eff_to, share_conv


# ===========================================================================
# TestEngineInProcess
# ===========================================================================

class TestEngineInProcess:
    """Tests for the InProcessEngine via get_engine()."""

    def test_get_engine_inprocess_returns_results(self):
        engine = get_engine("inprocess")
        engine.load_facts(['(verified-mapping "R1" "W1" "L")'])
        results = engine.query('match &self (verified-mapping $r $w $s) $r')
        assert any('"R1"' in x for x in results), f"R1 not found in {results}"

    def test_engine_accumulates_facts_across_load_calls(self):
        """Multiple load_facts() calls accumulate before a query."""
        engine = get_engine("inprocess")
        engine.load_facts(['(verified-mapping "R1" "W1" "L")'])
        engine.load_facts(['(verified-mapping "R2" "W2" "L")'])
        results = engine.query('match &self (verified-mapping $r $w $s) $r')
        result_str = " ".join(results)
        assert '"R1"' in result_str
        assert '"R2"' in result_str

    def test_engine_reset_clears_state(self):
        """reset() must clear accumulated facts so old data cannot bleed into new queries."""
        engine = get_engine("inprocess")
        engine.load_facts(['(verified-mapping "R1" "W1" "L")'])
        engine.reset()
        engine.load_facts(['(verified-mapping "R2" "W2" "L")'])
        results = engine.query('match &self (verified-mapping $r $w $s) $r')
        result_str = " ".join(results)
        assert '"R1"' not in result_str, "R1 must not appear after reset"
        assert '"R2"' in result_str

    def test_engine_reset_returns_self(self):
        """reset() should return the engine for chaining."""
        engine = get_engine("inprocess")
        result = engine.reset()
        assert result is engine

    def test_engine_load_facts_returns_self(self):
        """load_facts() should return the engine for chaining."""
        engine = get_engine("inprocess")
        result = engine.load_facts(['(verified-mapping "R1" "W1" "L")'])
        assert result is engine

    def test_engine_load_rules_from_file(self, tmp_path):
        """load_rules() reads a .metta file and appends to the program buffer."""
        rules_file = tmp_path / "test.metta"
        rules_file.write_text(
            '(= (has-link $r) (match &self (verified-mapping $r $w $s) True))\n',
            encoding="utf-8",
        )
        engine = get_engine("inprocess")
        engine.load_rules(rules_file)
        engine.load_facts(['(verified-mapping "R1" "W1" "L")'])
        results = engine.query('match &self (verified-mapping $r $w $s) $r')
        assert any('"R1"' in x for x in results)

    def test_get_engine_invalid_mode_raises(self):
        """An unknown mode raises ValueError with a clear message."""
        with pytest.raises(ValueError, match="Unknown METTA_MODE"):
            get_engine("bananamode")


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """Full pipeline: dicts_to_facts → load_facts → query."""

    def test_full_pipeline_verified_mapping(self):
        """End-to-end: dict → MeTTa fact → query → result."""
        facts_list = dicts_to_facts(
            mappings=[{
                "recording_id": "END-REC-001",
                "work_id": "END-WRK-001",
                "source_label": "TestLabel",
                "verified": "true",
            }]
        )
        program = load_facts(facts_list)
        results = query(program, 'match &self (verified-mapping $r $w $s) $r')
        assert any('"END-REC-001"' in x for x in results)

    def test_full_pipeline_claim_and_scope(self):
        """Claim and scope-compatible facts are both emitted and queryable."""
        claims = [
            {
                "work_id": "WRK-SC-01",
                "contributor": "Artist Alpha",
                "share": "55.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "2021-01-01",
                "effective_to": "2031-12-31",
                "share_convention": "unknown",
            },
            {
                "work_id": "WRK-SC-01",
                "contributor": "Artist Beta",
                "share": "45.0",
                "status": "",
                "rights_category": "mechanical",
                "territory": "WW",
                "effective_from": "2021-01-01",
                "effective_to": "2031-12-31",
                "share_convention": "unknown",
            },
        ]
        facts_list = dicts_to_facts(claims=claims)
        program = load_facts(facts_list)

        # Both claims are retrievable
        claim_results = query(program, 'match &self (claim $w $c $s $rc $t $f $to $sc) $c')
        contributors = " ".join(claim_results)
        assert '"Artist Alpha"' in contributors
        assert '"Artist Beta"' in contributors

        # scope-compatible fact was emitted and is queryable
        scope_results = query(program, 'match &self (scope-compatible $a $b $rc $t $f $to) $a')
        assert any('"WRK-SC-01"' in x for x in scope_results), \
            f"scope-compatible not found in results: {scope_results}"
