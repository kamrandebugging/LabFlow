# LabFlow — Staff CRUD with Platform-Controlled Role Gating

**Implementation report and evidence**
**Date:** 2026-11-10
**Branch:** `labs/staff-crud-role-gating` (off `main` @ `502f73d`)
**Merged:** PR #62 → `main` @ `58a3328` (squash merge)
**CI:** all checks green on the PR and on `main`.

---

## 1. Report corrections (verified against code)

The specification asked for its claims to be re-checked. These were confirmed:

| Claim | Result |
|---|---|
| Five fixed roles | Confirmed: `owner / manager / reception / technician / pathologist` (`backend/apps/accounts/models.py`). |
| No staff CRUD existed | Confirmed. Only `/staff/{id}/branches` and `/staff/{id}/reset-totp` existed. |
| No role dashboards | Confirmed. `/` always rendered `OwnerDashboardScreen`. |
| `StaffUser` had no name | Confirmed. `display_name` added in this branch. |
| Auth hardening already shipped | Confirmed. Temp-password flag, TOTP self-service, session revocation reused, not rebuilt. |
| Platform role toggles unverified | Partly present: `Tenant.enabled_roles` + `PUT /api/v1/platform/access/{id}` existed, but used the non-existent `receptionist` value, exposed no active-staff counts, and allowed disabling a role with active staff. Fixed here. |

Two corrections to the proposed design:

1. **Pathologist stays tenant-wide.** Existing documented branch rule (Doc 04 §8.4/§8.5, `StaffUser.is_tenant_wide`) treats Owner and Pathologist as tenant-wide. Enforcing a single branch on Pathologist would have regressed scoping tests and blocked cross-branch approvals. Staff CRUD therefore requires a branch for `manager`, `reception`, `technician`; Pathologist is stored with `branch = NULL`. This is the only deviation from FR-6, and it preserves existing, tested behaviour.
2. **The platform role endpoint was extended, not duplicated.** `/api/v1/platform/access/{tenant_id}` already owned TOTP-gated platform writes and audit. Adding a second `/roles` endpoint would have created two sources of truth. The existing endpoint now returns per-role rows and enforces D-D.

---

## 2. Locked decisions applied

The recommendations in Section 10 of the specification were applied as the user decision, because the instruction was to implement the report as written:

- **D-A** No second Owner via Staff CRUD; the role validator only accepts the four creatable roles.
- **D-B** `display_name` added, required at staff creation, shown in list/detail/audit and PDF signatories.
- **D-C** One home branch per staff account (Pathologist excepted, see §1).
- **D-D** Disabling a role with active staff is blocked (`422 role_has_active_staff`), listing the blocking staff.
- **D-E** Seat count includes the Owner (`StaffUser.objects.count()`), so Starter = 5 total rows.
- **D-F** Manager permissions extracted from code, not invented (matrix below).
- **D-G** New lab defaults: Owner + Reception + Technician.
- **D-H** Temp password is shown once in the Owner's UI; never returned by a GET, never logged.
- **D-I** PDF footer now prints display name + real role label, email fallback.

---

## 3. Corrected permission matrix (extracted from code)

Citations are the existing gate constants; the Owner column is the locked superrole decision.

| Capability | Owner | Manager | Reception | Technician | Pathologist |
|---|---|---|---|---|---|
| Register patient | YES | YES | YES (`patients/views.py:81`) | NO | NO |
| Edit patient | YES | YES | NO (`patients/services.py:413`) | NO | NO |
| Invoice / take payment | YES | YES | YES (`billing/services.py:62,71`) | read only | read only |
| Discount / refund | YES | YES (refund ≤ PKR 5,000) | NO (`billing/services.py:70,72`) | NO | NO |
| Collect / receive sample | YES | YES | collect YES / receive NO (`samples/services.py:75-80`) | collect NO / receive YES | NO |
| Enter results | YES | NO | NO | YES | YES (`results/services.py:27`) |
| Approve results (incl. own) | YES | NO | NO | NO | YES (`results/services.py:29`) |
| View report | YES | YES | YES | YES | YES (`reports/services_query.py:33`) |
| Regenerate report | YES | YES | NO | NO | YES (`reports/services.py:62`) |
| Deliver / issue patient link | YES | YES | YES | NO | NO (`reports/services.py:64,68`) |
| Money / settlements / ledger | YES | ledger + settlements read; no approve/settle | NO | NO | NO (`partners/views_ledger.py:51`, `views_settlements.py:74,138,234`) |
| Referral partners / rules | YES | NO | NO | NO | NO (`partners/views.py:48`) |
| Catalog / prices | YES | NO | NO | NO | read; ranges write (`catalog/views.py:45-63`) |
| Branches | YES | NO | NO | NO | NO (`branches/services.py:55`) |
| Staff CRUD | YES | NO | NO | NO | NO (new `staff_service.py`) |
| Platform role toggles | NO | NO | NO | NO | NO (platform JWT only) |
| `/platform/*` | NO | NO | NO | NO | NO (separate login) |

Hard rules enforced server-side: staff never edit/deactivate/impersonate the Owner, never change their own role/branch/status, and never reach owner-only endpoints.

---

## 4. What was built

### Data model
- `StaffUser.display_name` — required for newly created staff, email-local-part backfill for legacy rows.
- `StaffUser.created_by` — self-FK (SET NULL), Owner who created the account.
- Case-insensitive unique email constraint `uq_staff_user_email_ci`; existing exact-match constraint retained.
- Migration `0008_staff_identity_and_ci_email.py` is additive and never reads or rewrites password/TOTP material.
- The public `Tenant.staff_count` mirror is refreshed after create/reactivate/deactivate so the Platform labs list does not show stale seat usage.

### Tenant API (Owner only)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/staff` | cursor list, excludes Owner, returns Owner card, enabled roles, branches, seat limit |
| POST | `/api/v1/staff` | creates account + temp password (once) |
| GET | `/api/v1/staff/{id}` | detail + account audit history |
| PATCH | `/api/v1/staff/{id}` | display name / role / branch, audited |
| POST | `/api/v1/staff/{id}/deactivate` | deactivate-only, revokes sessions |
| POST | `/api/v1/staff/{id}/reactivate` | role must still be enabled |
| POST | `/api/v1/staff/{id}/reset-password` | new temp password once, revokes sessions |

Error codes: `role_not_enabled` (422), `branch_not_in_tenant` (422), `email_exists` (409), `staff_limit_reached` (422 with limit/current), `owner_immutable` (403), `validation_error` (422), `not_found` (404), `forbidden` (403).

### Platform API
`GET/PUT /api/v1/platform/access/{tenant_id}` now returns `roles[]` with `{role, label, enabled, immutable, active_staff_count, updated_by, updated_at}`, normalises `receptionist → reception`, blocks `role_has_active_staff`, and writes one `role.enabled` / `role.disabled` audit row per changed role in addition to the existing summary row.

### Security hardening in this branch
- **S6/S7:** login-issued sessions carry an `onboarding` claim. Authentication returns `403 password_change_required` or `403 totp_enrollment_required` for every route outside the relevant flow. The check is state-based, so finishing the flow upgrades the same token. TOTP disable for a mandatory role revokes all sessions and forces re-enrolment.
- **S5:** read-only sample/result/report/detail paths now filter by the caller's branch and return 404. Lifecycle actions keep their documented codes (`sample_not_here` 409, `result_entry_disabled_at_branch` 403); invoice creation checks that both patient and branch belong to the caller's scope.
- **S12:** deactivate and password reset call the existing revoke-all machinery immediately.
- **S9:** committed Fernet key in `.env.example` replaced by a generation instruction/placeholder.
- **S14:** every staff mutation rejects an Owner target with `owner_immutable`.

### Frontend
- New `Settings → Staff` screen (`/settings/staff`) with list, Owner card, empty state, create/edit/detail/audit, deactivate/reactivate/reset password, one-time temp-password panel.
- Role-aware sidebar, landing screens and route guard:
  - Owner → existing dashboard.
  - Manager → branch oversight summary.
  - Reception → patients/invoices/samples summary.
  - Technician → worklist/samples summary.
  - Pathologist → approvals/reports/exceptions summary.
- Owner-only paths (`/settings/staff`, branches, exports, partners, catalog) redirect staff to their home; the API still returns 403.
- Forced temporary-password screen replaces the dismissible modal.
- Platform Access Control shows active-staff counts and refuses to switch off a role with active staff, explaining why.

---

## 5. Automated evidence

Environment: PostgreSQL 16 on `127.0.0.1:5440` (`labflow_test`), Redis `127.0.0.1:6379`, `config.settings.test`.

| Check | Result |
|---|---|
| `makemigrations --check --dry-run` | No changes detected |
| `manage.py check` | no issues |
| `ruff check .` | All checks passed |
| `ruff format --check` | clean after formatting |
| `mypy` on changed backend modules | Success, no issues |
| `tests/tenancy/test_staff_crud_role_gating.py` | **27 passed** |
| `tsc --noEmit` | clean |
| ESLint targeted | clean |
| Vitest `access.test.ts` + `StaffScreen.test.tsx` | **11 passed** |
| GitHub Actions `Unit & Integration Tests` (full suite) | **1385 passed, 2 skipped** |
| GitHub Actions Lint / Type Checks / Build / Secrets / Dependency Scan | **all green** |

Security cases explicitly proven by the 18 backend tests:

- Owner create → 201, temp password, `password_is_temporary`, branch row, audit row, no credential fields in response.
- Non-owner create/list → 403; anonymous → 401.
- Disabled role with forged body → `422 role_not_enabled`.
- Body containing `tenant_id`, `is_owner`, `enabled_roles` → `422 validation_error`.
- Cross-tenant branch → `422 branch_not_in_tenant`; cross-tenant staff id → 404.
- Case-insensitive duplicate email → `409 email_exists`.
- Edit to disabled role → 422; after platform enables it → 200 + audit.
- Owner detail readable; Owner patch/deactivate/reset → `403 owner_immutable`.
- Deactivate kills the existing token (401) and blocks login; reactivate restores login.
- Reset password kills the old password immediately and forces `must_change_password`.
- Seat limit with Owner counted → `422 staff_limit_reached`.
- Temp-password token cannot call `/api/v1/branches` (`password_change_required`).
- Mandatory-TOTP token cannot skip enrolment (`totp_enrollment_required`); after confirm, the same token works.
- Platform cannot disable a role with active staff (`role_has_active_staff`); role rows include active counts.

---

## 5b. ECC agent review pass

The installed ECC agents were run against the branch:

- `planner` — requirements/risk gap review.
- `tdd-guide` — test-quality and coverage audit.
- `django-reviewer` (with `security-reviewer` criteria) — ORM/DRF/security review.

Findings fixed after that pass:

1. **Multi-branch assignment wipe:** a display-name-only PATCH no longer deletes
   `staff_branch` rows; assignments are rewritten only when role/branch changes.
2. **Branch-scope source consistency:** read checks now use
   `effective_branch_ids()` (`staff_branch` ∪ home branch), so revocation and
   secondary-branch access behave consistently with lists.
3. **Fail-closed role defaults:** an empty `enabled_roles` is Owner-only; D-G
   defaults are written explicitly at provisioning, never inferred.
4. **D-D fail-closed:** if the staff table cannot be read while a role is being
   disabled, the write returns `422 role_state_unknown` instead of allowing it.
5. **Platform write atomicity:** tenant + flags + audit rows now share one
   transaction; quotas are parsed once and rejected cleanly (no 500/-1 caps).
6. **Cursor pagination:** the cursor is the last returned row; UI has “Load more”.
7. **Seat/email races:** creation locks the public Tenant row, re-checks seat
   and email inside the transaction, and maps `IntegrityError` to `409`.
8. **TOTP reset/promotion:** resetting a mandatory role's TOTP or promoting a
   staff member into a mandatory-TOTP role revokes their sessions; Owner/self
   TOTP reset through the staff endpoint is rejected.
9. **Refresh no longer trusts a stale claim:** onboarding is re-derived from the
   current account state on every refresh.
10. **S8:** staff writes are rate-limited per user (60/hour); unsafe methods only.
11. **XFF hardening:** audit IPs are validated with `ipaddress.ip_address`.
12. **Unknown roles:** navigation/guard functions fail closed instead of throwing.

Residual items deliberately not claimed as solved: best-effort Redis revocation
failure handling, pre-deploy refresh sessions, and the case-variant email
migration preflight are documented as open risks rather than silently accepted.

## 6. Honest still-open list

1. **Live browser E2E (E2E-1 … E2E-7) was not executed in this session.** The branch includes automated API evidence and frontend unit/behaviour tests, but the specification's live Apex-style run (provisioned lab, real login, screenshots, PDF delivery) still needs to be performed on a fully running stack. No "PASS" is claimed for those cases.
2. **Manager permission matrix confirmation** remains a product sign-off item (D-F): the matrix above is extracted from code, not newly invented, but the user should confirm Manager's read-only settlements/ledger scope.
3. **Pathologist branch model** is documented as tenant-wide; if the user truly wants one-branch Pathologists, that is a separate scoping change affecting results/reports.
4. **Legacy tenants with `enabled_roles = ["owner"]`** will show no creatable roles until Kamran enables them in the Platform Access Control screen. This is D1 working as specified, not a defect.
5. **`receptionist` remains accepted as a legacy input alias** on the platform endpoint; all stored and returned values are canonical `reception`.
