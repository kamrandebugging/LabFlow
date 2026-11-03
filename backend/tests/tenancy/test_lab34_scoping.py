"""LAB-34 / KAN-159 — Branch scoping & RBAC (Doc 04 §8.4, §8.5, §18).

Part 1 (LAB-45): staff_branch assignment API + BranchScopedQuerySet /
BranchScopedManager / IsInBranchScope, wired into the key list endpoints.
Part 2 (LAB-54) isolation generator tests live in
tests/isolation/test_cross_tenant_isolation.py and test_lab34_isolation.py.

TN mapping:
- TN-19: generated scope matrix (role x assignment x list endpoint).
- TN-20: structural test — a viewset skipping the base class fails the suite.
- TN-21: zero-assignment account — lists empty, writes 403 branch_scope_denied;
  assignments for a tenant-wide role -> 422 tenant_wide_role.
- TN-24: BS-4 identifiers-only search returns exactly the identifier fields.
- TN-27: transfer scope — destination sees the open transfer while the sample
  is 404 in its scope; after receipt, scope moves.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.services import BillingService
from apps.patients.models import Patient
from apps.samples.models import Sample
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

PATIENTS_URL = "/api/v1/patients"
INVOICES_URL = "/api/v1/invoices"
STAFF_BRANCHES_URL = "/api/v1/staff/{staff_id}/branches"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def lab34_setup(tenant_a: Any) -> dict[str, Any]:
    """Two branches, one row per branch per scoped model, full role roster."""
    with tenant_context(tenant_a):
        branch_a = BranchFactory(code="BR1", name="Branch One")
        branch_b = BranchFactory(code="BR2", name="Branch Two")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="l34_owner@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch_a, email="l34_path@labflow.app"
        )
        manager_a = StaffUserFactory(
            role=Role.MANAGER, branch=branch_a, email="l34_mgra@labflow.app"
        )
        StaffBranch.objects.create(
            staff_user=manager_a, branch=branch_a, is_primary=True
        )
        reception_a = StaffUserFactory(
            role=Role.RECEPTION, branch=branch_a, email="l34_recpa@labflow.app"
        )
        StaffBranch.objects.create(
            staff_user=reception_a, branch=branch_a, is_primary=True
        )
        tech_a = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch_a, email="l34_tcha@labflow.app"
        )
        StaffBranch.objects.create(staff_user=tech_a, branch=branch_a, is_primary=True)
        manager_b = StaffUserFactory(
            role=Role.MANAGER, branch=branch_b, email="l34_mgrb@labflow.app"
        )
        StaffBranch.objects.create(
            staff_user=manager_b, branch=branch_b, is_primary=True
        )
        # SB-1 violation by construction: a branch-scoped account with zero
        # assignments (TN-21 probe).
        zero_manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch_a, email="l34_zero@labflow.app"
        )

        patient_a = PatientFactory(
            branch=branch_a, name="Scope Matrix Alpha", mrn="MRN-BR1-000101"
        )
        patient_b = PatientFactory(
            branch=branch_b, name="Scope Matrix Beta", mrn="MRN-BR2-000202"
        )

        test = TestFactory(name="CBC Test", code="CBC034")
        TestPriceFactory(test=test, panel=None, price=Decimal("1500.00"))
        invoice_a = _make_invoice_via_service(branch_a, patient_a, test, manager_a)
        invoice_b = _make_invoice_via_service(branch_b, patient_b, test, manager_b)

        sample_a = SampleFactory(branch=branch_a, invoice=invoice_a)
        sample_b = SampleFactory(branch=branch_b, invoice=invoice_b)

        return {
            "tenant": tenant_a,
            "branch_a": branch_a,
            "branch_b": branch_b,
            "owner": owner,
            "pathologist": pathologist,
            "manager_a": manager_a,
            "reception_a": reception_a,
            "tech_a": tech_a,
            "manager_b": manager_b,
            "zero_manager": zero_manager,
            "patient_a": patient_a,
            "patient_b": patient_b,
            "invoice_a": invoice_a,
            "invoice_b": invoice_b,
            "sample_a": sample_a,
            "sample_b": sample_b,
            "test": test,
        }


def _make_invoice_via_service(branch: Any, patient: Any, test: Any, actor: Any) -> Any:
    invoice, _ = BillingService.create_invoice(
        patient_id=patient.id,
        branch_id=branch.id,
        referral_partner_id=None,
        items=[{"test_id": test.id, "qty": 1}],
        discount_amount=Decimal("0.00"),
        discount_reason=None,
        idempotency_key=f"lab34-{uuid.uuid4()}",
        actor=actor,
    )
    return invoice


def _list_patients(client: Client, headers: dict[str, str], qs: str = "") -> Any:
    return client.get(f"{PATIENTS_URL}{qs}", headers=headers)


def _list_invoices(client: Client, headers: dict[str, str], qs: str = "") -> Any:
    return client.get(f"{INVOICES_URL}{qs}", headers=headers)


def _patient_branch_codes(resp: Any) -> set[str]:
    from apps.branches.models import Branch

    data = resp.json()
    rows = data if isinstance(data, list) else data.get("results", [])
    branch_ids = {r["branch_id"] for r in rows}
    code_by_id = {
        str(b.id): b.code for b in Branch.objects.filter(pk__in=list(branch_ids))
    }
    return {code_by_id[bid] for bid in branch_ids}


# ---------------------------------------------------------------------------
# TN-19 — generated scope matrix
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTN19ScopeMatrix:
    """Role x assignment matrix over the key list endpoints (Doc 04 §8.5)."""

    MATRIX = [
        # (user_key, endpoint, expected_branch_codes)
        ("owner", "patients", {"BR1", "BR2"}),  # BS-1 tenant-wide
        ("pathologist", "patients", {"BR1", "BR2"}),  # BS-1 tenant-wide
        ("manager_a", "patients", {"BR1"}),
        ("reception_a", "patients", {"BR1"}),
        ("tech_a", "patients", {"BR1"}),
        ("manager_b", "patients", {"BR2"}),
        ("zero_manager", "patients", set()),  # BS-2: lists empty
        ("owner", "invoices", {"BR1", "BR2"}),
        ("pathologist", "invoices", {"BR1", "BR2"}),
        ("manager_a", "invoices", {"BR1"}),
        ("manager_b", "invoices", {"BR2"}),
        ("zero_manager", "invoices", set()),
    ]

    @pytest.mark.parametrize(
        "user_key,endpoint,expected",
        MATRIX,
        ids=[f"{u}-{e}" for u, e, _ in MATRIX],
    )
    def test_scope_matrix(
        self,
        tenant_a: Any,
        lab34_setup: dict[str, Any],
        auth_headers: Any,
        user_key: str,
        endpoint: str,
        expected: set[str],
    ) -> None:
        with tenant_context(tenant_a):
            user = lab34_setup[user_key]
            headers = auth_headers(user)
            if endpoint == "patients":
                resp = _list_patients(Client(), headers)
            else:
                resp = _list_invoices(Client(), headers)
            assert resp.status_code == 200
            assert _patient_branch_codes(resp) == expected

    def test_branch_id_filter_out_of_scope_returns_empty(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """A scoped caller filtering to a branch outside its assignments sees []."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            branch_b_id = lab34_setup["branch_b"].id
            resp = _list_patients(Client(), headers, f"?branch_id={branch_b_id}")
            assert resp.status_code == 200
            assert resp.json() == []


# ---------------------------------------------------------------------------
# TN-20 — structural guard: viewsets must inherit the Layer-2 base class
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTN20StructuralGuard:
    def test_scoped_list_views_inherit_base_class(self) -> None:
        """Every scoped list view inherits BranchScopedAPIView (Doc 04 §8.5 L2)."""
        from apps.branches.scope_views import (
            BranchScopedAPIView,
            assert_branch_scope_conformance,
            get_branch_scoped_list_views,
        )

        views = get_branch_scoped_list_views()
        assert len(views) >= 2
        for view_cls in views:
            assert issubclass(view_cls, BranchScopedAPIView), (
                f"{view_cls.__name__} must inherit BranchScopedAPIView"
            )
        # The conformance checker passes for the registered set.
        assert_branch_scope_conformance(views)

    def test_dummy_viewset_without_base_class_fails(self) -> None:
        """A viewset skipping the base class fails the structural guard."""
        import pytest as _pytest
        from rest_framework.views import APIView

        from apps.branches.scope_views import assert_branch_scope_conformance

        class DummyScopedView(APIView):
            """Deliberately skips BranchScopedAPIView."""

        with _pytest.raises(AssertionError, match="DummyScopedView"):
            assert_branch_scope_conformance([DummyScopedView])


# ---------------------------------------------------------------------------
# TN-21 — zero-assignment account behaviour
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTN21ZeroAssignment:
    def test_zero_assignment_patient_write_403_branch_scope_denied(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["zero_manager"])
            body = {
                "name": "No Scope Patient",
                "phone": "03009998877",
                "sex": "male",
                "branch_id": str(lab34_setup["branch_a"].id),
            }
            resp = Client().post(
                PATIENTS_URL,
                data=json.dumps(body),
                content_type="application/json",
                headers=headers,
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "branch_scope_denied"

    def test_zero_assignment_invoice_write_403_branch_scope_denied(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["zero_manager"])
            body = {
                "patient_id": str(setup["patient_a"].id),
                "branch_id": str(setup["branch_a"].id),
                "items": [{"test_id": str(setup["test"].id), "qty": 1}],
                "discount_amount": "0.00",
            }
            resp = Client().post(
                INVOICES_URL,
                data=json.dumps(body),
                content_type="application/json",
                headers={**headers, "Idempotency-Key": f"lab34-{uuid.uuid4()}"},
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "branch_scope_denied"

    def test_zero_assignment_payment_write_403_branch_scope_denied(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["zero_manager"])
            body = {
                "kind": "payment",
                "method": "cash",
                "amount": "100.00",
            }
            resp = Client().post(
                f"{INVOICES_URL}/{setup['invoice_a'].id}/payments",
                data=json.dumps(body),
                content_type="application/json",
                headers={**headers, "Idempotency-Key": f"lab34-{uuid.uuid4()}"},
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "branch_scope_denied"

    def test_out_of_scope_branch_write_403_branch_scope_denied(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Layer 3: a write naming a branch outside the caller's assignments
        is refused with 403 branch_scope_denied (not a misleading 404)."""
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["manager_a"])
            body = {
                "patient_id": str(setup["patient_b"].id),
                "branch_id": str(setup["branch_b"].id),
                "items": [{"test_id": str(setup["test"].id), "qty": 1}],
                "discount_amount": "0.00",
            }
            resp = Client().post(
                INVOICES_URL,
                data=json.dumps(body),
                content_type="application/json",
                headers={**headers, "Idempotency-Key": f"lab34-{uuid.uuid4()}"},
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "branch_scope_denied"

    def test_assignments_for_tenant_wide_role_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-2: owner/pathologist take no assignments (TN-21)."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            for target_key in ("owner", "pathologist"):
                target = lab34_setup[target_key]
                url = STAFF_BRANCHES_URL.format(staff_id=target.id)
                resp = Client().put(
                    url,
                    data=json.dumps(
                        [
                            {
                                "branch_id": str(lab34_setup["branch_a"].id),
                                "is_primary": True,
                            }
                        ]
                    ),
                    content_type="application/json",
                    headers=headers,
                )
                assert resp.status_code == 422, target_key
                assert resp.json()["error"]["code"] == "tenant_wide_role"


# ---------------------------------------------------------------------------
# TN-24 — BS-4 identifiers-only cross-branch search
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTN24IdentifiersOnlySearch:
    def test_cross_branch_search_returns_identifiers_only(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            resp = _list_patients(Client(), headers, "?q=Scope Matrix Beta")
            assert resp.status_code == 200
            rows = resp.json()
            assert isinstance(rows, list) and len(rows) >= 1
            hit = next(r for r in rows if r["mrn"] == "MRN-BR2-000202")
            assert hit["is_cross_branch"] is True
            # Exactly the BS-4 identifier fields are populated …
            assert hit["name"] == "Scope Matrix Beta"
            assert hit["mrn"] == "MRN-BR2-000202"
            assert hit["sex"] == "M"
            assert hit["year_of_birth"] == 1990
            # … everything sensitive is redacted.
            assert hit["phone"] is None
            assert hit["date_of_birth"] is None
            assert hit["created_at"] is None
            assert hit["updated_at"] is None


# ---------------------------------------------------------------------------
# TN-27 — transfer scope moves on receipt
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTN27TransferScopeMoves:
    def test_sample_invisible_at_destination_until_receipt(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        from apps.samples.services import TransferService

        with tenant_context(tenant_a):
            setup = lab34_setup
            manager_a, manager_b = setup["manager_a"], setup["manager_b"]
            sample = setup["sample_a"]

            transfer = TransferService.create_transfer(
                sample_id=sample.id,
                to_branch_id=setup["branch_b"].id,
                actor=manager_a,
                ip="127.0.0.1",
                user_agent="lab34",
            )
            assert transfer.status == "open"

            # Destination sees the open transfer row (the expected arrival)…
            from apps.samples.models import SampleTransfer

            assert SampleTransfer.objects.filter(
                pk=transfer.pk, to_branch=setup["branch_b"]
            ).exists()
            # …while the sample itself is 404 in the destination scope.
            assert not Sample.objects.scoped_to(manager_b).filter(pk=sample.pk).exists()
            assert Sample.objects.scoped_to(manager_a).filter(pk=sample.pk).exists()

            received = TransferService.receive_transfer(
                transfer_id=transfer.pk,
                actor=manager_b,
                ip="127.0.0.1",
                user_agent="lab34",
            )
            assert received.status == "received"

            # Scope moved with the sample.
            assert Sample.objects.scoped_to(manager_b).filter(pk=sample.pk).exists()
            assert not Sample.objects.scoped_to(manager_a).filter(pk=sample.pk).exists()


# ---------------------------------------------------------------------------
# scoped_to unit behaviour (Doc 04 §8.5 Layer 1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestScopedTo:
    def test_tenant_wide_roles_unfiltered(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """BS-1: owner and pathologist see every branch (Doc 04 §8.5)."""
        with tenant_context(tenant_a):
            for user_key in ("owner", "pathologist"):
                user = lab34_setup[user_key]
                assert user.is_tenant_wide is True
                codes = {p.branch.code for p in Patient.objects.scoped_to(user).all()}
                assert codes == {"BR1", "BR2"}

    def test_scoped_user_sees_only_assigned_open_branches(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            manager_a = lab34_setup["manager_a"]
            assert manager_a.is_tenant_wide is False
            assert manager_a.assigned_branch_ids() == {lab34_setup["branch_a"].id}
            codes = {p.branch.code for p in Patient.objects.scoped_to(manager_a)}
            assert codes == {"BR1"}

    def test_closed_branch_grants_nothing(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """LAB-33 close revokes scope at once: closed branches are excluded."""
        from django.utils import timezone

        with tenant_context(tenant_a):
            branch_b = lab34_setup["branch_b"]
            branch_b.deleted_at = timezone.now()
            branch_b.save(update_fields=["deleted_at"])
            manager_b = lab34_setup["manager_b"]
            assert manager_b.assigned_branch_ids() == set()
            assert list(Patient.objects.scoped_to(manager_b)) == []
            # …but the owner still sees everything (BS-1).
            assert Patient.objects.scoped_to(lab34_setup["owner"]).count() == 2

    def test_zero_assignments_sees_nothing(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            zero = lab34_setup["zero_manager"]
            assert zero.assigned_branch_ids() == set()
            assert list(Patient.objects.scoped_to(zero)) == []

    def test_missing_scope_field_fails_loudly(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """A scoped model without branch_scope_field is a programming error."""
        from django.core.exceptions import ImproperlyConfigured

        from apps.branches.models import Branch

        with tenant_context(tenant_a), pytest.raises(ImproperlyConfigured):
            list(Branch.objects.scoped_to(lab34_setup["manager_a"]))

    def test_result_scopes_via_sample(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """Scope path sample__branch_id on Result (Doc 04 §8.5)."""
        from apps.results.models import Result
        from tests.factories.results import ResultFactory

        with tenant_context(tenant_a):
            ResultFactory(sample=lab34_setup["sample_a"])
            ResultFactory(sample=lab34_setup["sample_b"])
            manager_a = lab34_setup["manager_a"]
            samples = {r.sample_id for r in Result.objects.scoped_to(manager_a)}
            assert samples == {lab34_setup["sample_a"].id}

    def test_manager_scoped_queryset_chains(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """scoped_to composes with further filters (Layer-2 viewset use)."""
        with tenant_context(tenant_a):
            qs = Patient.objects.scoped_to(lab34_setup["manager_a"]).filter(
                deleted_at__isnull=True
            )
            assert {p.branch.code for p in qs} == {"BR1"}


# ---------------------------------------------------------------------------
# Part 1 — staff_branch assignment endpoints
# ---------------------------------------------------------------------------


def _branches_url(staff_id: uuid.UUID) -> str:
    return STAFF_BRANCHES_URL.format(staff_id=staff_id)


def _put_branches(
    client: Client, headers: dict[str, str], staff_id: uuid.UUID, body: Any
) -> Any:
    return client.put(
        _branches_url(staff_id),
        data=json.dumps(body),
        content_type="application/json",
        headers=headers,
    )


@pytest.mark.django_db
class TestStaffBranchesGet:
    def test_owner_reads_any_roster(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = Client().get(
                _branches_url(lab34_setup["manager_a"].id), headers=headers
            )
            assert resp.status_code == 200
            rows = resp.json()
            assert rows == [
                {
                    "branch_id": str(lab34_setup["branch_a"].id),
                    "branch_code": "BR1",
                    "branch_name": "Branch One",
                    "is_primary": True,
                }
            ]

    def test_manager_reads_own_branch_roster(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-5: a Manager reads the roster of their own branches."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            # reception_a shares branch A with manager_a
            resp = Client().get(
                _branches_url(lab34_setup["reception_a"].id), headers=headers
            )
            assert resp.status_code == 200
            assert resp.json()[0]["branch_code"] == "BR1"

    def test_manager_cannot_read_other_branch_roster(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            resp = Client().get(
                _branches_url(lab34_setup["manager_b"].id), headers=headers
            )
            assert resp.status_code == 403

    def test_receptionist_cannot_read_roster(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["reception_a"])
            resp = Client().get(
                _branches_url(lab34_setup["manager_a"].id), headers=headers
            )
            assert resp.status_code == 403

    def test_get_unknown_staff_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = Client().get(_branches_url(uuid.uuid4()), headers=headers)
            assert resp.status_code == 404


@pytest.mark.django_db
class TestStaffBranchesPut:
    def test_put_replaces_set_and_audits(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["owner"])
            manager_a = setup["manager_a"]
            branch_a, branch_b = setup["branch_a"], setup["branch_b"]

            resp = _put_branches(
                Client(),
                headers,
                manager_a.id,
                [
                    {"branch_id": str(branch_a.id), "is_primary": False},
                    {"branch_id": str(branch_b.id), "is_primary": True},
                ],
            )
            assert resp.status_code == 200
            rows = resp.json()
            assert {r["branch_code"] for r in rows} == {"BR1", "BR2"}
            primaries = [r for r in rows if r["is_primary"]]
            assert len(primaries) == 1 and primaries[0]["branch_code"] == "BR2"

            # Old set fully replaced; exactly one primary (SB-4).
            db_rows = list(
                StaffBranch.objects.filter(staff_user=manager_a).order_by(
                    "branch__code"
                )
            )
            assert [str(r.branch_id) for r in db_rows] == [
                str(branch_a.id),
                str(branch_b.id),
            ]
            assert sum(1 for r in db_rows if r.is_primary) == 1

            # SB-6: audit with before/after in the same transaction.
            audit = AuditLog.objects.get(
                action="staff.branches_assigned",
                entity_type="staff_user",
                entity_id=manager_a.id,
            )
            assert audit.actor_id == setup["owner"].id
            assert isinstance(audit.before_jsonb, dict)
            assert isinstance(audit.after_jsonb, dict)
            before = audit.before_jsonb["branches"]
            after = audit.after_jsonb["branches"]
            assert {b["branch_code"] for b in before} == {"BR1"}
            assert {b["branch_code"] for b in after} == {"BR1", "BR2"}
            assert [b for b in after if b["is_primary"]][0]["branch_code"] == "BR2"

    def test_put_requires_owner(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-5: only the Owner writes assignments."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            resp = _put_branches(
                Client(),
                headers,
                lab34_setup["reception_a"].id,
                [
                    {
                        "branch_id": str(lab34_setup["branch_a"].id),
                        "is_primary": True,
                    }
                ],
            )
            assert resp.status_code == 403

    def test_put_empty_set_for_branch_scoped_role_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-1: branch-scoped roles need at least one assignment."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = _put_branches(Client(), headers, lab34_setup["manager_a"].id, [])
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "staff_branch_required"

    def test_put_empty_set_for_tenant_wide_role_ok(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-2: tenant-wide roles take no assignments; an empty set is a no-op."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = _put_branches(Client(), headers, lab34_setup["pathologist"].id, [])
            assert resp.status_code == 200
            assert resp.json() == []

    def test_put_two_primaries_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                setup["manager_a"].id,
                [
                    {"branch_id": str(setup["branch_a"].id), "is_primary": True},
                    {"branch_id": str(setup["branch_b"].id), "is_primary": True},
                ],
            )
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "two_primaries"

    def test_put_zero_primaries_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SB-4: exactly one is_primary=true per staff member."""
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                setup["manager_a"].id,
                [
                    {"branch_id": str(setup["branch_a"].id), "is_primary": False},
                    {"branch_id": str(setup["branch_b"].id), "is_primary": False},
                ],
            )
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "primary_required"

    def test_put_unknown_branch_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                lab34_setup["manager_a"].id,
                [{"branch_id": str(uuid.uuid4()), "is_primary": True}],
            )
            assert resp.status_code == 404

    def test_put_unknown_staff_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                uuid.uuid4(),
                [
                    {
                        "branch_id": str(lab34_setup["branch_a"].id),
                        "is_primary": True,
                    }
                ],
            )
            assert resp.status_code == 404

    def test_put_duplicate_branch_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                setup["manager_a"].id,
                [
                    {"branch_id": str(setup["branch_a"].id), "is_primary": True},
                    {"branch_id": str(setup["branch_a"].id), "is_primary": False},
                ],
            )
            assert resp.status_code == 422

    def test_put_is_atomic_on_validation_failure(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Validated whole, or nothing changes: a bad row keeps the old set."""
        with tenant_context(tenant_a):
            setup = lab34_setup
            headers = auth_headers(setup["owner"])
            manager_a = setup["manager_a"]
            before_ids = sorted(
                str(r.branch_id)
                for r in StaffBranch.objects.filter(staff_user=manager_a)
            )
            audit_count = AuditLog.objects.filter(
                action="staff.branches_assigned", entity_id=manager_a.id
            ).count()

            resp = _put_branches(
                Client(),
                headers,
                manager_a.id,
                [
                    {"branch_id": str(setup["branch_b"].id), "is_primary": True},
                    {"branch_id": str(uuid.uuid4()), "is_primary": False},
                ],
            )
            assert resp.status_code == 404
            after_ids = sorted(
                str(r.branch_id)
                for r in StaffBranch.objects.filter(staff_user=manager_a)
            )
            assert after_ids == before_ids
            assert (
                AuditLog.objects.filter(
                    action="staff.branches_assigned", entity_id=manager_a.id
                ).count()
                == audit_count
            )

    def test_put_strict_serializer_rejects_unknown_fields(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = _put_branches(
                Client(),
                headers,
                lab34_setup["manager_a"].id,
                [
                    {
                        "branch_id": str(lab34_setup["branch_a"].id),
                        "is_primary": True,
                        "admin": True,
                    }
                ],
            )
            assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Out-of-scope detail -> 404 (Layer 2), not 403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOutOfScopeDetail404:
    def test_invoice_detail_out_of_scope_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            invoice_b = lab34_setup["invoice_b"]
            resp = Client().get(f"{INVOICES_URL}/{invoice_b.id}", headers=headers)
            assert resp.status_code == 404

    def test_invoice_detail_in_scope_200(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            invoice_a = lab34_setup["invoice_a"]
            resp = Client().get(f"{INVOICES_URL}/{invoice_a.id}", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["id"] == str(invoice_a.id)

    def test_invoice_cancel_out_of_scope_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Layer 2: actions fetch through the scoped queryset (Doc 04 §8.5)."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            invoice_b = lab34_setup["invoice_b"]
            resp = Client().post(
                f"{INVOICES_URL}/{invoice_b.id}/cancel",
                data=json.dumps({"reason": "scope probe"}),
                content_type="application/json",
                headers=headers,
            )
            assert resp.status_code == 404

    def test_invoice_payment_out_of_scope_404(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["manager_a"])
            invoice_b = lab34_setup["invoice_b"]
            resp = Client().post(
                f"{INVOICES_URL}/{invoice_b.id}/payments",
                data=json.dumps(
                    {"kind": "payment", "method": "cash", "amount": "100.00"}
                ),
                content_type="application/json",
                headers={**headers, "Idempotency-Key": f"lab34-{uuid.uuid4()}"},
            )
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Validation-branch + Layer-2/3 unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAssignmentValidationBranches:
    """Cover every strict-validation branch of the PUT body (SB-4/SB-6)."""

    def _put(
        self, client: Client, headers: dict[str, str], staff_id: Any, body: Any
    ) -> Any:
        return client.put(
            _branches_url(staff_id),
            data=body if isinstance(body, str) else json.dumps(body),
            content_type="application/json",
            headers=headers,
        )

    def test_body_not_a_list_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = self._put(
                Client(), headers, lab34_setup["manager_a"].id, {"branch_id": "x"}
            )
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "validation_error"

    def test_item_not_an_object_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = self._put(Client(), headers, lab34_setup["manager_a"].id, ["nope"])
            assert resp.status_code == 422

    def test_item_missing_key_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = self._put(
                Client(),
                headers,
                lab34_setup["manager_a"].id,
                [{"branch_id": str(lab34_setup["branch_a"].id)}],
            )
            assert resp.status_code == 422

    def test_item_invalid_branch_id_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = self._put(
                Client(),
                headers,
                lab34_setup["manager_a"].id,
                [{"branch_id": "not-a-uuid", "is_primary": True}],
            )
            assert resp.status_code == 422

    def test_item_non_bool_is_primary_422(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(lab34_setup["owner"])
            resp = self._put(
                Client(),
                headers,
                lab34_setup["manager_a"].id,
                [
                    {
                        "branch_id": str(lab34_setup["branch_a"].id),
                        "is_primary": "yes",
                    }
                ],
            )
            assert resp.status_code == 422


@pytest.mark.django_db
class TestLayer2And3Units:
    def test_get_scoped_queryset(
        self, tenant_a: Any, lab34_setup: dict[str, Any]
    ) -> None:
        """BranchScopedAPIView.get_scoped_queryset honours the caller's scope."""
        from apps.branches.scope_views import BranchScopedAPIView
        from apps.patients.models import Patient

        class _PatientView(BranchScopedAPIView):
            scoped_model = Patient

        with tenant_context(tenant_a):
            view = _PatientView()
            qs = view.get_scoped_queryset(user=lab34_setup["manager_a"])
            assert {p.branch.code for p in qs} == {"BR1"}
            qs_all = view.get_scoped_queryset(user=lab34_setup["owner"])
            assert {p.branch.code for p in qs_all} == {"BR1", "BR2"}

    def test_get_scoped_queryset_without_model_raises(self) -> None:
        from django.core.exceptions import ImproperlyConfigured

        from apps.branches.scope_views import BranchScopedAPIView

        with pytest.raises(ImproperlyConfigured):
            BranchScopedAPIView().get_scoped_queryset()

    def test_permission_unauthenticated_denied(self) -> None:
        """Unauthenticated requests are denied (IsAuthenticated owns the 401)."""
        from types import SimpleNamespace

        from apps.branches.scope_views import IsInBranchScope

        request = SimpleNamespace(
            method="POST", user=SimpleNamespace(is_authenticated=False)
        )
        assert IsInBranchScope().has_permission(request, None) is False

    def test_resolve_branch_kwargs_and_malformed(self) -> None:
        """scope_branch_source='kwargs:…' resolves; malformed UUIDs defer to
        the serializer's 422 instead of a scope refusal."""
        from types import SimpleNamespace

        from apps.branches.scope_views import IsInBranchScope

        perm = IsInBranchScope()
        branch_id = uuid.uuid4()

        view = SimpleNamespace(scope_branch_source="kwargs:branch_id")
        request = SimpleNamespace(
            method="POST",
            parser_context={"kwargs": {"branch_id": str(branch_id)}},
        )
        assert perm._resolve_branch(request, view) == branch_id

        view = SimpleNamespace(scope_branch_source="body:branch_id")
        request = SimpleNamespace(method="POST", data={"branch_id": "not-a-uuid"})
        assert perm._resolve_branch(request, view) is None

    def test_exception_handler_delegates_other_exceptions(self) -> None:
        """Non-scope exceptions keep DRF's default rendering."""
        from rest_framework.exceptions import NotFound

        from apps.core.exceptions import problem_json_exception_handler

        resp = problem_json_exception_handler(NotFound(), {})
        assert resp is not None
        assert resp.status_code == 404


@pytest.mark.django_db
class TestIdempotencyScope:
    def test_idempotency_key_does_not_leak_across_branches(
        self, tenant_a: Any, lab34_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Presenting another branch's idempotency key must not return that
        branch's invoice — the replay lookup is scope-aware (Doc 04 §8.5)."""
        with tenant_context(tenant_a):
            setup = lab34_setup
            key = f"lab34-replay-{uuid.uuid4()}"
            body_a = {
                "patient_id": str(setup["patient_a"].id),
                "branch_id": str(setup["branch_a"].id),
                "items": [{"test_id": str(setup["test"].id), "qty": 1}],
                "discount_amount": "0.00",
            }
            headers_a = auth_headers(setup["manager_a"])
            resp_a = Client().post(
                INVOICES_URL,
                data=json.dumps(body_a),
                content_type="application/json",
                headers={**headers_a, "Idempotency-Key": key},
            )
            assert resp_a.status_code == 201

            # Same key, other branch, other manager: 409 — never A's invoice.
            body_b = {
                "patient_id": str(setup["patient_b"].id),
                "branch_id": str(setup["branch_b"].id),
                "items": [{"test_id": str(setup["test"].id), "qty": 1}],
                "discount_amount": "0.00",
            }
            headers_b = auth_headers(setup["manager_b"])
            resp_b = Client().post(
                INVOICES_URL,
                data=json.dumps(body_b),
                content_type="application/json",
                headers={**headers_b, "Idempotency-Key": key},
            )
            assert resp_b.status_code == 409
            assert resp_b.json()["error"]["code"] == "idempotency_key_reused"
            # The other branch's invoice data is never returned.
            assert "id" not in resp_b.json()

            # Same actor replaying their own key still gets their invoice.
            resp_replay = Client().post(
                INVOICES_URL,
                data=json.dumps(body_a),
                content_type="application/json",
                headers={**headers_a, "Idempotency-Key": key},
            )
            assert resp_replay.status_code == 200
            assert resp_replay.json()["id"] == resp_a.json()["id"]
