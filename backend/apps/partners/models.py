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


class ShareLedgerEntry(models.Model):
    """
    Immutable revenue-share ledger entry (Doc 02 §5.8, §6, §12; Doc 05 §6).
    - Append-only: created_at only, never updated_at or deleted_at.
    - No status column and no settlement_id column (OQ-22 resolved).
    - UNIQUE payment_id (uq_share_ledger_entry_payment_id) enforces 1 entry per payment.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    payment = models.ForeignKey(
        "billing.Payment",
        on_delete=models.PROTECT,
        related_name="share_ledger_entries",
        db_column="payment_id",
        db_index=False,
        null=False,
    )
    referral_partner = models.ForeignKey(
        "partners.ReferralPartner",
        on_delete=models.PROTECT,
        related_name="share_ledger_entries",
        db_column="referral_partner_id",
        db_index=False,
        null=False,
    )
    rule = models.ForeignKey(
        "partners.RevenueShareRule",
        on_delete=models.PROTECT,
        related_name="share_ledger_entries",
        db_column="rule_id",
        db_index=False,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
    )
    percent_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=False,
    )
    basis_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
    )
    period = models.TextField(null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True, null=False)

    class Meta:
        db_table = "share_ledger_entry"
        indexes = [
            models.Index(
                fields=["payment"],
                name="idx_share_ledger_entry_payment_id",
            ),
            models.Index(
                fields=["referral_partner"],
                name="idx_share_ledger_entry_referral_partner_id",
            ),
            models.Index(
                fields=["rule"],
                name="idx_share_ledger_entry_rule_id",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment"],
                name="uq_share_ledger_entry_payment_id",
            ),
            models.CheckConstraint(
                condition=Q(
                    percent_applied__gte=Decimal("0.00"),
                    percent_applied__lte=Decimal("100.00"),
                ),
                name="chk_share_ledger_entry_percent_0_100",
            ),
            models.CheckConstraint(
                condition=Q(period__regex=r"^\d{4}-\d{2}$"),
                name="chk_share_ledger_entry_period_format",
            ),
        ]

    def __str__(self) -> str:
        return f"ShareLedgerEntry {self.id} ({self.amount} PKR, {self.period})"


class Settlement(models.Model):
    """
    Monthly partner settlement statement (Doc 02 §5.8, Doc 05 §7).
    Partial UNIQUE on (referral_partner, period) WHERE status <> 'CANCELLED'.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        SENT = "SENT", "Sent"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    referral_partner = models.ForeignKey(
        "partners.ReferralPartner",
        on_delete=models.PROTECT,
        related_name="settlements",
        db_column="referral_partner_id",
        db_index=False,
        null=False,
    )
    period = models.TextField(null=False, blank=False)
    status = models.TextField(
        choices=Status.choices,
        default=Status.DRAFT,
        db_default=Status.DRAFT,
        null=False,
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        db_default=Decimal("0.00"),
        null=False,
    )
    statement_pdf_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    approved_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="approved_settlements",
        db_column="approved_by",
        db_index=False,
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "settlement"
        indexes = [
            models.Index(
                fields=["referral_partner"],
                name="idx_settlement_referral_partner_id",
            ),
            models.Index(
                fields=["approved_by"],
                name="idx_settlement_approved_by",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["referral_partner", "period"],
                condition=~Q(status="CANCELLED"),
                name="uq_settlement_partner_id_period",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "DRAFT",
                        "APPROVED",
                        "SENT",
                        "PAID",
                        "CANCELLED",
                    ]
                ),
                name="chk_settlement_status",
            ),
            models.CheckConstraint(
                condition=Q(period__regex=r"^\d{4}-\d{2}$"),
                name="chk_settlement_period_format",
            ),
        ]

    def __str__(self) -> str:
        return f"Settlement {self.id} ({self.period} - {self.status})"


class SettlementLine(models.Model):
    """
    Itemisation of a settlement: which ledger entries it includes
    (Doc 02 §5.8, Doc 05 §7.1). UNIQUE share_ledger_entry_id ensures an entry
    appears in at most one settlement line. created_at only — never updated_at.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    settlement = models.ForeignKey(
        "partners.Settlement",
        on_delete=models.PROTECT,
        related_name="lines",
        db_column="settlement_id",
        db_index=False,
        null=False,
    )
    share_ledger_entry = models.ForeignKey(
        "partners.ShareLedgerEntry",
        on_delete=models.PROTECT,
        related_name="settlement_lines",
        db_column="share_ledger_entry_id",
        db_index=False,
        null=False,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, null=False)

    class Meta:
        db_table = "settlement_line"
        indexes = [
            models.Index(
                fields=["settlement"],
                name="idx_settlement_line_settlement_id",
            ),
            models.Index(
                fields=["share_ledger_entry"],
                name="idx_settlement_line_share_ledger_entry_id",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["share_ledger_entry"],
                name="uq_settlement_line_share_ledger_entry_id",
            ),
        ]

    def __str__(self) -> str:
        return f"SettlementLine {self.id} ({self.amount} PKR)"
