import { useEffect, useState } from "react";
import { platformService } from "./platformService";
import { TotpConfirmModal } from "./TotpConfirmModal";
import type {
  CommercialTiersConfig,
  FoundingOfferConfig,
  PlatformSettingsResponse,
  PlatformTogglesConfig,
} from "./types";

export function SettingsScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form states
  const [commercial, setCommercial] = useState<CommercialTiersConfig>({
    starter_price_pkr: "2999.00",
    growth_price_pkr: "5999.00",
    scale_price_pkr: "9999.00",
    lifetime_single_pkr: "71999.00",
    lifetime_multi_pkr: "143999.00",
    annual_maintenance_pct: 15,
  });

  const [founding, setFounding] = useState<FoundingOfferConfig>({
    active: true,
    slots_used: 3,
    slots_total: 10,
  });

  const [toggles, setToggles] = useState<PlatformTogglesConfig>({
    allow_new_signups: true,
    maintenance_mode: false,
  });

  // TOTP save modals
  const [totpSection, setTotpSection] = useState<
    "commercial" | "founding" | "toggles" | null
  >(null);
  const [saving, setSaving] = useState(false);
  const [totpError, setTotpError] = useState<string | null>(null);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.getSettings();
      setCommercial(res.commercial_tiers);
      setFounding(res.founding_offer);
      setToggles(res.platform_toggles);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Failed to load platform settings.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async (totpCode: string) => {
    if (!totpSection) return;
    try {
      setSaving(true);
      setTotpError(null);

      let payload: Partial<PlatformSettingsResponse> = {};
      if (totpSection === "commercial")
        payload = { commercial_tiers: commercial };
      if (totpSection === "founding") payload = { founding_offer: founding };
      if (totpSection === "toggles") payload = { platform_toggles: toggles };

      const res = await platformService.updateSettings(payload, totpCode);
      setCommercial(res.commercial_tiers);
      setFounding(res.founding_offer);
      setToggles(res.platform_toggles);
      setTotpSection(null);
      setSuccess("Settings updated and synchronized with platform plans.");
    } catch (e: unknown) {
      setTotpError(e instanceof Error ? e.message : "Settings update failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-7xl mx-auto">
      {/* Top Meta & Title Breadcrumb Ribbon */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs font-label-sm text-label-sm text-outline">
            <span>Platform</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span>Global Settings</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="text-primary font-semibold">
              Commercial & Orchestration
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-extrabold">
            Platform Commercial & System Settings
          </h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">
            Configure commercial subscription pricing in Pakistani Rupees (PKR),
            oversee regional founding partner promotions, and control
            infrastructure availability gates.
          </p>
        </div>

        {/* Sync Status Pill */}
        <div className="flex items-center gap-space-sm bg-surface-container-lowest px-space-md py-space-xs rounded shadow-sm self-start md:self-auto border border-outline-variant/30">
          <span className="w-2 h-2 rounded-full bg-primary-container animate-pulse" />
          <div className="flex flex-col font-code-sm text-xs">
            <span className="text-on-surface font-bold">
              PUBLIC SCHEMA SYNCED
            </span>
            <span className="text-outline">Plan records auto-updated</span>
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

      {loading ? (
        <div className="p-16 text-center text-outline">
          <span className="inline-block w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
          <p className="font-body-md text-body-md font-semibold">
            Loading platform settings...
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-space-xl">
          {/* Section 1: Commercial Subscription Tiers & Pricing */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[22px]">
                  payments
                </span>
                <div>
                  <h2 className="font-title-md text-title-md text-on-surface font-bold">
                    Commercial Subscription Tiers (PKR)
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Base rates charged to Pakistani laboratory facilities.
                    Editing prices here directly syncs public Plan rows and
                    provision calculators.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTotpError(null);
                  setTotpSection("commercial");
                }}
                className="h-8 px-space-md bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center gap-1 self-start sm:self-auto"
              >
                <span className="material-symbols-outlined text-[16px]">
                  save
                </span>
                <span>Save Commercial Pricing</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-space-md pt-2">
              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Starter Tier (Monthly)</span>
                  <span className="font-code-sm text-xs text-outline">
                    1 Branch • 5 Staff
                  </span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    PKR
                  </span>
                  <input
                    type="number"
                    step="1"
                    value={commercial.starter_price_pkr}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        starter_price_pkr: e.target.value,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest pl-12 pr-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Growth Tier (Monthly)</span>
                  <span className="font-code-sm text-xs text-outline">
                    3 Branches • Unlimited
                  </span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    PKR
                  </span>
                  <input
                    type="number"
                    step="1"
                    value={commercial.growth_price_pkr}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        growth_price_pkr: e.target.value,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest pl-12 pr-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Scale Tier (Monthly)</span>
                  <span className="font-code-sm text-xs text-outline">
                    Unlimited Branches & Staff
                  </span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    PKR
                  </span>
                  <input
                    type="number"
                    step="1"
                    value={commercial.scale_price_pkr}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        scale_price_pkr: e.target.value,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest pl-12 pr-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Lifetime Perpetual (Single Branch)</span>
                  <span className="font-code-sm text-xs text-secondary font-bold">
                    One-Time
                  </span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    PKR
                  </span>
                  <input
                    type="number"
                    step="1"
                    value={commercial.lifetime_single_pkr}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        lifetime_single_pkr: e.target.value,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest pl-12 pr-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Lifetime Perpetual (Multi-Branch)</span>
                  <span className="font-code-sm text-xs text-secondary font-bold">
                    One-Time
                  </span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    PKR
                  </span>
                  <input
                    type="number"
                    step="1"
                    value={commercial.lifetime_multi_pkr}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        lifetime_multi_pkr: e.target.value,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest pl-12 pr-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="p-space-md bg-surface-container-low rounded flex flex-col gap-1.5 border border-outline-variant/30">
                <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                  <span>Annual Maintenance Surcharge</span>
                  <span className="font-code-sm text-xs text-outline">
                    Post-warranty updates
                  </span>
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="100"
                    value={commercial.annual_maintenance_pct}
                    onChange={(e) =>
                      setCommercial({
                        ...commercial,
                        annual_maintenance_pct:
                          parseInt(e.target.value, 10) || 0,
                      })
                    }
                    className="w-full h-9 bg-surface-container-lowest px-3 font-code-sm text-sm font-bold text-on-surface rounded border border-outline-variant/50 focus:outline-none focus:border-primary"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 font-code-sm text-xs text-outline font-bold">
                    %
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Founding Member Campaign Allocation */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-secondary text-[22px]">
                  workspace_premium
                </span>
                <div>
                  <h2 className="font-title-md text-title-md text-on-surface font-bold">
                    Founding Partner Promotion Campaign
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Subsidized launch slots for initial 10 pioneer diagnostic
                    laboratories across Pakistan.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTotpError(null);
                  setTotpSection("founding");
                }}
                className="h-8 px-space-md bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center gap-1 self-start sm:self-auto"
              >
                <span className="material-symbols-outlined text-[16px]">
                  save
                </span>
                <span>Save Campaign</span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-lg items-center pt-2">
              <div className="flex items-center justify-between p-space-md bg-surface-container-low rounded border border-outline-variant/30">
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm font-bold text-on-surface">
                    Founding Member Offer State
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    When active, new qualified labs receive lifetime founder
                    rate locks.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setFounding({ ...founding, active: !founding.active })
                  }
                  className={`w-11 h-6 rounded-full relative transition-colors cursor-pointer ${
                    founding.active ? "bg-primary" : "bg-surface-container-high"
                  }`}
                >
                  <span
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all shadow-xs ${
                      founding.active ? "right-1" : "left-1"
                    }`}
                  />
                </button>
              </div>

              <div className="p-space-md bg-surface-container-low rounded border border-outline-variant/30 flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="font-title-sm text-title-sm font-bold text-on-surface">
                    Pioneer Slots Quota
                  </span>
                  <span className="font-code-sm text-xs font-bold text-primary">
                    {founding.slots_used} of {founding.slots_total} slots
                    claimed
                  </span>
                </div>
                <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden my-1">
                  <div
                    className="bg-primary h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (founding.slots_used / founding.slots_total) * 100)}%`,
                    }}
                  />
                </div>
                <span className="font-body-xs text-body-xs text-outline">
                  {Math.max(0, founding.slots_total - founding.slots_used)}{" "}
                  subsidized onboarding allocations remaining.
                </span>
              </div>
            </div>
          </div>

          {/* Section 3: Platform Availability & Orchestration Toggles */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[22px]">
                  toggle_on
                </span>
                <div>
                  <h2 className="font-title-md text-title-md text-on-surface font-bold">
                    Platform Availability & Maintenance Gates
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Master kill switches for multi-tenant gateway traffic and
                    new lab registration.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTotpError(null);
                  setTotpSection("toggles");
                }}
                className="h-8 px-space-md bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center gap-1 self-start sm:self-auto"
              >
                <span className="material-symbols-outlined text-[16px]">
                  save
                </span>
                <span>Save Operational Gates</span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md pt-2">
              <div className="flex items-center justify-between p-space-md bg-surface-container-low rounded border border-outline-variant/30">
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm font-bold text-on-surface">
                    Allow New Tenant Provisioning
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    When disabled, the `/platform/tenants/new` flow is locked
                    for non-super users.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setToggles({
                      ...toggles,
                      allow_new_signups: !toggles.allow_new_signups,
                    })
                  }
                  className={`w-11 h-6 rounded-full relative transition-colors cursor-pointer ${
                    toggles.allow_new_signups
                      ? "bg-primary"
                      : "bg-surface-container-high"
                  }`}
                >
                  <span
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all shadow-xs ${
                      toggles.allow_new_signups ? "right-1" : "left-1"
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-space-md bg-surface-container-low rounded border border-outline-variant/30">
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm font-bold text-on-surface">
                    Platform Maintenance Mode
                  </span>
                  <span className="font-body-xs text-body-xs text-error font-semibold">
                    Warning: Places all tenant nodes into temporary read-only
                    state.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setToggles({
                      ...toggles,
                      maintenance_mode: !toggles.maintenance_mode,
                    })
                  }
                  className={`w-11 h-6 rounded-full relative transition-colors cursor-pointer ${
                    toggles.maintenance_mode
                      ? "bg-error"
                      : "bg-surface-container-high"
                  }`}
                >
                  <span
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all shadow-xs ${
                      toggles.maintenance_mode ? "right-1" : "left-1"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TOTP Confirmation Modal */}
      <TotpConfirmModal
        isOpen={Boolean(totpSection)}
        title="Authorize Platform Settings Mutation"
        description="You are writing system-wide commercial or operational modifications. Enter your 6-digit TOTP security code to authorize."
        confirmLabel="Save Configuration"
        isLoading={saving}
        error={totpError}
        onConfirm={handleSave}
        onCancel={() => setTotpSection(null)}
      />
    </div>
  );
}
