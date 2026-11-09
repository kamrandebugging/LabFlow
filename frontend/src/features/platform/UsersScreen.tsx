import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { platformService } from "./platformService";
import { TotpConfirmModal } from "./TotpConfirmModal";
import type {
  LabOwnerUserItem,
  PlatformTeamMember,
  PlatformUserInviteItem,
} from "./types";

export function UsersScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [labOwners, setLabOwners] = useState<LabOwnerUserItem[]>([]);
  const [platformTeam, setPlatformTeam] = useState<PlatformTeamMember[]>([]);
  const [invitations, setInvitations] = useState<PlatformUserInviteItem[]>([]);

  const [search, setSearch] = useState("");

  // Invite Operator modal
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("support");
  const [inviteTotpOpen, setInviteTotpOpen] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Disable modal
  const [userToDisable, setUserToDisable] = useState<PlatformTeamMember | null>(
    null,
  );
  const [disableLoading, setDisableLoading] = useState(false);
  const [disableError, setDisableError] = useState<string | null>(null);

  const loadUsers = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.listUsers();
      setLabOwners(res.lab_owners);
      setPlatformTeam(res.platform_team);
      setInvitations(res.invitations);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Failed to load users directory.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const filteredOwners = useMemo(() => {
    if (!search.trim()) return labOwners;
    const q = search.toLowerCase();
    return labOwners.filter(
      (o) =>
        o.name.toLowerCase().includes(q) ||
        o.email.toLowerCase().includes(q) ||
        o.lab_name.toLowerCase().includes(q) ||
        o.lab_slug.toLowerCase().includes(q) ||
        o.whatsapp.toLowerCase().includes(q),
    );
  }, [labOwners, search]);

  const handleInviteConfirm = async (totpCode: string) => {
    if (!inviteEmail.trim()) {
      setInviteError("Please provide an email address.");
      return;
    }
    try {
      setInviteLoading(true);
      setInviteError(null);
      const res = await platformService.invitePlatformUser(
        inviteEmail.trim(),
        inviteRole,
        totpCode,
      );
      setInviteTotpOpen(false);
      setInviteModalOpen(false);
      setInviteEmail("");
      setSuccess(res.detail || "Platform operator invitation created.");
      loadUsers();
    } catch (e: unknown) {
      setInviteError(e instanceof Error ? e.message : "Invitation failed.");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleDisableConfirm = async (totpCode: string) => {
    if (!userToDisable) return;
    try {
      setDisableLoading(true);
      setDisableError(null);
      const res = await platformService.disablePlatformUser(
        userToDisable.id,
        totpCode,
      );
      setUserToDisable(null);
      setSuccess(res.detail || "Account status updated.");
      loadUsers();
    } catch (e: unknown) {
      setDisableError(
        e instanceof Error ? e.message : "Account update failed.",
      );
    } finally {
      setDisableLoading(false);
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Utility Context Bar */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-space-md pb-space-xs">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-outline font-label-sm text-label-sm uppercase tracking-wider">
            <span>Platform Management</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="text-primary font-bold">
              Identity & User Directory
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-extrabold">
            Users & Account Governance
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl">
            Administer tenant laboratory owner credentials and internal LabFlow
            platform operators across Pakistani municipal zones.
          </p>
        </div>

        {/* Quick Search Field */}
        <div className="flex items-center gap-space-sm w-full lg:w-96">
          <div className="relative w-full">
            <span className="material-symbols-outlined absolute left-space-sm top-1/2 -translate-y-1/2 text-outline text-[18px]">
              person_search
            </span>
            <input
              type="text"
              placeholder="Search by user, email, lab, phone..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-9 bg-surface-container-lowest pl-8 pr-space-md rounded font-body-sm text-body-sm text-on-surface placeholder:text-outline shadow-sm border border-outline-variant/30 focus:outline-none focus:bg-surface-container-low transition-colors"
            />
          </div>
        </div>
      </div>

      {success && (
        <div className="p-space-md bg-primary-fixed/30 border border-primary text-primary-container rounded flex items-center justify-between font-title-sm text-title-sm font-semibold">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">
              check_circle
            </span>
            <span>{success}</span>
          </div>
          <button
            onClick={() => setSuccess(null)}
            className="text-on-surface-variant hover:text-on-surface"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      )}

      {error && (
        <div className="p-space-md bg-error/10 border border-error/20 text-error rounded flex items-center gap-2 font-body-sm text-body-sm">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{error}</span>
        </div>
      )}

      {/* Part A: Laboratory Owner Accounts Table */}
      <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-primary text-[22px]">
              medical_services
            </span>
            <div>
              <h2 className="font-title-md text-title-md text-on-surface font-bold">
                Tenant Laboratory Owners
              </h2>
              <p className="font-body-xs text-body-xs text-outline">
                Primary director contacts extracted strictly from public tenant
                registration records. (Tenant staff are strictly isolated in
                tenant databases).
              </p>
            </div>
          </div>
          <span className="font-code-sm text-code-sm bg-surface-container-high text-on-surface-variant px-2 py-0.5 rounded font-bold">
            {filteredOwners.length} Registered Lab Owners
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-outline">
            <span className="inline-block w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-2" />
            <p className="font-body-sm text-body-sm">
              Loading laboratory accounts...
            </p>
          </div>
        ) : filteredOwners.length === 0 ? (
          <div className="p-8 text-center text-outline">
            <p className="font-body-sm text-body-sm">
              No laboratory owner records found matching query.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                  <th className="px-3 py-1 font-semibold">Owner Identity</th>
                  <th className="px-3 py-1 font-semibold">
                    Laboratory Facility
                  </th>
                  <th className="px-3 py-1 font-semibold">WhatsApp / Phone</th>
                  <th className="px-3 py-1 font-semibold">Status</th>
                  <th className="px-3 py-1 font-semibold">
                    Last Login / Active
                  </th>
                  <th className="px-3 py-1 font-semibold text-right">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                {filteredOwners.map((owner) => {
                  const isActive = owner.status === "active";

                  return (
                    <tr
                      key={owner.id}
                      className="h-12 hover:bg-surface-container-low transition-colors"
                    >
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <span className="font-title-sm text-title-sm font-bold text-inverse-surface">
                            {owner.name}
                          </span>
                          <span className="font-code-sm text-code-sm text-outline">
                            {owner.email}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <Link
                            to={`/platform/tenants/${owner.id}`}
                            className="font-medium text-on-surface hover:text-primary transition-colors flex items-center gap-1"
                          >
                            <span>{owner.lab_name}</span>
                            <span className="material-symbols-outlined text-[14px] text-outline">
                              launch
                            </span>
                          </Link>
                          <span className="font-code-sm text-code-sm text-outline">
                            {owner.lab_slug}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        {owner.whatsapp ? (
                          <a
                            href={`https://wa.me/${owner.whatsapp.replace(/\D/g, "")}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-primary hover:underline font-code-sm font-semibold"
                          >
                            <span className="material-symbols-outlined text-[16px]">
                              chat
                            </span>
                            <span>{owner.whatsapp}</span>
                          </a>
                        ) : (
                          <span className="text-outline font-code-sm">
                            Not configured
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isActive ? (
                          <span className="px-2 py-0.5 bg-primary-fixed text-on-primary-fixed font-label-sm text-label-sm font-bold uppercase rounded">
                            ACTIVE
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 bg-error-container text-on-error-container font-label-sm text-label-sm font-bold uppercase rounded">
                            {owner.status.toUpperCase()}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-code-sm text-outline">
                        {owner.last_login
                          ? new Date(owner.last_login).toLocaleString("en-PK", {
                              day: "numeric",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : `Registered ${new Date(
                              owner.created_at,
                            ).toLocaleDateString("en-PK", {
                              day: "numeric",
                              month: "short",
                            })}`}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="inline-flex items-center gap-1 justify-end">
                          <Link
                            to={`/platform/tenants/${owner.id}`}
                            className="h-7 px-2.5 bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm rounded transition-colors flex items-center gap-1"
                          >
                            <span>Inspect Node</span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Part B: Platform Internal Team */}
      <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-primary text-[22px]">
              admin_panel_settings
            </span>
            <div>
              <h2 className="font-title-md text-title-md text-on-surface font-bold">
                Platform Internal Team & Operators
              </h2>
              <p className="font-body-xs text-body-xs text-outline">
                Super administrator and regional operations engineers with root
                access to multi-tenant orchestration.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setInviteModalOpen(true)}
            className="h-8 px-space-md bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors flex items-center gap-1 self-start sm:self-auto shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px]">
              person_add
            </span>
            <span>Invite Platform Operator</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                <th className="px-3 py-1 font-semibold">Operator Account</th>
                <th className="px-3 py-1 font-semibold">Security Role</th>
                <th className="px-3 py-1 font-semibold">2FA Security State</th>
                <th className="px-3 py-1 font-semibold">Status</th>
                <th className="px-3 py-1 font-semibold">Enrolled On</th>
                <th className="px-3 py-1 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
              {platformTeam.map((u) => {
                const isSuper = u.role === "super_admin";

                return (
                  <tr
                    key={u.id}
                    className="h-12 hover:bg-surface-container-low transition-colors"
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-space-sm">
                        <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold">
                          {u.email[0]?.toUpperCase() || "U"}
                        </div>
                        <div className="flex flex-col">
                          <span className="font-title-sm text-title-sm font-bold text-on-surface">
                            {u.email.split("@")[0]}
                          </span>
                          <span className="font-code-sm text-code-sm text-outline">
                            {u.email}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {isSuper ? (
                        <span className="px-2 py-0.5 bg-primary-container text-on-primary font-code-sm text-[11px] font-bold uppercase rounded">
                          Platform Owner
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-surface-container-high text-on-surface-variant font-code-sm text-[11px] font-bold uppercase rounded">
                          {u.role.replace("_", " ")}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {u.totp_enabled ? (
                        <span className="inline-flex items-center gap-1 text-primary font-body-xs font-semibold">
                          <span className="material-symbols-outlined text-[16px]">
                            verified_user
                          </span>
                          <span>Hardware TOTP Enforced</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-error font-body-xs font-semibold">
                          <span className="material-symbols-outlined text-[16px]">
                            warning
                          </span>
                          <span>TOTP Pending Enrollment</span>
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {u.is_active ? (
                        <span className="px-2 py-0.5 bg-primary-fixed text-on-primary-fixed font-label-sm text-label-sm font-bold uppercase rounded">
                          ACTIVE
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-error-container text-on-error-container font-label-sm text-label-sm font-bold uppercase rounded">
                          SUSPENDED
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-code-sm text-outline">
                      {new Date(u.date_joined).toLocaleDateString("en-PK", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {!isSuper && (
                        <button
                          type="button"
                          onClick={() => setUserToDisable(u)}
                          className="h-7 px-2.5 bg-surface-container-high hover:bg-error-container hover:text-on-error-container text-on-surface-variant font-label-sm text-label-sm rounded transition-colors"
                        >
                          {u.is_active ? "Disable" : "Re-enable"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pending Invitations */}
        {invitations.length > 0 && (
          <div className="mt-space-md pt-space-md border-t border-surface-container flex flex-col gap-space-xs">
            <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider font-semibold">
              Pending Operator Invitations ({invitations.length})
            </span>
            <div className="divide-y divide-surface-container-high">
              {invitations.map((inv) => (
                <div
                  key={inv.id}
                  className="py-2 flex items-center justify-between text-body-sm"
                >
                  <div className="flex items-center gap-space-sm font-code-sm">
                    <span className="material-symbols-outlined text-outline text-[18px]">
                      mail
                    </span>
                    <span className="font-semibold">{inv.email}</span>
                    <span className="px-1.5 py-0.5 bg-surface-container-high rounded text-xs text-on-surface-variant uppercase">
                      {inv.role}
                    </span>
                  </div>
                  <span className="font-code-sm text-xs text-outline">
                    Invited {new Date(inv.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Invite Modal Step 1 */}
      {inviteModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container-lowest max-w-md w-full p-space-lg rounded-lg shadow-xl border border-outline-variant/40 flex flex-col gap-space-md">
            <div className="flex items-center gap-space-xs">
              <span className="material-symbols-outlined text-primary text-[24px]">
                person_add
              </span>
              <h3 className="font-title-md text-title-md text-on-surface font-bold">
                Invite Platform Operator
              </h3>
            </div>
            <p className="font-body-sm text-body-sm text-outline">
              Create an administrative invitation for support engineers or
              operations staff. They will be required to enroll a hardware TOTP
              authenticator upon initial password establishment.
            </p>

            <div className="flex flex-col gap-space-sm">
              <div className="flex flex-col gap-1">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                  Corporate Email Address *
                </label>
                <input
                  type="email"
                  placeholder="operator@labflow.pk"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full h-9 bg-surface-container-low px-3 font-code-sm text-code-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                  Security Access Role *
                </label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full h-9 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary cursor-pointer"
                >
                  <option value="support">
                    Support Operator (Read-only + health telemetry)
                  </option>
                  <option value="admin">
                    Platform Admin (Lab lifecycle + settlements)
                  </option>
                  <option value="super_admin">
                    Super Administrator (Full root control)
                  </option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-space-sm pt-space-xs border-t border-surface-container">
              <button
                type="button"
                onClick={() => setInviteModalOpen(false)}
                className="px-space-md py-space-xs bg-surface-container hover:bg-surface-container-high rounded text-sm font-semibold text-on-surface"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!inviteEmail.trim()) return;
                  setInviteTotpOpen(true);
                }}
                className="px-space-md py-space-xs bg-primary hover:bg-primary-container text-white rounded text-sm font-bold shadow-sm"
              >
                Continue to TOTP Auth
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Invite TOTP Modal */}
      <TotpConfirmModal
        isOpen={inviteTotpOpen}
        title="Authorize Operator Invitation"
        description={`You are dispatching an internal platform operator invitation to ${inviteEmail} with role "${inviteRole}". Enter your 6-digit TOTP code to authorize.`}
        confirmLabel="Send Operator Invite"
        isLoading={inviteLoading}
        error={inviteError}
        onConfirm={handleInviteConfirm}
        onCancel={() => setInviteTotpOpen(false)}
      />

      {/* Disable TOTP Modal */}
      <TotpConfirmModal
        isOpen={Boolean(userToDisable)}
        title="Authorize Account Modification"
        description={`You are toggling the active status of platform operator ${userToDisable?.email}. Enter your 6-digit TOTP code to authorize.`}
        confirmLabel={
          userToDisable?.is_active ? "Disable Operator" : "Re-enable Operator"
        }
        confirmVariant={userToDisable?.is_active ? "danger" : "primary"}
        isLoading={disableLoading}
        error={disableError}
        onConfirm={handleDisableConfirm}
        onCancel={() => setUserToDisable(null)}
      />
    </div>
  );
}
