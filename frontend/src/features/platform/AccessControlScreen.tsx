import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { platformService } from "./platformService";
import { TotpConfirmModal } from "./TotpConfirmModal";
import type { AccessControlData, TenantListItem } from "./types";

interface RoleDef {
  key: string;
  name: string;
  immutable?: boolean;
  desc: string;
}

const ROLES: RoleDef[] = [
  {
    key: "owner",
    name: "Laboratory Owner",
    immutable: true,
    desc: "Root administrative and commercial authority. Cannot be disabled on any tenant node.",
  },
  {
    key: "manager",
    name: "General / Operations Manager",
    desc: "Branch staff oversight, shift scheduling, inventory thresholds, and cash drawer management.",
  },
  {
    key: "receptionist",
    name: "Receptionist / Billing Desk",
    desc: "Patient registration, token queue processing, sample intake, and thermal receipt printing.",
  },
  {
    key: "technician",
    name: "Medical Laboratory Technician",
    desc: "Analyzer sample rack assignment, test result data entry, worklists, and calibration runs.",
  },
  {
    key: "pathologist",
    name: "Consultant Pathologist",
    desc: "Diagnostic interpretation, electronic report signing, abnormal panic values, and QC sign-offs.",
  },
];

interface FeatureFlagDef {
  key: string;
  name: string;
  desc: string;
  icon: string;
}

const FLAGS: FeatureFlagDef[] = [
  {
    key: "referral_partners",
    name: "Doctor & Clinic Referral Partners",
    desc: "Commission rules, referral tracking, and periodic settlement vouchers for referring physicians.",
    icon: "handshake",
  },
  {
    key: "settlements",
    name: "Manual Financial Settlements",
    desc: "Enables manual Pakistani bank transfer, Easypaisa, and JazzCash payment logging in tenant app.",
    icon: "payments",
  },
  {
    key: "advanced_analytics",
    name: "Advanced Clinical & Financial Analytics",
    desc: "Real-time TAT (Turnaround Time) metrics, sample rejection rates, and revenue forecasting.",
    icon: "analytics",
  },
  {
    key: "automated_whatsapp",
    name: "Automated Patient WhatsApp Dispatch",
    desc: "Direct PDF delivery of verified diagnostic test results to patient WhatsApp numbers.",
    icon: "chat",
  },
];

export function AccessControlScreen() {
  const { tenantId: routeTenantId } = useParams<{ tenantId?: string }>();

  const [tenants, setTenants] = useState<TenantListItem[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>("");
  const [access, setAccess] = useState<AccessControlData | null>(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form states
  const [enabledRoles, setEnabledRoles] = useState<string[]>(["owner"]);
  const [branchLimit, setBranchLimit] = useState<number>(1);
  const [staffLimit, setStaffLimit] = useState<string>("");
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});

  // TOTP modal
  const [totpModalOpen, setTotpModalOpen] = useState(false);
  const [totpError, setTotpError] = useState<string | null>(null);

  // Load tenant list
  useEffect(() => {
    let isMounted = true;
    platformService
      .listTenants({ limit: 100 })
      .then((res) => {
        if (!isMounted) return;
        setTenants(res.tenants);
        const initId = routeTenantId || res.tenants[0]?.id;
        if (initId) setSelectedTenantId(initId);
      })
      .catch((e: unknown) => {
        if (!isMounted) return;
        setError(
          e instanceof Error ? e.message : "Failed to load tenant list.",
        );
      });
    return () => {
      isMounted = false;
    };
  }, [routeTenantId]);

  // Load tenant access control
  useEffect(() => {
    if (!selectedTenantId) return;
    let isMounted = true;
    setLoading(true);
    setError(null);
    setSuccess(null);

    platformService
      .getAccessControl(selectedTenantId)
      .then((data) => {
        if (!isMounted) return;
        setAccess(data);
        setEnabledRoles(data.enabled_roles || ["owner"]);
        setBranchLimit(data.branch_limit || 1);
        setStaffLimit(
          data.staff_limit !== null ? String(data.staff_limit) : "",
        );
        setFeatureFlags(data.feature_flags || {});
      })
      .catch((e: unknown) => {
        if (!isMounted) return;
        setError(
          e instanceof Error
            ? e.message
            : "Failed to load access configuration.",
        );
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedTenantId]);

  const toggleRole = (key: string) => {
    if (key === "owner") return; // IMMUTABLE
    if (enabledRoles.includes(key)) {
      setEnabledRoles(enabledRoles.filter((r) => r !== key));
    } else {
      setEnabledRoles([...enabledRoles, key]);
    }
  };

  const toggleFlag = (key: string) => {
    setFeatureFlags((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleSave = async (totpCode: string) => {
    if (!selectedTenantId) return;
    try {
      setSaving(true);
      setTotpError(null);
      const res = await platformService.updateAccessControl(
        selectedTenantId,
        {
          branch_limit: branchLimit,
          staff_limit:
            staffLimit.trim() === "" ? null : parseInt(staffLimit, 10),
          enabled_roles: enabledRoles,
          feature_flags: featureFlags,
        },
        totpCode,
      );
      setAccess(res);
      setTotpModalOpen(false);
      setSuccess("Access policies & feature scopes saved successfully.");
    } catch (e: unknown) {
      setTotpError(
        e instanceof Error ? e.message : "Failed to update access control.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Header Breadcrumb & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-code-sm text-code-sm">
            <span>Platform Governance</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="text-on-surface font-semibold">
              Tenant Access & Feature Scopes
            </span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight font-extrabold">
            Tenant Access Control & Permissions
          </h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">
            Configure role visibility, operational staff quotas, and enterprise
            feature flags enforced in tenant applications.
          </p>
        </div>

        <div className="flex items-center gap-space-sm self-start md:self-auto">
          <button
            type="button"
            onClick={() => {
              if (!access) return;
              setEnabledRoles(access.enabled_roles);
              setBranchLimit(access.branch_limit);
              setStaffLimit(
                access.staff_limit !== null ? String(access.staff_limit) : "",
              );
              setFeatureFlags(access.feature_flags);
              setSuccess(null);
            }}
            className="h-8 px-space-md bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm rounded transition-colors flex items-center gap-space-xs shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px]">
              restart_alt
            </span>
            Reset Changes
          </button>
          <button
            type="button"
            onClick={() => {
              setTotpError(null);
              setTotpModalOpen(true);
            }}
            className="h-8 px-space-lg bg-primary-container hover:bg-primary text-on-primary font-label-sm text-label-sm rounded transition-colors flex items-center gap-space-xs shadow-sm font-bold"
          >
            <span className="material-symbols-outlined text-[16px]">
              verified_user
            </span>
            Save Access Policy
          </button>
        </div>
      </div>

      {/* Tenant Context Selector Strip */}
      <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col xl:flex-row xl:items-center justify-between gap-space-md">
        <div className="flex flex-col sm:flex-row sm:items-center gap-space-md">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm font-semibold">
            <span className="material-symbols-outlined text-primary text-[18px]">
              domain
            </span>
            <span className="uppercase tracking-wider">Tenant Selection</span>
          </div>
          <div className="relative min-w-[320px] max-w-md">
            <select
              value={selectedTenantId}
              onChange={(e) => setSelectedTenantId(e.target.value)}
              className="w-full h-9 bg-surface-container-low font-title-sm text-title-sm text-on-surface pl-space-md pr-8 rounded appearance-none focus:outline-none focus:border-primary border border-outline-variant/40 cursor-pointer"
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.slug} • {t.plan_name || "Active Tier"})
                </option>
              ))}
            </select>
            <span className="material-symbols-outlined absolute right-space-sm top-1/2 -translate-y-1/2 text-outline pointer-events-none text-[18px]">
              unfold_more
            </span>
          </div>
        </div>

        {access && (
          <div className="flex flex-wrap items-center gap-space-xs font-code-sm text-code-sm text-outline">
            <span className="px-2 py-0.5 bg-surface-container-high rounded text-on-surface-variant font-semibold">
              Plan: <strong className="text-primary">{access.plan_name}</strong>
            </span>
            <span className="px-2 py-0.5 bg-surface-container-high rounded text-on-surface-variant">
              Plan Branch Cap: {access.max_branches ?? "Unlimited"}
            </span>
            <span className="px-2 py-0.5 bg-surface-container-high rounded text-on-surface-variant">
              Plan Staff Cap: {access.max_staff ?? "Unlimited"}
            </span>
          </div>
        )}
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

      {loading ? (
        <div className="p-16 text-center text-outline">
          <span className="inline-block w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
          <p className="font-body-md text-body-md font-semibold">
            Loading access permissions...
          </p>
        </div>
      ) : access ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
          {/* Section 1: Role Entitlements Matrix (7 Columns) */}
          <div className="lg:col-span-7 bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">
                  badge
                </span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  Role Entitlement Matrix
                </h2>
              </div>
              <span className="font-body-xs text-body-xs text-outline italic">
                Only enabled roles appear in this lab's app
              </span>
            </div>

            <div className="divide-y divide-surface-container-high">
              {ROLES.map((role) => {
                const isEnabled = enabledRoles.includes(role.key);
                const isOwner = role.key === "owner";

                return (
                  <div
                    key={role.key}
                    className="py-space-md flex items-start justify-between gap-space-md"
                  >
                    <div className="flex flex-col">
                      <div className="flex items-center gap-space-xs">
                        <span className="font-title-sm text-title-sm text-on-surface font-bold">
                          {role.name}
                        </span>
                        {isOwner ? (
                          <span className="bg-primary text-on-primary font-code-sm text-[10px] px-1.5 py-0.5 rounded font-extrabold uppercase tracking-wider flex items-center gap-1">
                            <span className="material-symbols-outlined text-[12px]">
                              lock
                            </span>
                            IMMUTABLE SYSTEM ROLE
                          </span>
                        ) : isEnabled ? (
                          <span className="bg-primary-fixed text-on-primary-fixed font-code-sm text-[10px] px-1.5 py-0.5 rounded font-bold uppercase">
                            ENABLED
                          </span>
                        ) : (
                          <span className="bg-surface-container-high text-outline font-code-sm text-[10px] px-1.5 py-0.5 rounded font-bold uppercase">
                            DISABLED
                          </span>
                        )}
                      </div>
                      <p className="font-body-xs text-body-xs text-on-surface-variant mt-1 leading-relaxed">
                        {role.desc}
                      </p>
                    </div>

                    <button
                      type="button"
                      disabled={isOwner}
                      onClick={() => toggleRole(role.key)}
                      className={`w-11 h-6 rounded-full relative transition-colors shrink-0 mt-1 cursor-pointer disabled:cursor-not-allowed ${
                        isEnabled ? "bg-primary" : "bg-surface-container-high"
                      }`}
                    >
                      <span
                        className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all shadow-xs ${
                          isEnabled ? "right-1" : "left-1"
                        }`}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Quotas & Feature Flags (5 Columns) */}
          <div className="lg:col-span-5 flex flex-col gap-space-lg">
            {/* Operational Quotas */}
            <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
              <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[20px]">
                    tune
                  </span>
                  <h2 className="font-title-md text-title-md text-on-surface font-bold">
                    Operational Quotas
                  </h2>
                </div>
                <span className="font-code-sm text-code-sm text-outline">
                  Enforced at API Gateway
                </span>
              </div>

              <div className="flex flex-col gap-space-sm">
                <div className="flex flex-col gap-1">
                  <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                    <span>Staff Seats Limit</span>
                    <span className="font-body-xs text-body-xs text-outline">
                      {access.max_staff
                        ? `Plan max: ${access.max_staff}`
                        : "Unlimited on plan"}
                    </span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    max={access.max_staff ?? 999}
                    placeholder="Leave empty for unlimited"
                    value={staffLimit}
                    onChange={(e) => setStaffLimit(e.target.value)}
                    className="w-full h-9 bg-surface-container-low px-3 font-code-sm text-code-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary"
                  />
                  <span className="font-body-xs text-body-xs text-outline">
                    Total simultaneous active login accounts permitted across
                    all non-owner roles.
                  </span>
                </div>

                <div className="flex flex-col gap-1 mt-2">
                  <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                    <span>Branch Physical Locations Limit</span>
                    <span className="font-body-xs text-body-xs text-outline">
                      {access.max_branches
                        ? `Plan max: ${access.max_branches}`
                        : "Unlimited on plan"}
                    </span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    max={access.max_branches ?? 999}
                    value={branchLimit}
                    onChange={(e) =>
                      setBranchLimit(parseInt(e.target.value, 10) || 1)
                    }
                    className="w-full h-9 bg-surface-container-low px-3 font-code-sm text-code-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary"
                  />
                  <span className="font-body-xs text-body-xs text-outline">
                    Number of collection centers / diagnostic processing hubs
                    this tenant may create.
                  </span>
                </div>
              </div>
            </div>

            {/* Feature Flags */}
            <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
              <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[20px]">
                    toggle_on
                  </span>
                  <h2 className="font-title-md text-title-md text-on-surface font-bold">
                    Enterprise Feature Flags
                  </h2>
                </div>
                <span className="font-code-sm text-code-sm text-outline">
                  Dynamic Scopes
                </span>
              </div>

              <div className="divide-y divide-surface-container-high">
                {FLAGS.map((f) => {
                  const isEnabled = Boolean(featureFlags[f.key]);

                  return (
                    <div
                      key={f.key}
                      className="py-space-sm flex items-start justify-between gap-space-md"
                    >
                      <div className="flex items-start gap-space-sm">
                        <div className="w-8 h-8 rounded bg-surface-container flex items-center justify-center text-primary shrink-0 mt-0.5">
                          <span className="material-symbols-outlined text-[18px]">
                            {f.icon}
                          </span>
                        </div>
                        <div className="flex flex-col">
                          <div className="flex items-center gap-space-xs">
                            <span className="font-title-sm text-title-sm text-on-surface font-bold">
                              {f.name}
                            </span>
                            {isEnabled ? (
                              <span className="bg-primary-fixed text-on-primary-fixed font-code-sm text-[10px] px-1 py-0.5 rounded font-bold uppercase">
                                ON
                              </span>
                            ) : (
                              <span className="bg-surface-container-high text-outline font-code-sm text-[10px] px-1 py-0.5 rounded font-bold uppercase">
                                OFF
                              </span>
                            )}
                          </div>
                          <p className="font-body-xs text-body-xs text-on-surface-variant mt-0.5">
                            {f.desc}
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => toggleFlag(f.key)}
                        className={`w-9 h-5 rounded-full relative transition-colors shrink-0 mt-1 cursor-pointer ${
                          isEnabled ? "bg-primary" : "bg-surface-container-high"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow-xs ${
                            isEnabled ? "right-0.5" : "left-0.5"
                          }`}
                        />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <TotpConfirmModal
        isOpen={totpModalOpen}
        title="Authorize Access Policy Update"
        description={`You are updating role visibility and operational quotas for ${access?.tenant_name || "the selected tenant"}. Enter your 6-digit TOTP code to write this change to the immutable platform audit ledger.`}
        confirmLabel="Save Access Policy"
        isLoading={saving}
        error={totpError}
        onConfirm={handleSave}
        onCancel={() => setTotpModalOpen(false)}
      />
    </div>
  );
}
