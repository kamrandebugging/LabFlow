"""LAB-24 (KAN-144): pure result-calculation engine tests.

These tests are PURE — they exercise ``apps.results.engine`` without any
database access (no ``django_db`` marker). The engine module must import
nothing from django / celery / http layers.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from apps.results.engine import (
    Flag,
    RangeRow,
    compute_delta,
    compute_flag,
    evaluate_qualitative,
    evaluate_result,
    parse_result,
    select_range,
)


def _row(**overrides: Any) -> RangeRow:
    """Build a RangeRow with sane defaults for selection tests."""
    params: dict[str, Any] = {
        "sex": "M",
        "age_min_days": 0,
        "age_max_days": 365,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "low": Decimal("13.500"),
        "high": Decimal("17.500"),
        "critical_low": Decimal("7.000"),
        "critical_high": Decimal("20.000"),
    }
    params.update(overrides)
    return RangeRow(**params)


# ---------------------------------------------------------------------------
# T-01: comparator extraction
# ---------------------------------------------------------------------------


class TestParseResultComparator:
    def test_lt_qualifier(self) -> None:
        parsed = parse_result("<0.1")
        assert parsed.qualifier == "<"
        assert parsed.value == Decimal("0.1")

    def test_gte_qualifier_with_space(self) -> None:
        parsed = parse_result(">= 5")
        assert parsed.qualifier == ">="
        assert parsed.value == Decimal("5")

    def test_lte_qualifier(self) -> None:
        parsed = parse_result("<=3.3")
        assert parsed.qualifier == "<="
        assert parsed.value == Decimal("3.3")

    def test_gt_qualifier(self) -> None:
        parsed = parse_result(">100")
        assert parsed.qualifier == ">"
        assert parsed.value == Decimal("100")

    def test_unicode_leq(self) -> None:
        parsed = parse_result("≤10")
        assert parsed.qualifier == "≤"
        assert parsed.value == Decimal("10")

    def test_unicode_geq(self) -> None:
        parsed = parse_result("≥2.5")
        assert parsed.qualifier == "≥"
        assert parsed.value == Decimal("2.5")

    def test_no_qualifier(self) -> None:
        parsed = parse_result("7.2")
        assert parsed.qualifier is None
        assert parsed.value == Decimal("7.2")

    def test_whitespace_trimmed(self) -> None:
        parsed = parse_result("  < 0.1  ")
        assert parsed.qualifier == "<"
        assert parsed.value == Decimal("0.1")


# ---------------------------------------------------------------------------
# T-02: thousands separators; scientific notation rejected
# ---------------------------------------------------------------------------


class TestParseResultNumbers:
    def test_thousands_separator(self) -> None:
        parsed = parse_result("1,234.5")
        assert parsed.value == Decimal("1234.5")

    def test_multiple_separators(self) -> None:
        parsed = parse_result("1,234,567")
        assert parsed.value == Decimal("1234567")

    def test_scientific_rejected(self) -> None:
        assert parse_result("1e5").value is None

    def test_scientific_upper_rejected(self) -> None:
        assert parse_result("1E5").value is None

    def test_multiple_dots_rejected(self) -> None:
        assert parse_result("12.3.4").value is None

    def test_letters_rejected(self) -> None:
        assert parse_result("trace").value is None

    def test_bare_qualifier_no_number(self) -> None:
        parsed = parse_result("<")
        assert parsed.qualifier == "<"
        assert parsed.value is None

    def test_empty_rejected(self) -> None:
        assert parse_result("").value is None
        assert parse_result("   ").value is None

    def test_negative_value(self) -> None:
        parsed = parse_result("-2.5")
        assert parsed.value == Decimal("-2.5")

    def test_absurd_length_rejected(self) -> None:
        assert parse_result("9" * 33).value is None
        assert parse_result("9" * 32).value == Decimal("9" * 32)


# ---------------------------------------------------------------------------
# T-03: inclusive bounds
# ---------------------------------------------------------------------------


class TestComputeFlagBounds:
    def test_exactly_on_low_is_normal(self) -> None:
        assert (
            compute_flag(Decimal("5"), Decimal("5"), Decimal("10"), None, None)
            == Flag.NORMAL
        )

    def test_exactly_on_high_is_normal(self) -> None:
        assert (
            compute_flag(Decimal("10"), Decimal("5"), Decimal("10"), None, None)
            == Flag.NORMAL
        )

    def test_below_low(self) -> None:
        assert (
            compute_flag(Decimal("4.9"), Decimal("5"), Decimal("10"), None, None)
            == Flag.LOW
        )

    def test_above_high(self) -> None:
        assert (
            compute_flag(Decimal("10.1"), Decimal("5"), Decimal("10"), None, None)
            == Flag.HIGH
        )

    def test_missing_low_not_checked(self) -> None:
        assert (
            compute_flag(Decimal("0.001"), None, Decimal("10"), None, None)
            == Flag.NORMAL
        )

    def test_missing_high_not_checked(self) -> None:
        assert (
            compute_flag(Decimal("9999"), Decimal("5"), None, None, None) == Flag.NORMAL
        )

    def test_none_value_is_none(self) -> None:
        assert compute_flag(None, Decimal("5"), Decimal("10"), None, None) is None


# ---------------------------------------------------------------------------
# T-04: critical override
# ---------------------------------------------------------------------------


class TestComputeFlagCritical:
    def test_below_critical_low(self) -> None:
        assert (
            compute_flag(
                Decimal("2"), Decimal("5"), Decimal("10"), Decimal("3"), Decimal("20")
            )
            == Flag.CRITICAL
        )

    def test_above_critical_high(self) -> None:
        assert (
            compute_flag(
                Decimal("25"), Decimal("5"), Decimal("10"), Decimal("3"), Decimal("20")
            )
            == Flag.CRITICAL
        )

    def test_low_but_not_critical(self) -> None:
        assert (
            compute_flag(
                Decimal("4"), Decimal("5"), Decimal("10"), Decimal("3"), Decimal("20")
            )
            == Flag.LOW
        )

    def test_exactly_on_critical_low_not_critical(self) -> None:
        # Critical bounds are strict: n < critical_low.
        assert (
            compute_flag(
                Decimal("3"), Decimal("5"), Decimal("10"), Decimal("3"), Decimal("20")
            )
            == Flag.LOW
        )

    def test_critical_overrides_high(self) -> None:
        assert (
            compute_flag(
                Decimal("21"), Decimal("5"), Decimal("10"), Decimal("3"), Decimal("20")
            )
            == Flag.CRITICAL
        )


# ---------------------------------------------------------------------------
# T-05: parse failures -> NULL flag, needs_review
# ---------------------------------------------------------------------------


class TestParseFailureNeedsReview:
    def test_bare_qualifier_needs_review(self) -> None:
        ev = evaluate_result(
            "<",
            range_row=_row(),
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=None,
        )
        assert ev.flag is None
        assert ev.needs_review is True
        assert ev.value is None
        assert ev.qualifier == "<"

    def test_trace_needs_review(self) -> None:
        ev = evaluate_result(
            "trace",
            range_row=_row(),
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=None,
        )
        assert ev.flag is None
        assert ev.needs_review is True

    def test_valid_numeric_no_review(self) -> None:
        ev = evaluate_result(
            "15.0",
            range_row=_row(),
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=None,
        )
        assert ev.flag == Flag.NORMAL
        assert ev.needs_review is False
        assert ev.value == Decimal("15.0")


# ---------------------------------------------------------------------------
# T-06: qualitative results
# ---------------------------------------------------------------------------


class TestQualitative:
    def test_case_insensitive_match(self) -> None:
        res = evaluate_qualitative("POSITIVE", ["Positive", "Negative"])
        assert res.matched is True
        assert res.needs_review is False

    def test_whitespace_trimmed_match(self) -> None:
        res = evaluate_qualitative(" Positive ", ["Positive", "Negative"])
        assert res.matched is True
        assert res.needs_review is False

    def test_outside_set_needs_review(self) -> None:
        res = evaluate_qualitative("weird", ["Positive", "Negative"])
        assert res.matched is False
        assert res.needs_review is True

    def test_no_set_free_text(self) -> None:
        res = evaluate_qualitative("anything at all", None)
        assert res.needs_review is False

    def test_qualitative_flag_always_none(self) -> None:
        ev = evaluate_result(
            "Positive",
            range_row=_row(low=None, high=None),
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=["Positive", "Negative"],
        )
        assert ev.flag is None
        assert ev.needs_review is False
        assert ev.matched_range is True

    def test_qualitative_outside_set_needs_review(self) -> None:
        ev = evaluate_result(
            "Mystery",
            range_row=_row(low=None, high=None),
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=["Positive", "Negative"],
        )
        assert ev.flag is None
        assert ev.needs_review is True


# ---------------------------------------------------------------------------
# T-07: effective-date selection (collection date, never today)
# ---------------------------------------------------------------------------


class TestSelectRangeEffectiveDates:
    def test_selects_row_effective_at_collection(self) -> None:
        old = _row(effective_from=date(2026, 1, 1), effective_to=date(2026, 5, 31))
        new = _row(effective_from=date(2026, 6, 1), effective_to=None)
        assert (
            select_range(
                [old, new],
                patient_sex="M",
                age_in_days=100,
                collection_date=date(2026, 3, 1),
            )
            is old
        )
        assert (
            select_range(
                [old, new],
                patient_sex="M",
                age_in_days=100,
                collection_date=date(2026, 7, 1),
            )
            is new
        )

    def test_future_range_never_selected(self) -> None:
        future = _row(effective_from=date(2026, 12, 1))
        assert (
            select_range(
                [future],
                patient_sex="M",
                age_in_days=100,
                collection_date=date(2026, 6, 15),
            )
            is None
        )

    def test_collection_before_any_range(self) -> None:
        row = _row(effective_from=date(2026, 1, 1))
        assert (
            select_range(
                [row],
                patient_sex="M",
                age_in_days=100,
                collection_date=date(2025, 6, 15),
            )
            is None
        )

    def test_accepts_datetime_collection(self) -> None:
        row = _row()
        assert (
            select_range(
                [row],
                patient_sex="M",
                age_in_days=100,
                collection_date=datetime(2026, 6, 15, 10, 30),
            )
            is row
        )


# ---------------------------------------------------------------------------
# T-08: sex-specific beats B
# ---------------------------------------------------------------------------


class TestSelectRangeSex:
    def test_specific_beats_both(self) -> None:
        both = _row(sex="B")
        specific = _row(sex="M")
        assert (
            select_range(
                [both, specific],
                patient_sex="M",
                age_in_days=100,
                collection_date=date(2026, 6, 15),
            )
            is specific
        )

    def test_falls_back_to_b(self) -> None:
        male = _row(sex="M")
        both = _row(sex="B")
        assert (
            select_range(
                [male, both],
                patient_sex="F",
                age_in_days=100,
                collection_date=date(2026, 6, 15),
            )
            is both
        )

    def test_unknown_sex_only_b(self) -> None:
        male = _row(sex="M")
        both = _row(sex="B")
        assert (
            select_range(
                [male, both],
                patient_sex=None,
                age_in_days=100,
                collection_date=date(2026, 6, 15),
            )
            is both
        )


# ---------------------------------------------------------------------------
# T-09: age bands in days; NULL DOB -> catch-all only
# ---------------------------------------------------------------------------


class TestSelectRangeAge:
    def test_band_containment(self) -> None:
        child = _row(age_min_days=0, age_max_days=365)
        adult = _row(age_min_days=366, age_max_days=730)
        assert (
            select_range(
                [child, adult],
                patient_sex="M",
                age_in_days=400,
                collection_date=date(2026, 6, 15),
            )
            is adult
        )

    def test_boundaries_inclusive(self) -> None:
        band = _row(age_min_days=100, age_max_days=200)
        for age in (100, 200):
            assert (
                select_range(
                    [band],
                    patient_sex="M",
                    age_in_days=age,
                    collection_date=date(2026, 6, 15),
                )
                is band
            )

    def test_open_ended_band(self) -> None:
        band = _row(age_min_days=365, age_max_days=None)
        assert (
            select_range(
                [band],
                patient_sex="M",
                age_in_days=36500,
                collection_date=date(2026, 6, 15),
            )
            is band
        )

    def test_null_dob_matches_catch_all_only(self) -> None:
        catch_all = _row(age_min_days=0, age_max_days=None)
        banded = _row(age_min_days=0, age_max_days=365)
        assert (
            select_range(
                [catch_all, banded],
                patient_sex="M",
                age_in_days=None,
                collection_date=date(2026, 6, 15),
            )
            is catch_all
        )

    def test_null_dob_no_catch_all_returns_none(self) -> None:
        banded = _row(age_min_days=0, age_max_days=365)
        assert (
            select_range(
                [banded],
                patient_sex="M",
                age_in_days=None,
                collection_date=date(2026, 6, 15),
            )
            is None
        )


# ---------------------------------------------------------------------------
# T-10: no matched range -> NULL flag
# ---------------------------------------------------------------------------


class TestNoMatchedRange:
    def test_no_range_flag_null_needs_review(self) -> None:
        ev = evaluate_result(
            "5.0",
            range_row=None,
            patient_sex="M",
            age_in_days=100,
            collection_date=date(2026, 6, 15),
            qualitative_values=None,
        )
        assert ev.flag is None
        assert ev.needs_review is True
        assert ev.matched_range is False
        assert ev.value == Decimal("5.0")


# ---------------------------------------------------------------------------
# Delta
# ---------------------------------------------------------------------------


class TestComputeDelta:
    def test_absolute_and_percent(self) -> None:
        d = compute_delta(Decimal("10"), Decimal("8"))
        assert d is not None
        assert d.absolute == Decimal("2")
        assert d.percent == Decimal("25")

    def test_negative_delta(self) -> None:
        d = compute_delta(Decimal("6"), Decimal("8"))
        assert d is not None
        assert d.absolute == Decimal("-2")
        assert d.percent == Decimal("-25")

    def test_zero_previous_percent_none(self) -> None:
        d = compute_delta(Decimal("5"), Decimal("0"))
        assert d is not None
        assert d.absolute == Decimal("5")
        assert d.percent is None

    def test_missing_current_none(self) -> None:
        assert compute_delta(None, Decimal("8")) is None

    def test_missing_previous_none(self) -> None:
        assert compute_delta(Decimal("8"), None) is None

    def test_both_none(self) -> None:
        assert compute_delta(None, None) is None


# ---------------------------------------------------------------------------
# Module purity: no django/celery/http imports
# ---------------------------------------------------------------------------


class TestEnginePurity:
    def test_no_forbidden_imports(self) -> None:
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[2]
            / "apps"
            / "results"
            / "engine.py"
        )
        text = src.read_text(encoding="utf-8")
        for forbidden in (
            "import django",
            "from django",
            "import celery",
            "from celery",
            "import requests",
            "from requests",
        ):
            assert forbidden not in text, f"forbidden import found: {forbidden}"
