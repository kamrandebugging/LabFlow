"""Business logic service for Diagnostic Catalog (Doc 03 §5.2, §6.3, KAN-118).

Handles:
- Test creation and update with audit logging.
- Panel creation, update, and component linking with audit logging.
- Effective-dated pricing with automatic closure of superseded price rows (CT-2).
- get_effective_price resolver raising TestNotPricedError (CT-3, T-16).
- Reference range CRUD with overlap rejection (CT-4, CT-V2, KAN-119).
- Deterministic reference range selection (Doc 03 §8.2, T-10, KAN-119).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import AuditLog, StaffUser
from apps.catalog.models import Panel, PanelTest, ReferenceRange, Test, TestPrice

# Sentinel for open-ended age bands / effective windows in comparisons.
_OPEN_AGE_MAX = 10**9


class TestNotPricedError(Exception):
    """Raised when no effective price exists for a test or panel (CT-3, T-16)."""

    __test__ = False

    def __init__(self, message: str = "Test or panel has no effective price.") -> None:
        super().__init__(message)


class OverlappingRangeError(Exception):
    """Raised when a range overlaps an existing range (CT-4, CT-V2, KAN-119)."""

    __test__ = False

    def __init__(
        self, message: str = "Reference range overlaps an existing range."
    ) -> None:
        super().__init__(message)


class RangeWindowError(ValueError):
    """Raised when a range's effective window is invalid (KAN-119)."""

    __test__ = False


def _sexes_overlap(a: str, b: str) -> bool:
    """Sex buckets overlap when either is B (Both) or they are equal."""
    return a == "B" or b == "B" or a == b


def _bands_overlap(
    a_min: int,
    a_max: int | None,
    b_min: int,
    b_max: int | None,
) -> bool:
    """Day-based age bands overlap (shared boundary day counts as overlap)."""
    hi = min(
        a_max if a_max is not None else _OPEN_AGE_MAX,
        b_max if b_max is not None else _OPEN_AGE_MAX,
    )
    return max(a_min, b_min) <= hi


def _windows_overlap(
    a_from: date,
    a_to: date | None,
    b_from: date,
    b_to: date | None,
) -> bool:
    """Effective date windows overlap (open-ended = runs forever)."""
    hi = min(
        a_to if a_to is not None else date.max, b_to if b_to is not None else date.max
    )
    return max(a_from, b_from) <= hi


def _range_snapshot(range_obj: ReferenceRange) -> dict[str, Any]:
    """JSON-safe snapshot of a reference range for audit before/after."""

    def _dec(value: Decimal | None) -> str | None:
        return f"{value:.3f}" if value is not None else None

    return {
        "id": str(range_obj.id),
        "test_id": str(range_obj.test_id),
        "sex": range_obj.sex,
        "age_min_days": range_obj.age_min_days,
        "age_max_days": range_obj.age_max_days,
        "low": _dec(range_obj.low),
        "high": _dec(range_obj.high),
        "critical_low": _dec(range_obj.critical_low),
        "critical_high": _dec(range_obj.critical_high),
        "unit": range_obj.unit,
        "effective_from": range_obj.effective_from.isoformat(),
        "effective_to": (
            range_obj.effective_to.isoformat()
            if range_obj.effective_to is not None
            else None
        ),
    }


def _validate_range_fields(
    *,
    sex: str,
    age_min_days: int,
    age_max_days: int | None,
    low: Decimal | None,
    high: Decimal | None,
    critical_low: Decimal | None,
    critical_high: Decimal | None,
    unit: str,
    effective_from: date,
    effective_to: date | None,
) -> None:
    """Shared field-level validation for range create / supersede (KAN-119)."""
    if sex not in ("M", "F", "B"):
        raise RangeWindowError(f"Invalid sex '{sex}': must be M, F or B.")
    if age_min_days < 0:
        raise RangeWindowError("age_min_days cannot be negative.")
    if age_max_days is not None and age_max_days < age_min_days:
        raise RangeWindowError("age_max_days cannot be less than age_min_days.")
    if low is not None and high is not None and low > high:
        raise RangeWindowError("low cannot be greater than high.")
    if (
        critical_low is not None
        and critical_high is not None
        and critical_low > critical_high
    ):
        raise RangeWindowError("critical_low cannot be greater than critical_high.")
    if not unit or not unit.strip():
        raise RangeWindowError("unit cannot be empty.")
    if effective_to is not None and effective_to < effective_from:
        raise RangeWindowError("effective_to cannot be before effective_from.")


def _assert_no_overlap(
    *,
    test_id: uuid.UUID,
    sex: str,
    age_min_days: int,
    age_max_days: int | None,
    effective_from: date,
    effective_to: date | None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """CT-4 / CT-V2: reject ranges overlapping an existing range (KAN-119)."""
    candidates = ReferenceRange.objects.filter(test_id=test_id)
    if exclude_id is not None:
        candidates = candidates.exclude(id=exclude_id)
    for existing in candidates:
        if (
            _sexes_overlap(sex, existing.sex)
            and _bands_overlap(
                age_min_days, age_max_days, existing.age_min_days, existing.age_max_days
            )
            and _windows_overlap(
                effective_from,
                effective_to,
                existing.effective_from,
                existing.effective_to,
            )
        ):
            raise OverlappingRangeError(
                f"Overlaps existing range {existing.id} "
                f"[{existing.sex} {existing.age_min_days}-"
                f"{existing.age_max_days or '*'}d "
                f"{existing.effective_from}..{existing.effective_to or '*'}]."
            )


class CatalogService:
    @staticmethod
    def create_test(
        *,
        code: str,
        name: str,
        category: str | None = None,
        unit: str | None = None,
        is_active: bool = True,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Test:
        with transaction.atomic():
            test_obj = Test.objects.create(
                code=code,
                name=name,
                category=category,
                unit=unit,
                is_active=is_active,
            )

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.test_created",
                entity_type="test",
                entity_id=test_obj.id,
                before_jsonb=None,
                after_jsonb={
                    "code": test_obj.code,
                    "name": test_obj.name,
                    "category": test_obj.category,
                    "unit": test_obj.unit,
                    "is_active": test_obj.is_active,
                },
                ip=ip,
                user_agent=user_agent,
            )
            return test_obj

    @staticmethod
    def update_test(
        *,
        test_obj: Test,
        data: dict[str, Any],
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Test:
        with transaction.atomic():
            before = {
                "name": test_obj.name,
                "category": test_obj.category,
                "unit": test_obj.unit,
                "is_active": test_obj.is_active,
            }

            if "name" in data:
                test_obj.name = data["name"]
            if "category" in data:
                test_obj.category = data["category"]
            if "unit" in data:
                test_obj.unit = data["unit"]
            if "is_active" in data:
                test_obj.is_active = data["is_active"]

            test_obj.save()

            after = {
                "name": test_obj.name,
                "category": test_obj.category,
                "unit": test_obj.unit,
                "is_active": test_obj.is_active,
            }

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.test_updated",
                entity_type="test",
                entity_id=test_obj.id,
                before_jsonb=before,
                after_jsonb=after,
                ip=ip,
                user_agent=user_agent,
            )
            return test_obj

    @staticmethod
    def create_panel(
        *,
        code: str,
        name: str,
        test_ids: list[uuid.UUID],
        is_active: bool = True,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Panel:
        with transaction.atomic():
            panel = Panel.objects.create(
                code=code,
                name=name,
                is_active=is_active,
            )

            for t_id in test_ids:
                PanelTest.objects.create(panel=panel, test_id=t_id)

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.panel_created",
                entity_type="panel",
                entity_id=panel.id,
                before_jsonb=None,
                after_jsonb={
                    "code": panel.code,
                    "name": panel.name,
                    "is_active": panel.is_active,
                    "test_ids": [str(t) for t in test_ids],
                },
                ip=ip,
                user_agent=user_agent,
            )
            return panel

    @staticmethod
    def update_panel(
        *,
        panel: Panel,
        data: dict[str, Any],
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Panel:
        with transaction.atomic():
            before_test_ids = list(panel.panel_tests.values_list("test_id", flat=True))
            before = {
                "name": panel.name,
                "is_active": panel.is_active,
                "test_ids": [str(t) for t in before_test_ids],
            }

            if "name" in data:
                panel.name = data["name"]
            if "is_active" in data:
                panel.is_active = data["is_active"]
            panel.save()

            if "test_ids" in data:
                PanelTest.objects.filter(panel=panel).delete()
                for t_id in data["test_ids"]:
                    PanelTest.objects.create(panel=panel, test_id=t_id)

            after_test_ids = list(panel.panel_tests.values_list("test_id", flat=True))
            after = {
                "name": panel.name,
                "is_active": panel.is_active,
                "test_ids": [str(t) for t in after_test_ids],
            }

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.panel_updated",
                entity_type="panel",
                entity_id=panel.id,
                before_jsonb=before,
                after_jsonb=after,
                ip=ip,
                user_agent=user_agent,
            )
            return panel

    @staticmethod
    def set_price(
        *,
        amount: Decimal,
        effective_from: datetime | None = None,
        test_id: uuid.UUID | None = None,
        panel_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> TestPrice:
        if test_id is None and panel_id is None:
            raise ValueError("Either test_id or panel_id must be provided.")
        if test_id is not None and panel_id is not None:
            raise ValueError("Cannot specify both test_id and panel_id.")

        if effective_from is None:
            effective_from = timezone.now()

        target_id: uuid.UUID = (
            test_id if test_id is not None else cast(uuid.UUID, panel_id)
        )
        entity_type: str = "test" if test_id is not None else "panel"

        with transaction.atomic():
            # CT-2: Close any overlapping open price row
            qs = TestPrice.objects.all()
            if test_id is not None:
                qs = qs.filter(test_id=test_id)
            else:
                qs = qs.filter(panel_id=cast(uuid.UUID, panel_id))

            if branch_id is not None:
                qs = qs.filter(branch_id=branch_id)
            else:
                qs = qs.filter(branch_id__isnull=True)

            existing_prices = qs.filter(
                Q(effective_to__isnull=True) | Q(effective_to__gt=effective_from)
            )

            last_price = existing_prices.first()
            before_jsonb = {"amount": f"{last_price.price:.2f}"} if last_price else None

            for old_price in existing_prices:
                old_price.effective_to = effective_from
                old_price.save(update_fields=["effective_to", "updated_at"])

            new_price = TestPrice.objects.create(
                test_id=test_id,
                panel_id=panel_id,
                branch_id=branch_id,
                price=amount,
                effective_from=effective_from,
                effective_to=None,
            )

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.price_changed",
                entity_type=entity_type,
                entity_id=target_id,
                before_jsonb=before_jsonb,
                after_jsonb={
                    "amount": f"{amount:.2f}",
                    "effective_from": effective_from.isoformat(),
                    "branch_id": str(branch_id) if branch_id else None,
                    "price_id": str(new_price.id),
                },
                ip=ip,
                user_agent=user_agent,
            )
            return new_price

    @staticmethod
    def get_effective_price(
        *,
        test_id: uuid.UUID | None = None,
        panel_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        on_date: datetime | date | None = None,
    ) -> Decimal:
        """Finds effective price for test or panel on given date (CT-3, T-16)."""
        if test_id is None and panel_id is None:
            raise ValueError("Either test_id or panel_id must be provided.")

        if on_date is None:
            ref_dt = timezone.now()
        elif isinstance(on_date, datetime):
            ref_dt = on_date
        else:
            ref_dt = datetime.combine(on_date, datetime.max.time()).replace(tzinfo=UTC)

        # 1. Try branch-specific price if branch_id is supplied
        if branch_id is not None:
            b_qs = TestPrice.objects.filter(
                branch_id=branch_id, effective_from__lte=ref_dt
            )
            if test_id is not None:
                b_qs = b_qs.filter(test_id=test_id)
            else:
                b_qs = b_qs.filter(panel_id=cast(uuid.UUID, panel_id))

            branch_price = (
                b_qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=ref_dt))
                .order_by("-effective_from")
                .first()
            )
            if branch_price is not None:
                return branch_price.price

        # 2. Try tenant-wide price (branch_id IS NULL)
        t_qs = TestPrice.objects.filter(
            branch_id__isnull=True, effective_from__lte=ref_dt
        )
        if test_id is not None:
            t_qs = t_qs.filter(test_id=test_id)
        else:
            t_qs = t_qs.filter(panel_id=cast(uuid.UUID, panel_id))

        tenant_price = (
            t_qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=ref_dt))
            .order_by("-effective_from")
            .first()
        )
        if tenant_price is not None:
            return tenant_price.price

        raise TestNotPricedError(
            f"No effective price configured for entity "
            f"(test={test_id}, panel={panel_id}, branch={branch_id}) on {ref_dt}."
        )

    @staticmethod
    def create_reference_range(
        *,
        test_id: uuid.UUID,
        sex: str,
        age_min_days: int,
        age_max_days: int | None = None,
        low: Decimal | None = None,
        high: Decimal | None = None,
        critical_low: Decimal | None = None,
        critical_high: Decimal | None = None,
        unit: str,
        effective_from: date,
        effective_to: date | None = None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> ReferenceRange:
        """Create a reference range with overlap rejection (CT-4, CT-V2, KAN-119)."""
        _validate_range_fields(
            sex=sex,
            age_min_days=age_min_days,
            age_max_days=age_max_days,
            low=low,
            high=high,
            critical_low=critical_low,
            critical_high=critical_high,
            unit=unit,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        _assert_no_overlap(
            test_id=test_id,
            sex=sex,
            age_min_days=age_min_days,
            age_max_days=age_max_days,
            effective_from=effective_from,
            effective_to=effective_to,
        )

        with transaction.atomic():
            range_obj = ReferenceRange.objects.create(
                test_id=test_id,
                sex=sex,
                age_min_days=age_min_days,
                age_max_days=age_max_days,
                low=low,
                high=high,
                critical_low=critical_low,
                critical_high=critical_high,
                unit=unit.strip(),
                effective_from=effective_from,
                effective_to=effective_to,
            )

            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.range_created",
                entity_type="reference_range",
                entity_id=range_obj.id,
                before_jsonb=None,
                after_jsonb=_range_snapshot(range_obj),
                ip=ip,
                user_agent=user_agent,
            )
            return range_obj

    @staticmethod
    def supersede_reference_range(
        *,
        range_obj: ReferenceRange,
        data: dict[str, Any],
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> ReferenceRange:
        """Supersede a range: close the old row, open a new one (Doc 03 §5.2).

        History is preserved — the old row is never deleted or mutated apart
        from its effective_to closure date. A payload containing only
        effective_to retires the row without a successor.
        """
        with transaction.atomic():
            before = _range_snapshot(range_obj)

            # Pure retirement: only effective_to supplied.
            if set(data.keys()) == {"effective_to"}:
                new_to = data["effective_to"]
                if new_to is not None and new_to < range_obj.effective_from:
                    raise RangeWindowError(
                        "effective_to cannot be before effective_from."
                    )
                range_obj.effective_to = new_to
                range_obj.save(update_fields=["effective_to", "updated_at"])
                AuditLog.objects.create(
                    actor_id=actor.id,
                    action="catalog.range_updated",
                    entity_type="reference_range",
                    entity_id=range_obj.id,
                    before_jsonb=before,
                    after_jsonb=_range_snapshot(range_obj),
                    ip=ip,
                    user_agent=user_agent,
                )
                return range_obj

            new_from = data.get("effective_from", timezone.localdate())
            if not isinstance(new_from, date):
                raise RangeWindowError("effective_from must be a date.")
            if new_from < range_obj.effective_from:
                raise RangeWindowError(
                    "New effective_from cannot precede the row's effective_from; "
                    "history cannot be rewritten."
                )

            merged: dict[str, Any] = {
                "sex": data.get("sex", range_obj.sex),
                "age_min_days": data.get("age_min_days", range_obj.age_min_days),
                "age_max_days": data.get("age_max_days", range_obj.age_max_days),
                "low": data.get("low", range_obj.low),
                "high": data.get("high", range_obj.high),
                "critical_low": data.get("critical_low", range_obj.critical_low),
                "critical_high": data.get("critical_high", range_obj.critical_high),
                "unit": data.get("unit", range_obj.unit),
                "effective_from": new_from,
                "effective_to": data.get("effective_to"),
            }
            _validate_range_fields(
                sex=merged["sex"],
                age_min_days=merged["age_min_days"],
                age_max_days=merged["age_max_days"],
                low=merged["low"],
                high=merged["high"],
                critical_low=merged["critical_low"],
                critical_high=merged["critical_high"],
                unit=merged["unit"],
                effective_from=merged["effective_from"],
                effective_to=merged["effective_to"],
            )

            # Close the old row the day before the successor starts.
            range_obj.effective_to = max(
                new_from - timedelta(days=1), range_obj.effective_from
            )
            range_obj.save(update_fields=["effective_to", "updated_at"])

            _assert_no_overlap(
                test_id=range_obj.test_id,
                sex=merged["sex"],
                age_min_days=merged["age_min_days"],
                age_max_days=merged["age_max_days"],
                effective_from=merged["effective_from"],
                effective_to=merged["effective_to"],
                exclude_id=range_obj.id,
            )

            new_range = ReferenceRange.objects.create(
                test_id=range_obj.test_id,
                sex=merged["sex"],
                age_min_days=merged["age_min_days"],
                age_max_days=merged["age_max_days"],
                low=merged["low"],
                high=merged["high"],
                critical_low=merged["critical_low"],
                critical_high=merged["critical_high"],
                unit=str(merged["unit"]).strip(),
                effective_from=merged["effective_from"],
                effective_to=merged["effective_to"],
            )

            after = _range_snapshot(new_range)
            after["supersedes"] = str(range_obj.id)
            AuditLog.objects.create(
                actor_id=actor.id,
                action="catalog.range_updated",
                entity_type="reference_range",
                entity_id=new_range.id,
                before_jsonb=before,
                after_jsonb=after,
                ip=ip,
                user_agent=user_agent,
            )
            return new_range

    @staticmethod
    def resolve_reference_range(
        *,
        test_id: uuid.UUID,
        patient_sex: str | None,
        patient_age_days: int | None,
        collection_date: date | datetime,
    ) -> ReferenceRange | None:
        """Deterministic range selection (Doc 03 §8.2, T-10, KAN-119).

        T-10: a range effective after the collection date is never selected.
        Tie-breaks: specific sex (M/F) beats B; narrower age band beats wider;
        latest effective_from, then latest created row, wins any residual tie
        (fully deterministic).
        """
        as_of = (
            collection_date.date()
            if isinstance(collection_date, datetime)
            else collection_date
        )

        candidates = ReferenceRange.objects.filter(
            test_id=test_id,
            effective_from__lte=as_of,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=as_of),
        )

        if patient_sex in ("M", "F"):
            candidates = candidates.filter(
                Q(sex="B") | Q(sex=patient_sex),
            )
        else:
            # Unknown sex degrades explicitly: only Both-buckets match.
            candidates = candidates.filter(sex="B")

        if patient_age_days is not None:
            candidates = candidates.filter(
                age_min_days__lte=patient_age_days,
            ).filter(
                Q(age_max_days__isnull=True) | Q(age_max_days__gte=patient_age_days),
            )

        def _sort_key(row: ReferenceRange) -> tuple[int, int, float, float, str]:
            sex_rank = 0 if row.sex in ("M", "F") else 1
            width = (
                row.age_max_days if row.age_max_days is not None else _OPEN_AGE_MAX
            ) - row.age_min_days
            return (
                sex_rank,
                width,
                -row.effective_from.toordinal(),
                -row.created_at.timestamp(),
                str(row.id),
            )

        ordered = sorted(candidates, key=_sort_key)
        return ordered[0] if ordered else None
