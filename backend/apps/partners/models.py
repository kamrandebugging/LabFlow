from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class ReferralPartner(models.Model):
    """
    Referring doctor or facility (Doc 02 §5.8, Doc 05 §5.1).
    Record only — no login in v1. Soft-deletable via deleted_at.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.TextField(null=False, blank=False)
    organisation = models.TextField(null=True, blank=True)  # noqa: DJ001
    phone = models.TextField(null=True, blank=True)  # noqa: DJ001
    email = models.TextField(null=True, blank=True)  # noqa: DJ001
    is_active = models.BooleanField(
        default=True,
        db_default=True,
        null=False,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "referral_partner"

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class RevenueShareRule(models.Model):
    """
    Effective-dated revenue-share percentage rule per partner, optional test category,
    and optional branch (Doc 02 §5.8, Doc 05 §5.2).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    referral_partner = models.ForeignKey(
        "partners.ReferralPartner",
        on_delete=models.PROTECT,
        related_name="revenue_share_rules",
        db_column="referral_partner_id",
        db_index=False,
        null=False,
    )
    test_category = models.TextField(null=True, blank=True)  # noqa: DJ001
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="revenue_share_rules",
        db_column="branch_id",
        db_index=False,
        null=True,
        blank=True,
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=False,
    )
    effective_from = models.DateField(null=False)
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "revenue_share_rule"
        indexes = [
            models.Index(
                fields=["referral_partner"],
                name="idx_revenue_share_rule_referral_partner_id",
            ),
            models.Index(
                fields=["branch"],
                name="idx_revenue_share_rule_branch_id",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    percent__gte=Decimal("0.00"),
                    percent__lte=Decimal("100.00"),
                ),
                name="chk_revenue_share_rule_percent_0_100",
            ),
        ]

    def __str__(self) -> str:
        return f"Rule {self.id} ({self.percent}%)"
