"""LAB-24 (KAN-144): pure result-calculation engine (Doc 03 §8).

PURE MODULE — depends on NOTHING outside the standard library (no web
framework, task queue, or HTTP client imports). Only ``decimal``,
``datetime``, ``re``, ``dataclasses``, ``enum`` and ``typing``.

Big-O notes (per ticket, for the PR):
- ``parse_result``: O(n) in the input length (single strip/scan + one regex).
- ``compute_flag``: O(1).
- ``select_range``: O(n) filter + O(n log n) sort; n = rows for one test
  (dozens in practice; the DB boundary pre-filters by test).
- ``evaluate_qualitative``: O(m) where m = size of the expected set.
- ``compute_delta``: O(1).
- ``evaluate_result``: O(1) beyond the single ``parse_result`` call.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

# Qualifiers recognised at the head of a raw result, longest first so that
# "<=" wins over "<". Unicode ≤ / ≥ are accepted per Doc 03 §8.1.
_QUALIFIERS: tuple[str, ...] = ("<=", ">=", "≤", "≥", "<", ">")

# Strict numeric body after qualifier extraction and comma/space removal.
# Allows an optional sign and a single decimal point; rejects scientific
# notation, NaN/Infinity, underscores and anything else Decimal() would
# otherwise accept.
_NUMERIC_BODY_RE: re.Pattern[str] = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")

# Width used for open-ended age bands in tie-breaks: larger than any real
# band, so bounded bands always win "narrower beats wider".
_OPEN_AGE_WIDTH_DAYS: int = 10**9

# Longest plausible lab value (Decimal(10,3) ≈ 11 chars) with headroom.
# Rejects absurd inputs before Decimal construction (DoS guard).
_MAX_NUMERIC_BODY_LEN: int = 32


class Flag(Enum):
    """Result flag per Doc 03 §8.3. ``None`` (not a member) is the NULL outcome."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ParsedResult:
    """Outcome of :func:`parse_result`."""

    qualifier: str | None  # kept for display; the numeric part drives the flag
    value: Decimal | None  # None when the raw text carries no parseable number


@dataclass(frozen=True)
class RangeRow:
    """Plain-data reference-range row for :func:`select_range`.

    Deliberately NOT a Django model instance so the selection stays DB-free.
    The DB boundary (``CatalogService.resolve_reference_range``) converts
    model rows to this shape. ``test_id`` is carried for traceability only.
    ``created_at`` feeds the deterministic final tie-break.
    """

    sex: str  # "M" | "F" | "B"
    age_min_days: int
    age_max_days: int | None
    effective_from: date
    effective_to: date | None
    low: Decimal | None
    high: Decimal | None
    critical_low: Decimal | None
    critical_high: Decimal | None
    test_id: Any = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class QualitativeResult:
    """Outcome of :func:`evaluate_qualitative`. The flag is ALWAYS None."""

    normalized: str  # trimmed raw text
    matched: bool  # in the expected set (True when there is no set: free text)
    needs_review: bool


@dataclass(frozen=True)
class Delta:
    """Display-only delta between two approved numeric results (Doc 03 §8.6).

    Never changes the flag and never blocks approval.
    """

    absolute: Decimal
    percent: Decimal | None  # None when previous == 0 (undefined)


@dataclass(frozen=True)
class ResultEvaluation:
    """Outcome of :func:`evaluate_result`."""

    value: Decimal | None
    qualifier: str | None
    flag: Flag | None  # None = NULL outcome, displayed as "—", never "normal"
    needs_review: bool
    matched_range: bool


def parse_result(raw: str) -> ParsedResult:
    """Parse a raw result string per Doc 03 §8.1 / OQ-25.

    Trims whitespace, extracts an optional leading comparator as the
    qualifier (``<``, ``>``, ``<=``, ``>=``, ``≤``, ``≥``), strips inner
    spaces and comma thousands separators, then parses the body with
    :class:`Decimal`. Scientific notation is rejected. Anything without a
    parseable number yields ``value=None``.
    """
    text = raw.strip()
    qualifier: str | None = None
    for cand in _QUALIFIERS:
        if text.startswith(cand):
            qualifier = cand
            text = text[len(cand) :]
            break
    body = re.sub(r"\s+", "", text).replace(",", "")
    if not body or len(body) > _MAX_NUMERIC_BODY_LEN:
        return ParsedResult(qualifier=qualifier, value=None)
    if _NUMERIC_BODY_RE.match(body) is None:
        return ParsedResult(qualifier=qualifier, value=None)
    try:
        value = Decimal(body)
    except InvalidOperation:
        return ParsedResult(qualifier=qualifier, value=None)
    return ParsedResult(qualifier=qualifier, value=value)


def compute_flag(
    value: Decimal | None,
    low: Decimal | None,
    high: Decimal | None,
    critical_low: Decimal | None,
    critical_high: Decimal | None,
) -> Flag | None:
    """Flag a numeric value per Doc 03 §8.3.

    Bounds are INCLUSIVE (exactly on low/high → normal). A ``None`` bound is
    not checked. Critical overrides: strictly below ``critical_low`` or
    strictly above ``critical_high`` → critical. ``value=None`` → None
    (never guessed — P-9).
    """
    if value is None:
        return None
    if critical_low is not None and value < critical_low:
        return Flag.CRITICAL
    if critical_high is not None and value > critical_high:
        return Flag.CRITICAL
    if low is not None and value < low:
        return Flag.LOW
    if high is not None and value > high:
        return Flag.HIGH
    return Flag.NORMAL


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _band_width(row: RangeRow) -> int:
    upper = row.age_max_days if row.age_max_days is not None else _OPEN_AGE_WIDTH_DAYS
    return upper - row.age_min_days


def select_range(
    rows: Sequence[RangeRow],
    *,
    patient_sex: str | None,
    age_in_days: int | None,
    collection_date: date | datetime,
) -> RangeRow | None:
    """Select the applicable reference-range row per Doc 03 §8.2 (pure).

    The collection date is passed in — never ``today()``, never the entry
    date (range ageing, §8.2). Predicates:

    - effective: ``effective_from <= collection_date`` and
      (``effective_to`` is None or ``>= collection_date``);
    - sex: row sex equals the patient sex, or ``"B"`` (unknown sex degrades
      to ``"B"``-only);
    - age: band containment; NULL DOB (``age_in_days=None``) matches only a
      catch-all band (``age_min_days == 0`` and ``age_max_days is None``).

    Tie-break (deterministic): sex-specific beats ``"B"``; narrower age band
    beats wider; later ``effective_from`` wins; later ``created_at`` wins;
    residual ties keep input order (the DB boundary feeds id-ordered rows).
    CT-4 forbids overlaps, so beyond the sex tie-break the deeper rules only
    trigger on rows inserted outside the API.
    """
    as_of = _as_date(collection_date)

    def _matches(row: RangeRow) -> bool:
        if row.effective_from > as_of:
            return False
        if row.effective_to is not None and row.effective_to < as_of:
            return False
        if not (row.sex == patient_sex or row.sex == "B"):
            return False
        if age_in_days is None:
            return row.age_min_days == 0 and row.age_max_days is None
        if row.age_min_days > age_in_days:
            return False
        return not (row.age_max_days is not None and age_in_days > row.age_max_days)

    def _sort_key(row: RangeRow) -> tuple[int, int, int, float]:
        sex_rank = 0 if row.sex in ("M", "F") else 1
        created_ts = row.created_at.timestamp() if row.created_at is not None else 0.0
        return (
            sex_rank,
            _band_width(row),
            -row.effective_from.toordinal(),
            -created_ts,
        )

    candidates = [row for row in rows if _matches(row)]
    candidates.sort(key=_sort_key)  # stable: input order breaks residual ties
    return candidates[0] if candidates else None


def evaluate_qualitative(
    value: str, expected_set: list[str] | None
) -> QualitativeResult:
    """Evaluate a qualitative result per Doc 03 §8.4.

    The flag is ALWAYS None for qualitative results. Matching is trimmed and
    case-insensitive. A value outside the set is still accepted but flagged
    ``needs_review=True``. With no set, free text is accepted without review.
    """
    normalized = value.strip()
    if expected_set is None:
        return QualitativeResult(
            normalized=normalized, matched=True, needs_review=False
        )
    lowered = normalized.casefold()
    matched = any(option.strip().casefold() == lowered for option in expected_set)
    return QualitativeResult(
        normalized=normalized, matched=matched, needs_review=not matched
    )


def compute_delta(current: Decimal | None, previous: Decimal | None) -> Delta | None:
    """Delta between two approved numeric results per Doc 03 §8.6.

    Either side ``None`` (qualitative / missing) → ``None``. ``percent`` is
    ``None`` when ``previous == 0`` (undefined). Display-only: never changes
    the flag, never blocks approval. (Looking up "the previous approved
    result for the same test" is a later LAB's job — this takes the values.)
    """
    if current is None or previous is None:
        return None
    absolute = current - previous
    percent = None if previous == 0 else (absolute / abs(previous) * 100)
    return Delta(absolute=absolute, percent=percent)


def evaluate_result(
    raw: str,
    *,
    range_row: RangeRow | None,
    patient_sex: str | None,
    age_in_days: int | None,
    collection_date: date | datetime,
    qualitative_values: list[str] | None,
) -> ResultEvaluation:
    """Orchestrate §8.1: parse → flag → review decision.

    Kind is picked from the matched row: ``low``/``high`` both NOT NULL →
    numeric, else qualitative. With no matched row, a numeric-looking raw is
    evaluated with flag NULL; otherwise qualitative free text. ``needs_review``
    when the numeric parse failed, the qualitative value is outside its set,
    or no range matched. (``patient_sex`` / ``age_in_days`` /
    ``collection_date`` are accepted for API stability — kind and flag derive
    from the pre-selected ``range_row``.)
    """
    matched = range_row is not None
    numeric_kind = (
        range_row is not None
        and range_row.low is not None
        and range_row.high is not None
    )

    if numeric_kind or not matched:
        parsed = parse_result(raw)
        if parsed.value is not None:
            flag: Flag | None = None
            if numeric_kind:
                assert range_row is not None  # guaranteed by numeric_kind
                flag = compute_flag(
                    parsed.value,
                    range_row.low,
                    range_row.high,
                    range_row.critical_low,
                    range_row.critical_high,
                )
            return ResultEvaluation(
                value=parsed.value,
                qualifier=parsed.qualifier,
                flag=flag,
                needs_review=not matched,
                matched_range=matched,
            )
        if not matched:
            # Not numeric and no row to define the kind: qualitative free text,
            # but always reviewed since the kind is unknown.
            evaluate_qualitative(raw, qualitative_values)
            return ResultEvaluation(
                value=None,
                qualifier=parsed.qualifier,
                flag=None,
                needs_review=True,
                matched_range=False,
            )
        return ResultEvaluation(
            value=None,
            qualifier=parsed.qualifier,
            flag=None,
            needs_review=True,
            matched_range=True,
        )

    qualitative = evaluate_qualitative(raw, qualitative_values)
    return ResultEvaluation(
        value=None,
        qualifier=None,
        flag=None,
        needs_review=qualitative.needs_review or not matched,
        matched_range=matched,
    )
