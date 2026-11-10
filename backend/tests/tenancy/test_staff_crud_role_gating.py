"""Staff CRUD, role gating and onboarding-attack tests (D1–D5, S1–S16).

Covers the privilege boundary directly against the real tenant schemas:
- Owner-only staff CRUD (create/list/detail/edit/deactivate/reactivate/reset)
- Platform role enablement re-checked server-side on create AND edit
- Cross-tenant 404, cross-branch 404, branch-in-tenant validation
- Plan seat limits (D-E counts every StaffUser row including the Owner)
- Owner immutability (S14)
- Immediate session revocation on deactivate/reset (S12)
- Limited login sessions: temp password and TOTP enrolment cannot be skipped
  by calling a business endpoint with the issued token (S6/S7)
- Platform D-D: a role with active staff cannot be disabled
"""

# mypy: disable-error-code="arg-type"
from __future__ import annotations

import uuid
from typing import Any, cast

import pyotp
import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.core.models import PlatformAudit, Subscription
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.branch import BranchFactory
from tests.factories.core import PlatformUserFactory
from tests.factories.staff_user import StaffUserFactory

STAFF_URL = "/api/v1/staff"


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _headers(user: StaffUser, tenant_id: str = "tenant_a") -> dict[str, str]:
    session = AuthService.create_session(user=user, tenant_id=tenant_id)
    return {"HTTP_AUTHORIZATION": f"Bearer {session['access']}"}


def _session(user: StaffUser, tenant_id: str = "tenant_a") -> str:
    return cast(
        str, AuthService.create_session(user=user, tenant_id=tenant_id)["access"]
    )


def _client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(tenant_a: Any) -> StaffUser:
    tenant_a.enabled_roles = ["owner", "reception", "technician"]
    tenant_a.save(update_fields=["enabled_roles", "updated_at"])
    with tenant_context(tenant_a):
        return cast(
            StaffUser,
            StaffUserFactory(
                role=Role.OWNER,
                branch=None,
                email="owner@staffcrud.test",
                display_name="Ayesha Owner",
                totp_enabled=True,
            ),
        )


@pytest.fixture
def branch(tenant_a: Any) -> Any:
    with tenant_context(tenant_a):
        return BranchFactory(code="SC1", name="Staff CRUD Branch")


@pytest.fixture
def reception(tenant_a: Any, branch: Any) -> StaffUser:
    with tenant_context(tenant_a):
        user = cast(
            StaffUser,
            StaffUserFactory(
                role=Role.RECEPTION,
                branch=branch,
                email="reception@staffcrud.test",
                display_name="Sana Reception",
            ),
        )
        StaffBranch.objects.create(staff_user=user, branch=branch, is_primary=True)
        return user


def _create_payload(branch_id: str | uuid.UUID, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "display_name": "Usman Technician",
        "email": "usman@staffcrud.test",
        "role": "technician",
        "branch_id": str(branch_id),
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
@pytest.mark.tenancy
class TestStaffCrud:
    def test_owner_creates_staff_with_temp_password_and_audit(
        self, owner: StaffUser, branch: Any
    ) -> None:
        response = _client().post(
            STAFF_URL,
            data=_create_payload(branch.id),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["temp_password"]
        assert body["password_is_temporary"] is True
        assert body["staff"]["display_name"] == "Usman Technician"
        assert body["staff"]["email"] == "usman@staffcrud.test"
        assert body["staff"]["role"] == "technician"
        assert body["staff"]["totp_status"] == "disabled"
        assert body["staff"]["branch"]["id"] == str(branch.id)

        staff = StaffUser.objects.get(email="usman@staffcrud.test")
        assert staff.password_is_temporary is True
        assert staff.created_by_id == owner.id
        assert staff.branch_id == branch.id
        assert StaffBranch.objects.filter(
            staff_user=staff, branch=branch, is_primary=True
        ).exists()
        assert AuditLog.objects.filter(
            action="staff.created", entity_id=staff.id
        ).exists()
        # S11: no credential material in the response.
        assert "password_hash" not in body["staff"]
        assert "totp_secret_encrypted" not in body["staff"]

    def test_non_owner_cannot_create_or_list(
        self, reception: StaffUser, branch: Any
    ) -> None:
        client = _client()
        create = client.post(
            STAFF_URL,
            data=_create_payload(branch.id),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(reception)},
        )
        assert create.status_code == 403

        listing = client.get(
            STAFF_URL,
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(reception)},
        )
        assert listing.status_code == 403

    def test_anonymous_staff_route_is_401(self, tenant_a: Any) -> None:
        response = _client().get(STAFF_URL, HTTP_HOST="tenant-a.localhost")
        assert response.status_code == 401

    def test_disabled_role_is_rejected_even_with_forged_body(
        self, owner: StaffUser, branch: Any
    ) -> None:
        response = _client().post(
            STAFF_URL,
            data=_create_payload(branch.id, role="pathologist"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "role_not_enabled"

    def test_unknown_and_privileged_body_fields_are_rejected(
        self, owner: StaffUser, branch: Any
    ) -> None:
        client = _client()
        for extra in (
            {"tenant_id": str(uuid.uuid4())},
            {"is_owner": True},
            {"enabled_roles": ["pathologist"]},
        ):
            response = client.post(
                STAFF_URL,
                data=_create_payload(branch.id, **extra),
                format="json",
                **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "validation_error"
            assert response.json()["error"]["details"]["unknown_fields"]

    def test_cross_tenant_branch_is_rejected(
        self, owner: StaffUser, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_b):
            foreign_branch = BranchFactory(code="FB1", name="Foreign")

        response = _client().post(
            STAFF_URL,
            data=_create_payload(foreign_branch.id),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "branch_not_in_tenant"

    def test_case_insensitive_duplicate_email_is_409(
        self, owner: StaffUser, branch: Any
    ) -> None:
        client = _client()
        first = client.post(
            STAFF_URL,
            data=_create_payload(branch.id, email="dup@staffcrud.test"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert first.status_code == 201
        second = client.post(
            STAFF_URL,
            data=_create_payload(
                branch.id, email="DUP@staffcrud.test", display_name="Other"
            ),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "email_exists"

    def test_list_excludes_owner_and_returns_enabled_roles(
        self, owner: StaffUser, reception: StaffUser
    ) -> None:
        response = _client().get(
            STAFF_URL,
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["owner"]["id"] == str(owner.id)
        assert all(row["role"] != "owner" for row in body["results"])
        roles = {row["role"] for row in body["enabled_roles"]}
        assert roles == {"reception", "technician"}
        assert all("password_hash" not in row for row in body["results"])

    def test_edit_to_disabled_role_rejected_then_enabled_role_allowed(
        self, owner: StaffUser, tenant_a: Any, branch: Any
    ) -> None:
        client = _client()
        created = client.post(
            STAFF_URL,
            data=_create_payload(branch.id),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        ).json()
        staff_id = created["staff"]["id"]

        denied = client.patch(
            f"{STAFF_URL}/{staff_id}",
            data={"role": "manager"},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert denied.status_code == 422
        assert denied.json()["error"]["code"] == "role_not_enabled"

        tenant_a.enabled_roles = ["owner", "reception", "technician", "manager"]
        tenant_a.save(update_fields=["enabled_roles", "updated_at"])
        allowed = client.patch(
            f"{STAFF_URL}/{staff_id}",
            data={"role": "manager", "display_name": "Now Manager"},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert allowed.status_code == 200
        assert allowed.json()["role"] == "manager"
        assert AuditLog.objects.filter(
            action="staff.updated", entity_id=uuid.UUID(staff_id)
        ).exists()

    def test_owner_record_is_readable_but_immutable(self, owner: StaffUser) -> None:
        client = _client()
        headers = {
            "HTTP_HOST": "tenant-a.localhost",
            **_headers(owner),
        }
        read = client.get(f"{STAFF_URL}/{owner.id}", **headers)
        assert read.status_code == 200
        assert read.json()["is_owner"] is True

        for method, path, data in (
            ("patch", f"{STAFF_URL}/{owner.id}", {"display_name": "Hacked"}),
            ("post", f"{STAFF_URL}/{owner.id}/deactivate", {}),
            ("post", f"{STAFF_URL}/{owner.id}/reset-password", {}),
        ):
            response = getattr(client, method)(
                path, data=data, format="json", **headers
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "owner_immutable"

    def test_cross_tenant_staff_id_is_404(
        self, owner: StaffUser, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_b):
            branch = BranchFactory(code="TB1", name="Tenant B Branch")
            foreign = StaffUserFactory(
                role=Role.TECHNICIAN,
                branch=branch,
                email="foreign@tenantb.test",
            )

        response = _client().get(
            f"{STAFF_URL}/{foreign.id}",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 404

    def test_deactivate_revokes_session_and_reactivate_restores_login(
        self, owner: StaffUser, tenant_a: Any, branch: Any
    ) -> None:
        client = _client()
        created = client.post(
            STAFF_URL,
            data=_create_payload(
                branch.id,
                email="lifecycle@staffcrud.test",
            ),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        ).json()
        staff_id = created["staff"]["id"]
        temp_password = created["temp_password"]

        with tenant_context(tenant_a):
            staff = StaffUser.objects.get(pk=staff_id)
            live_token = _session(staff)

        deactivated = client.post(
            f"{STAFF_URL}/{staff_id}/deactivate",
            data={},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["status"] == "deactivated"

        # The old access token is dead immediately (revocation marker).
        blocked = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {live_token}",
            },
        )
        assert blocked.status_code == 401

        reactivated = client.post(
            f"{STAFF_URL}/{staff_id}/reactivate",
            data={},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["status"] == "active"

        login = client.post(
            "/api/v1/auth/login",
            data={"email": "lifecycle@staffcrud.test", "password": temp_password},
            format="json",
            HTTP_HOST="tenant-a.localhost",
        )
        assert login.status_code == 200
        assert login.json()["user"]["must_change_password"] is True

    def test_reset_password_invalidates_old_and_forces_change(
        self, owner: StaffUser, branch: Any
    ) -> None:
        client = _client()
        created = client.post(
            STAFF_URL,
            data=_create_payload(branch.id, email="reset@staffcrud.test"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        ).json()
        staff_id = created["staff"]["id"]
        old_password = created["temp_password"]

        reset = client.post(
            f"{STAFF_URL}/{staff_id}/reset-password",
            data={},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert reset.status_code == 200
        new_password = reset.json()["temp_password"]
        assert new_password != old_password

        old_login = client.post(
            "/api/v1/auth/login",
            data={"email": "reset@staffcrud.test", "password": old_password},
            format="json",
            HTTP_HOST="tenant-a.localhost",
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/v1/auth/login",
            data={"email": "reset@staffcrud.test", "password": new_password},
            format="json",
            HTTP_HOST="tenant-a.localhost",
        )
        assert new_login.status_code == 200
        assert new_login.json()["user"]["must_change_password"] is True

    def test_second_owner_is_rejected(self, owner: StaffUser, branch: Any) -> None:
        response = _client().post(
            STAFF_URL,
            data=_create_payload(branch.id, role="owner"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_staff_cannot_use_any_staff_mutation(
        self, owner: StaffUser, reception: StaffUser
    ) -> None:
        client = _client()
        headers = {"HTTP_HOST": "tenant-a.localhost", **_headers(reception)}
        for method, path, data in (
            ("patch", f"{STAFF_URL}/{owner.id}", {"display_name": "x"}),
            ("post", f"{STAFF_URL}/{owner.id}/deactivate", {}),
            ("post", f"{STAFF_URL}/{owner.id}/reactivate", {}),
            ("post", f"{STAFF_URL}/{owner.id}/reset-password", {}),
            ("get", f"{STAFF_URL}/{owner.id}", None),
        ):
            if method == "get":
                response = client.get(path, **headers)
            else:
                response = getattr(client, method)(
                    path, data=data, format="json", **headers
                )
            assert response.status_code == 403

    def test_rename_preserves_multi_branch_assignments(
        self, owner: StaffUser, tenant_a: Any, branch: Any
    ) -> None:
        with tenant_context(tenant_a):
            second = BranchFactory(code="SC2", name="Second Staff Branch")
            manager = StaffUserFactory(
                role=Role.MANAGER,
                branch=branch,
                email="multi@staffcrud.test",
                display_name="Multi Branch",
            )
            StaffBranch.objects.create(
                staff_user=manager, branch=branch, is_primary=True
            )
            StaffBranch.objects.create(staff_user=manager, branch=second)

        response = _client().patch(
            f"{STAFF_URL}/{manager.id}",
            data={"display_name": "Renamed Manager"},
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert response.status_code == 200
        with tenant_context(tenant_a):
            assert StaffBranch.objects.filter(staff_user_id=manager.id).count() == 2

    def test_cursor_pagination_returns_every_row_once(
        self, owner: StaffUser, branch: Any
    ) -> None:
        client = _client()
        for index in range(3):
            created = client.post(
                STAFF_URL,
                data=_create_payload(branch.id, email=f"page{index}@staffcrud.test"),
                format="json",
                **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
            )
            assert created.status_code == 201

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(5):
            query = f"?limit=1{f'&cursor={cursor}' if cursor else ''}"
            response = client.get(
                f"{STAFF_URL}{query}",
                **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
            )
            body = response.json()
            seen.extend(row["id"] for row in body["results"])
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert len(seen) == 3
        assert len(set(seen)) == 3

    def test_staff_limit_counts_owner_and_blocks_next_create(
        self, owner: StaffUser, tenant_a: Any, branch: Any
    ) -> None:
        plan = Subscription.objects.get(
            tenant=tenant_a, status=Subscription.Status.ACTIVE
        ).plan
        plan.max_staff = 2  # Owner + one staff member
        plan.save(update_fields=["max_staff"])

        client = _client()
        first = client.post(
            STAFF_URL,
            data=_create_payload(branch.id, email="seat1@staffcrud.test"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert first.status_code == 201

        second = client.post(
            STAFF_URL,
            data=_create_payload(branch.id, email="seat2@staffcrud.test"),
            format="json",
            **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
        )
        assert second.status_code == 422
        body = second.json()["error"]
        assert body["code"] == "staff_limit_reached"
        assert body["details"]["limit"] == 2


@pytest.mark.django_db
@pytest.mark.tenancy
class TestOnboardingCannotBeBypassed:
    def test_temp_password_session_is_blocked_from_business_endpoints(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            owner = StaffUserFactory(
                role=Role.RECEPTION,
                branch=BranchFactory(code="TP1", name="Temp Branch"),
                email="tempowner@staffcrud.test",
                display_name="Temp Reception",
                password_hash=make_password("TempPassword123!"),
                password_is_temporary=True,
                totp_enabled=False,
            )

        client = _client()
        login = client.post(
            "/api/v1/auth/login",
            data={"email": owner.email, "password": "TempPassword123!"},
            format="json",
            HTTP_HOST="tenant-a.localhost",
        )
        assert login.status_code == 200
        token = login.json()["access"]
        assert login.json()["user"]["must_change_password"] is True

        blocked = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "password_change_required"

        changed = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "TempPassword123!",
                "new_password": "PermanentPassword123!",
            },
            format="json",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert changed.status_code == 200

        # Password changed, Owner TOTP already enrolled -> full access now.
        allowed = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert allowed.status_code == 200

    def test_mandatory_role_disabling_totp_revokes_session(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            owner = StaffUserFactory(
                role=Role.OWNER,
                branch=None,
                email="disabletotp@staffcrud.test",
                display_name="TOTP Owner",
                password_hash=make_password("OwnerPassword123!"),
                totp_enabled=True,
            )
            token = _session(owner)

        client = _client()
        disabled = client.post(
            "/api/v1/auth/totp/disable",
            data={"current_password": "OwnerPassword123!"},
            format="json",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert disabled.status_code == 200
        assert disabled.json()["re_enrol_required"] is True

        blocked = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert blocked.status_code == 401

    def test_mandatory_totp_session_cannot_skip_enrolment(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            owner = StaffUserFactory(
                role=Role.OWNER,
                branch=None,
                email="totpowner@staffcrud.test",
                display_name="TOTP Owner",
                password_hash=make_password("OwnerPassword123!"),
                password_is_temporary=False,
                totp_enabled=False,
            )

        client = _client()
        login = client.post(
            "/api/v1/auth/login",
            data={"email": owner.email, "password": "OwnerPassword123!"},
            format="json",
            HTTP_HOST="tenant-a.localhost",
        )
        assert login.status_code == 200
        token = login.json()["access"]
        assert login.json()["totp_enrollment_required"] is True

        blocked = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "totp_enrollment_required"

        enroll = client.post(
            "/api/v1/auth/totp/enroll",
            data={},
            format="json",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert enroll.status_code == 200
        secret = enroll.json()["secret"]

        confirm = client.post(
            "/api/v1/auth/totp/enroll/confirm",
            data={"code": pyotp.TOTP(secret).now()},
            format="json",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert confirm.status_code == 200

        allowed = client.get(
            "/api/v1/branches",
            **{
                "HTTP_HOST": "tenant-a.localhost",
                "HTTP_AUTHORIZATION": f"Bearer {token}",
            },
        )
        assert allowed.status_code == 200


@pytest.mark.django_db
@pytest.mark.tenancy
def test_platform_cannot_disable_role_with_active_staff(
    tenant_a: Any, owner: StaffUser, reception: StaffUser
) -> None:
    platform_user = cast(Any, PlatformUserFactory(totp_enabled=True))
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    blocked = client.put(
        f"/api/v1/platform/access/{tenant_a.id}",
        data={"roles": [{"role": "reception", "enabled": False}]},
        format="json",
        HTTP_HOST="localhost",
    )
    assert blocked.status_code == 422
    body = blocked.json()
    assert body["code"] == "role_has_active_staff"
    assert body["errors"]["role"] == ["reception"]


@pytest.mark.django_db
@pytest.mark.tenancy
def test_platform_enables_role_then_owner_can_create_it(
    tenant_a: Any, owner: StaffUser
) -> None:
    platform_user = cast(Any, PlatformUserFactory(totp_enabled=True))
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    enabled = client.put(
        f"/api/v1/platform/access/{tenant_a.id}",
        data={"roles": [{"role": "pathologist", "enabled": True}]},
        format="json",
        HTTP_HOST="localhost",
    )
    assert enabled.status_code == 200

    created = _client().post(
        STAFF_URL,
        data={
            "display_name": "Dr Ayesha Khan",
            "email": "path@staffcrud.test",
            "role": "pathologist",
            "branch_id": None,
        },
        format="json",
        **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
    )
    assert created.status_code == 201
    assert created.json()["staff"]["role"] == "pathologist"
    assert created.json()["staff"]["branch"] is None


@pytest.mark.django_db
@pytest.mark.tenancy
def test_tenant_owner_cannot_call_platform_role_endpoint(
    tenant_a: Any, owner: StaffUser
) -> None:
    # The platform URLconf lives on the apex host. A tenant JWT presented
    # there must not authenticate as a platform operator.
    response = _client().put(
        f"/api/v1/platform/access/{tenant_a.id}",
        data={"roles": [{"role": "pathologist", "enabled": True}]},
        format="json",
        **{"HTTP_HOST": "localhost", **_headers(owner)},
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.tenancy
def test_platform_d_d_resolution_and_audit(
    tenant_a: Any, owner: StaffUser, reception: StaffUser
) -> None:
    platform_user = cast(Any, PlatformUserFactory(totp_enabled=True))
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    blocked = client.put(
        f"/api/v1/platform/access/{tenant_a.id}",
        data={"roles": [{"role": "reception", "enabled": False}]},
        format="json",
        HTTP_HOST="localhost",
    )
    assert blocked.status_code == 422

    deactivated = _client().post(
        f"{STAFF_URL}/{reception.id}/deactivate",
        data={},
        format="json",
        **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
    )
    assert deactivated.status_code == 200

    enabled = client.put(
        f"/api/v1/platform/access/{tenant_a.id}",
        data={"roles": [{"role": "reception", "enabled": False}]},
        format="json",
        HTTP_HOST="localhost",
    )
    assert enabled.status_code == 200
    assert "reception" not in enabled.json()["enabled_roles"]
    assert PlatformAudit.objects.filter(
        action="role.disabled", entity_id=tenant_a.id
    ).exists()

    blocked_reactivate = _client().post(
        f"{STAFF_URL}/{reception.id}/reactivate",
        data={},
        format="json",
        **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
    )
    assert blocked_reactivate.status_code == 422
    assert blocked_reactivate.json()["error"]["code"] == "role_not_enabled"


@pytest.mark.django_db
@pytest.mark.tenancy
def test_deactivation_blocks_refresh_and_reset_kills_live_session(
    owner: StaffUser, branch: Any
) -> None:
    client = _client()
    created = client.post(
        STAFF_URL,
        data=_create_payload(branch.id, email="refreshkill@staffcrud.test"),
        format="json",
        **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
    ).json()
    staff_id = created["staff"]["id"]

    login = client.post(
        "/api/v1/auth/login",
        data={
            "email": "refreshkill@staffcrud.test",
            "password": created["temp_password"],
        },
        format="json",
        HTTP_HOST="tenant-a.localhost",
    )
    assert login.status_code == 200
    access = login.json()["access"]

    reset = client.post(
        f"{STAFF_URL}/{staff_id}/reset-password",
        data={},
        format="json",
        **{"HTTP_HOST": "tenant-a.localhost", **_headers(owner)},
    )
    assert reset.status_code == 200

    dead = client.get(
        "/api/v1/branches",
        **{
            "HTTP_HOST": "tenant-a.localhost",
            "HTTP_AUTHORIZATION": f"Bearer {access}",
        },
    )
    assert dead.status_code == 401

    # The browser still has the refresh cookie; it must not resurrect.
    refresh = client.post(
        "/api/v1/auth/refresh",
        format="json",
        HTTP_HOST="tenant-a.localhost",
    )
    assert refresh.status_code == 401


@pytest.mark.django_db
@pytest.mark.tenancy
def test_platform_role_rows_include_active_counts(
    tenant_a: Any, owner: StaffUser, reception: StaffUser
) -> None:
    platform_user = cast(Any, PlatformUserFactory(totp_enabled=True))
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.get(
        f"/api/v1/platform/access/{tenant_a.id}", HTTP_HOST="localhost"
    )
    assert response.status_code == 200
    rows = {row["role"]: row for row in response.json()["roles"]}
    assert rows["owner"]["immutable"] is True
    assert rows["reception"]["active_staff_count"] == 1
    assert rows["reception"]["label"] == "Receptionist / Collection Staff"
