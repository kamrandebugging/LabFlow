import React, { useEffect, useState } from "react";
import { useAuthStore } from "../auth/authStore";
import { settingsService, SettingsApiError } from "./settingsService";

export const TenantSettingsScreen: React.FC = () => {
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role === "owner" || user?.role === "manager";

  // Data state
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form states for the EXACT 6 keys from settings_registry.py
  const [brandDisplayName, setBrandDisplayName] = useState<string>(
    "City Diagnostic Lab",
  );
  const [brandAccentColour, setBrandAccentColour] = useState<string>("#005C55");
  const [billingHoldEnabled, setBillingHoldEnabled] = useState<boolean>(false);
  const [reportDefaultLanguage, setReportDefaultLanguage] = useState<
    "en" | "ur"
  >("en");
  const [reportLinkValidityDays, setReportLinkValidityDays] =
    useState<number>(7);
  const [transferLateAfterHours, setTransferLateAfterHours] =
    useState<number>(24);

  const fetchSettings = async (): Promise<void> => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await settingsService.getSettings();

      if (data.brand_display_name) {
        setBrandDisplayName(
          String(data.brand_display_name.value ?? "City Diagnostic Lab"),
        );
      }
      if (data.brand_accent_colour) {
        setBrandAccentColour(
          String(data.brand_accent_colour.value ?? "#005C55"),
        );
      }
      if (data.billing_hold_enabled) {
        setBillingHoldEnabled(Boolean(data.billing_hold_enabled.value));
      }
      if (data.report_default_language) {
        setReportDefaultLanguage(
          data.report_default_language.value === "ur" ? "ur" : "en",
        );
      }
      if (data.report_link_validity_days) {
        setReportLinkValidityDays(
          Number(data.report_link_validity_days.value ?? 7),
        );
      }
      if (data.transfer_late_after_hours) {
        setTransferLateAfterHours(
          Number(data.transfer_late_after_hours.value ?? 24),
        );
      }
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to load tenant settings",
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchSettings();
  }, []);

  const handleSave = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!canEdit) return;

    // Validate inputs per settings_registry.py rules
    if (!brandDisplayName.trim() || brandDisplayName.length > 120) {
      setErrorMsg("Brand display name must be between 1 and 120 characters.");
      return;
    }

    const hexRe = /^#[0-9a-fA-F]{6}$/;
    if (!hexRe.test(brandAccentColour)) {
      setErrorMsg(
        "Brand accent colour must be a valid 6-character hex code (e.g. #005C55).",
      );
      return;
    }

    if (reportLinkValidityDays < 1 || reportLinkValidityDays > 30) {
      setErrorMsg("Report link validity days must be between 1 and 30 days.");
      return;
    }

    if (transferLateAfterHours < 1) {
      setErrorMsg("Transfer late threshold must be at least 1 hour.");
      return;
    }

    setIsSaving(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    // Backend strictly requires string representations in PATCH body: {"settings": {"key": "str"}}
    const updates: Record<string, string> = {
      brand_display_name: brandDisplayName.trim(),
      brand_accent_colour: brandAccentColour.trim(),
      billing_hold_enabled: billingHoldEnabled ? "true" : "false",
      report_default_language: reportDefaultLanguage,
      report_link_validity_days: String(reportLinkValidityDays),
      transfer_late_after_hours: String(transferLateAfterHours),
    };

    try {
      await settingsService.updateSettings(updates);
      setSuccessMsg("Tenant settings updated successfully.");
      await fetchSettings();
    } catch (err: unknown) {
      if (err instanceof SettingsApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg(
          err instanceof Error ? err.message : "Failed to save settings",
        );
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex-1 bg-slate-50 min-h-screen px-4 sm:px-8 py-6 max-w-4xl mx-auto space-y-6">
      {/* Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-3 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span>Settings</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="text-teal-700 font-medium">Tenant Settings</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Tenant Settings
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Lab-wide configuration registry (Doc 04 §10 key/value store)
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Informative Timezone Pill per Step 2 instruction */}
          <span
            className="inline-flex items-center gap-1.5 font-mono text-xs text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200"
            title="All tenant transactions operate on Pakistan Standard Time"
          >
            <span className="material-symbols-outlined text-[15px] text-teal-600">
              schedule
            </span>
            <span>Asia/Karachi (PKT, UTC+5)</span>
          </span>
        </div>
      </div>

      {/* Notifications */}
      {errorMsg && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 text-red-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-red-600 shrink-0">
            error
          </span>
          <div>
            <p className="font-semibold">Settings Error</p>
            <p className="text-red-700 mt-0.5">{errorMsg}</p>
          </div>
        </div>
      )}

      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-emerald-600 shrink-0">
            check_circle
          </span>
          <p className="font-medium">{successMsg}</p>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="bg-white border border-slate-200 rounded-xl p-8 space-y-6 shadow-sm animate-pulse">
          <div className="h-6 bg-slate-200 rounded w-1/3"></div>
          <div className="h-10 bg-slate-100 rounded"></div>
          <div className="h-10 bg-slate-100 rounded"></div>
          <div className="h-10 bg-slate-100 rounded"></div>
        </div>
      )}

      {!isLoading && (
        <form
          data-testid="tenant-settings-form"
          onSubmit={handleSave}
          className="space-y-6"
        >
          {/* CARD 1: Branding & Report Identity */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span className="material-symbols-outlined text-teal-700">
                  corporate_fare
                </span>
                <span>Branding &amp; Report Identity</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Visual brand configuration displayed on clinical reports and
                invoice headers.
              </p>
            </div>

            <div className="p-6 space-y-6 text-sm">
              {/* 1. brand_display_name */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
                <div>
                  <label
                    htmlFor="brand_display_name"
                    className="block font-semibold text-slate-900"
                  >
                    Brand Display Name
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Printed at the top of patient reports, receipts, and portal
                    banners. (1–120 chars)
                  </p>
                </div>
                <div className="md:col-span-2">
                  <input
                    id="brand_display_name"
                    type="text"
                    required
                    maxLength={120}
                    disabled={!canEdit}
                    value={brandDisplayName}
                    onChange={(e) => setBrandDisplayName(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 text-slate-900 text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none disabled:bg-slate-50"
                  />
                </div>
              </div>

              {/* 2. brand_accent_colour */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start pt-4 border-t border-slate-100">
                <div>
                  <label
                    htmlFor="brand_accent_colour"
                    className="block font-semibold text-slate-900"
                  >
                    Brand Accent Colour
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Primary hex accent colour (#RRGGBB) used on PDF headers,
                    table borders, and online results.
                  </p>
                </div>
                <div className="md:col-span-2 flex items-center gap-3">
                  <input
                    type="color"
                    disabled={!canEdit}
                    value={
                      brandAccentColour.startsWith("#")
                        ? brandAccentColour
                        : "#005C55"
                    }
                    onChange={(e) =>
                      setBrandAccentColour(e.target.value.toUpperCase())
                    }
                    className="w-10 h-10 rounded border border-slate-300 cursor-pointer p-0.5 bg-white disabled:cursor-not-allowed"
                  />
                  <input
                    id="brand_accent_colour"
                    type="text"
                    required
                    maxLength={7}
                    disabled={!canEdit}
                    value={brandAccentColour}
                    onChange={(e) =>
                      setBrandAccentColour(e.target.value.toUpperCase())
                    }
                    placeholder="#005C55"
                    className="w-36 rounded-lg border border-slate-300 font-mono text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none uppercase disabled:bg-slate-50"
                  />
                  <span
                    className="w-6 h-6 rounded-full border border-slate-300 shadow-inner"
                    style={{ backgroundColor: brandAccentColour }}
                  ></span>
                </div>
              </div>
            </div>
          </div>

          {/* CARD 2: Clinical Operations & Traceability */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span className="material-symbols-outlined text-teal-700">
                  science
                </span>
                <span>Clinical Operations &amp; Traceability</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Thresholds and policies governing specimen transit and billing
                holds.
              </p>
            </div>

            <div className="p-6 space-y-6 text-sm">
              {/* 3. billing_hold_enabled */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
                <div>
                  <label
                    htmlFor="billing_hold_enabled"
                    className="block font-semibold text-slate-900"
                  >
                    Tenant Billing Hold
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    When active, receptionists are blocked from generating new
                    billing invoices across all branches.
                  </p>
                </div>
                <div className="md:col-span-2 pt-1">
                  <label className="inline-flex items-center gap-3 cursor-pointer">
                    <input
                      id="billing_hold_enabled"
                      type="checkbox"
                      disabled={!canEdit}
                      checked={billingHoldEnabled}
                      onChange={(e) => setBillingHoldEnabled(e.target.checked)}
                      className="rounded border-slate-300 text-red-600 focus:ring-red-500 w-4 h-4 disabled:cursor-not-allowed"
                    />
                    <span className="font-medium text-slate-800 text-sm">
                      Enable billing hold (Freeze invoice generation)
                    </span>
                  </label>
                  {billingHoldEnabled && (
                    <p className="text-xs text-red-600 mt-1 flex items-center gap-1 font-medium">
                      <span className="material-symbols-outlined text-[15px]">
                        warning
                      </span>
                      Notice: Front desk staff will see &quot;Billing is
                      temporarily held&quot; when attempting to bill patients.
                    </p>
                  )}
                </div>
              </div>

              {/* 4. transfer_late_after_hours */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start pt-4 border-t border-slate-100">
                <div>
                  <label
                    htmlFor="transfer_late_after_hours"
                    className="block font-semibold text-slate-900"
                  >
                    Transfer Late Threshold
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Maximum allowed hours for inter-branch specimen courier
                    transfer before an exception is logged.
                  </p>
                </div>
                <div className="md:col-span-2 flex items-center gap-2">
                  <input
                    id="transfer_late_after_hours"
                    type="number"
                    min={1}
                    required
                    disabled={!canEdit}
                    value={transferLateAfterHours}
                    onChange={(e) =>
                      setTransferLateAfterHours(
                        parseInt(e.target.value, 10) || 1,
                      )
                    }
                    className="w-28 rounded-lg border border-slate-300 font-mono text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none disabled:bg-slate-50"
                  />
                  <span className="text-slate-600 text-sm font-medium">
                    hours (≥ 1)
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* CARD 3: Patient Communication & Report Delivery */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span className="material-symbols-outlined text-teal-700">
                  chat
                </span>
                <span>Patient Communication &amp; Report Delivery</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Language preferences and cryptographic access token life cycle.
              </p>
            </div>

            <div className="p-6 space-y-6 text-sm">
              {/* 5. report_default_language */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
                <div>
                  <label
                    htmlFor="report_default_language"
                    className="block font-semibold text-slate-900"
                  >
                    Default Patient Language
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Language template applied for automated SMS, WhatsApp
                    messages, and patient report links.
                  </p>
                </div>
                <div className="md:col-span-2">
                  <select
                    id="report_default_language"
                    disabled={!canEdit}
                    value={reportDefaultLanguage}
                    onChange={(e) =>
                      setReportDefaultLanguage(e.target.value as "en" | "ur")
                    }
                    className="w-full md:w-64 rounded-lg border border-slate-300 text-slate-900 text-sm px-3 py-2 bg-white focus:ring-2 focus:ring-teal-600 focus:outline-none disabled:bg-slate-50 font-medium"
                  >
                    <option value="en">English (en)</option>
                    <option value="ur">Urdu (اردو - ur)</option>
                  </select>
                </div>
              </div>

              {/* 6. report_link_validity_days */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start pt-4 border-t border-slate-100">
                <div>
                  <label
                    htmlFor="report_link_validity_days"
                    className="block font-semibold text-slate-900"
                  >
                    Report Link Validity
                  </label>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Security expiration window for tokenized public report
                    inspection links without patient login. (1–30 days)
                  </p>
                </div>
                <div className="md:col-span-2 flex items-center gap-2">
                  <input
                    id="report_link_validity_days"
                    type="number"
                    min={1}
                    max={30}
                    required
                    disabled={!canEdit}
                    value={reportLinkValidityDays}
                    onChange={(e) =>
                      setReportLinkValidityDays(
                        parseInt(e.target.value, 10) || 1,
                      )
                    }
                    className="w-28 rounded-lg border border-slate-300 font-mono text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none disabled:bg-slate-50"
                  />
                  <span className="text-slate-600 text-sm font-medium">
                    days (1–30)
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Form Actions Footer */}
          {canEdit ? (
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={fetchSettings}
                disabled={isSaving}
                className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-sm font-medium"
              >
                Reset to Current
              </button>
              <button
                type="submit"
                disabled={isSaving}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
              >
                <span className="material-symbols-outlined text-[18px]">
                  check
                </span>
                <span>{isSaving ? "Saving..." : "Save Settings"}</span>
              </button>
            </div>
          ) : (
            <div className="bg-slate-100 border border-slate-200 rounded-lg p-3 text-xs text-slate-600 text-center">
              You are viewing tenant settings in read-only mode. Only Lab Owners
              and Managers may update configurations.
            </div>
          )}
        </form>
      )}
    </div>
  );
};
