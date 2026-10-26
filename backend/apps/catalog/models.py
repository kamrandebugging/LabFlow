import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class Test(models.Model):
    """One orderable laboratory test (Doc 02 §5.3).

    Retired via is_active=False; never soft-deleted.
    """

    __test__ = False

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    code = models.TextField()
    name = models.TextField()
    category = models.TextField(null=True, blank=True)  # noqa: DJ001
    unit = models.TextField(null=True, blank=True)  # noqa: DJ001
    is_active = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "test"
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                name="uq_test_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Panel(models.Model):
    """A named group of tests, e.g. CBC, LFT (Doc 02 §5.3).

    Retired via is_active=False; never soft-deleted.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    code = models.TextField()
    name = models.TextField()
    is_active = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "panel"
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                name="uq_panel_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class PanelTest(models.Model):
    """Pure join table linking a panel to its component tests (Doc 02 §5.3, §17).

    Composite primary key (panel_id, test_id) with ON DELETE CASCADE.
    """

    pk = models.CompositePrimaryKey("panel_id", "test_id")
    panel = models.ForeignKey(
        "catalog.Panel",
        on_delete=models.CASCADE,
        related_name="panel_tests",
        db_column="panel_id",
        db_index=False,
    )
    test = models.ForeignKey(
        "catalog.Test",
        on_delete=models.CASCADE,
        related_name="panel_memberships",
        db_column="test_id",
        db_index=False,
    )

    class Meta:
        db_table = "panel_test"
        indexes = [
            models.Index(
                fields=["panel"],
                name="idx_panel_test_panel_id",
            ),
            models.Index(
                fields=["test"],
                name="idx_panel_test_test_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Panel({self.panel_id}) -> Test({self.test_id})"


class TestPrice(models.Model):
    """Effective-dated price of a test XOR panel at a branch or tenant-wide
    (Doc 02 §5.3).

    Money is numeric(12,2) in PKR (Doc 01 ADR-010).
    """

    __test__ = False

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="test_prices",
        db_column="branch_id",
        db_index=False,
    )
    test = models.ForeignKey(
        "catalog.Test",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prices",
        db_column="test_id",
        db_index=False,
    )
    panel = models.ForeignKey(
        "catalog.Panel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prices",
        db_column="panel_id",
        db_index=False,
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "test_price"
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=Decimal("0.00")),
                name="chk_test_price_price_non_neg",
            ),
            models.CheckConstraint(
                condition=(
                    Q(test__isnull=False, panel__isnull=True)
                    | Q(test__isnull=True, panel__isnull=False)
                ),
                name="chk_test_price_test_xor_panel",
            ),
        ]
        indexes = [
            models.Index(
                fields=["branch"],
                name="idx_test_price_branch_id",
            ),
            models.Index(
                fields=["test"],
                name="idx_test_price_test_id",
            ),
            models.Index(
                fields=["panel"],
                name="idx_test_price_panel_id",
            ),
        ]

    def __str__(self) -> str:
        target = f"Test({self.test_id})" if self.test_id else f"Panel({self.panel_id})"
        return f"{target} @ PKR {self.price}"
