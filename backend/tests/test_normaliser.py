"""
tests/test_normaliser.py
========================
Unit tests for app.normaliser — type coercion, scope defaults,
comparison key generation, and raw verbatim preservation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.normaliser import (
    UNKNOWN,
    NormalisedRow,
    make_comparison_key,
    normalise_row,
    normalise_rows,
)


# ---------------------------------------------------------------------------
# make_comparison_key
# ---------------------------------------------------------------------------
class TestMakeComparisonKey:
    def test_empty_string(self):
        assert make_comparison_key("") == ""

    def test_casefolded(self):
        assert make_comparison_key("Golden Hour") == "golden hour"

    def test_accent_stripped(self):
        # ñ → n, é → e
        assert make_comparison_key("Ñoño") == "nono"
        assert make_comparison_key("café") == "cafe"

    def test_whitespace_collapsed(self):
        assert make_comparison_key("  Multiple   Spaces  ") == "multiple spaces"

    def test_combined(self):
        assert make_comparison_key("  Ré Mi  ") == "re mi"

    def test_unicode_casefold(self):
        # German sharp-s: ß → ss
        assert make_comparison_key("STRAßE") == "strasse"


# ---------------------------------------------------------------------------
# normalise_row — share coercion
# ---------------------------------------------------------------------------
class TestNormaliseRowShare:
    def _row(self, share_val: str) -> NormalisedRow:
        return normalise_row(
            raw_canonical={"share": share_val},
            original_cells={"Share %": share_val},
        )

    def test_valid_decimal(self):
        nr = self._row("60.0000")
        assert nr.normalised["share"] == Decimal("60.0000")

    def test_integer_string(self):
        nr = self._row("50")
        assert nr.normalised["share"] == Decimal("50")

    def test_empty_share_is_none(self):
        nr = self._row("")
        assert nr.normalised["share"] is None

    def test_non_numeric_share_is_none(self):
        nr = self._row("abc")
        assert nr.normalised["share"] is None

    def test_whitespace_share_is_none(self):
        nr = self._row("   ")
        assert nr.normalised["share"] is None


# ---------------------------------------------------------------------------
# normalise_row — scope fields default to "unknown"
# ---------------------------------------------------------------------------
class TestNormaliseRowScopeFields:
    def test_empty_territory_becomes_unknown(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["territory"] == UNKNOWN

    def test_empty_rights_category_becomes_unknown(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["rights_category"] == UNKNOWN

    def test_empty_effective_from_becomes_unknown(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["effective_from"] == UNKNOWN

    def test_empty_effective_to_becomes_unknown(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["effective_to"] == UNKNOWN

    def test_empty_share_convention_becomes_unknown(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["share_convention"] == UNKNOWN

    def test_nonempty_territory_kept(self):
        nr = normalise_row(raw_canonical={"territory": "WW"}, original_cells={})
        assert nr.normalised["territory"] == "WW"

    def test_nonempty_rights_category_kept(self):
        nr = normalise_row(raw_canonical={"rights_category": "mechanical"}, original_cells={})
        assert nr.normalised["rights_category"] == "mechanical"

    def test_whitespace_only_territory_becomes_unknown(self):
        nr = normalise_row(raw_canonical={"territory": "   "}, original_cells={})
        assert nr.normalised["territory"] == UNKNOWN


# ---------------------------------------------------------------------------
# normalise_row — verified flag
# ---------------------------------------------------------------------------
class TestNormaliseRowVerified:
    def _row(self, val: str) -> NormalisedRow:
        return normalise_row(raw_canonical={"verified": val}, original_cells={})

    def test_true_string(self):
        assert self._row("true").normalised["verified"] is True

    def test_yes_string(self):
        assert self._row("yes").normalised["verified"] is True

    def test_one_string(self):
        assert self._row("1").normalised["verified"] is True

    def test_y_string(self):
        assert self._row("y").normalised["verified"] is True

    def test_false_string(self):
        assert self._row("false").normalised["verified"] is False

    def test_empty_string(self):
        assert self._row("").normalised["verified"] is False

    def test_absent(self):
        nr = normalise_row(raw_canonical={}, original_cells={})
        assert nr.normalised["verified"] is False

    def test_case_insensitive_true(self):
        assert self._row("TRUE").normalised["verified"] is True
        assert self._row("True").normalised["verified"] is True
        assert self._row("YES").normalised["verified"] is True


# ---------------------------------------------------------------------------
# normalise_row — raw verbatim
# ---------------------------------------------------------------------------
class TestNormaliseRowRaw:
    def test_raw_preserves_original_keys_and_values(self):
        original = {"Track Code": "0042", "Songwriter %": "60.0"}
        nr = normalise_row(
            raw_canonical={"recording_id": "0042", "share": "60.0"},
            original_cells=original,
        )
        assert nr.raw == original

    def test_raw_is_independent_copy(self):
        original = {"col": "val"}
        nr = normalise_row(raw_canonical={}, original_cells=original)
        original["col"] = "mutated"
        assert nr.raw["col"] == "val"  # copy, not reference


# ---------------------------------------------------------------------------
# normalise_row — comparison keys
# ---------------------------------------------------------------------------
class TestNormaliseRowComparisonKeys:
    def test_title_key_is_casefolded(self):
        nr = normalise_row(
            raw_canonical={"title": "Golden Hour"},
            original_cells={},
        )
        assert nr.comparison_keys["title_key"] == "golden hour"

    def test_comparison_keys_not_in_normalised(self):
        nr = normalise_row(
            raw_canonical={"title": "Golden Hour"},
            original_cells={},
        )
        assert "title_key" not in nr.normalised
        assert "contributor_name_key" not in nr.normalised

    def test_accent_stripped_in_key(self):
        nr = normalise_row(
            raw_canonical={"title": "Café Bleu"},
            original_cells={},
        )
        assert nr.comparison_keys["title_key"] == "cafe bleu"

    def test_writers_key(self):
        nr = normalise_row(
            raw_canonical={"writers": "Writer X"},
            original_cells={},
        )
        assert nr.comparison_keys["writers_key"] == "writer x"


# ---------------------------------------------------------------------------
# normalise_rows — batch
# ---------------------------------------------------------------------------
class TestNormaliseRows:
    def test_returns_list_of_same_length(self):
        canon = [{"recording_id": "R1"}, {"recording_id": "R2"}]
        orig  = [{"col": "R1"}, {"col": "R2"}]
        result = normalise_rows(canon, orig)
        assert len(result) == 2

    def test_row_numbers_start_at_1(self):
        canon = [{"recording_id": "R1"}, {"recording_id": "R2"}]
        orig  = [{}, {}]
        result = normalise_rows(canon, orig)
        assert result[0].source_ref["row_number"] == 1
        assert result[1].source_ref["row_number"] == 2

    def test_source_ref_base_merged(self):
        canon = [{"recording_id": "R1"}]
        orig  = [{}]
        result = normalise_rows(canon, orig, source_ref_base={"file_name": "test.csv", "file_id": 7})
        assert result[0].source_ref["file_name"] == "test.csv"
        assert result[0].source_ref["file_id"] == 7
        assert result[0].source_ref["row_number"] == 1
