"""Business logic service for Diagnostic Catalog (Doc 03 §5.2, §6.3, KAN-118).

Handles:
- Test creation and update with audit logging.
- Panel creation, update, and component linking with audit logging.
- Effective-dated pricing with automatic closure of superseded price rows (CT-2).
- get_effective_price resolver raising TestNotPricedError (CT-3, T-16).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import AuditLog, StaffUser
from apps.catalog.models import Panel, PanelTest, Test, TestPrice


class TestNotPricedError(Exception):
    """Raised when no effective price exists for a test or panel (CT-3, T-16)."""

    __test__ = False

    def __init__(self, message: str = "Test or panel has no effective price.") -> None:
        super().__init__(message)


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
