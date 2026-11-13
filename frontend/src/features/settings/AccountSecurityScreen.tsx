import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { accountService, AccountApiError } from "./accountService";

/**
 * Account & Security screen (Settings suite).
 *
 * - Change password (clears the provisioning-issued temporary credential).
 * - Two-factor authentication: enable (QR/manual key + confirmation) and
 *   disable (requires current password).
 *
 * Styled to match the existing settings screens (TenantSettingsScreen):
 * slate surface, white cards, teal accent, material-symbols icons.
 */
export const AccountSecurityScreen: React.FC = () => {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const user = useAuthStore((s) => s.user);
  const setSession = useAuthStore((s) => s.setSession);
  const logout = useAuthStore((s) => s.logout);
  const currentLanguage = i18n.resolvedLanguage?.startsWith("ur") ? "ur" : "en";

  // --------------------------------------------------------------------------
  // Change password state
  // --------------------------------------------------------------------------
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  // --------------------------------------------------------------------------
  // Two-factor state
  // --------------------------------------------------------------------------
  const [totpEnabled, setTotpEnabled] = useState<boolean>(() =>
    Boolean(user?.totp_enabled),
  );
  const [totpError, setTotpError] = useState<string | null>(null);
  const [totpNotice, setTotpNotice] = useState<string | null>(null);

  // Enable flow
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [otpauthUri, setOtpauthUri] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [enrollBusy, setEnrollBusy] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  // Disable flow
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableBusy, setDisableBusy] = useState(false);

  const isTemporary = useMemo(
    () => Boolean(user?.must_change_password),
    [user],
  );

  // --------------------------------------------------------------------------
  // Change password
  // --------------------------------------------------------------------------
  const handleChangePassword = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (newPassword.length < 12) {
      setPasswordError(t("settings:account.error_short"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t("settings:account.error_mismatch"));
      return;
    }

    setPasswordBusy(true);
    try {
      await accountService.changePassword(currentPassword, newPassword);
      setPasswordSuccess(t("settings:account.password_changed"));

      // Clear the temporary-credential flag on the in-memory session so the
      // "change your password" warning disappears everywhere.
      const { accessToken } = useAuthStore.getState();
      if (user) {
        setSession(accessToken ?? "", { ...user, must_change_password: false });
      }

      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      setPasswordError(
        err instanceof AccountApiError
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:account.error_change_failed"),
      );
    } finally {
      setPasswordBusy(false);
    }
  };

  // --------------------------------------------------------------------------
  // Two-factor: enable
  // --------------------------------------------------------------------------
  const handleOpenEnroll = async (): Promise<void> => {
    setEnrollOpen(true);
    setTotpError(null);
    setBackupCodes(null);
    setTotpCode("");
    setSecret(null);
    setOtpauthUri(null);
    setEnrollBusy(true);
    try {
      const data = await accountService.startTotpEnroll();
      setSecret(data.secret);
      setOtpauthUri(data.otpauth_uri);
    } catch (err: unknown) {
      setTotpError(
        err instanceof AccountApiError
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:account.error_enrol_start"),
      );
      setEnrollOpen(false);
    } finally {
      setEnrollBusy(false);
    }
  };

  const handleConfirmEnroll = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setEnrollBusy(true);
    setTotpError(null);
    try {
      const data = await accountService.confirmTotpEnroll(totpCode);
      setBackupCodes(data.backup_codes);
      setTotpEnabled(true);
      setTotpNotice(t("settings:account.enabled_notice"));
    } catch (err: unknown) {
      setTotpError(
        err instanceof AccountApiError
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:account.error_code_mismatch"),
      );
    } finally {
      setEnrollBusy(false);
    }
  };

  const handleCopyKey = (): void => {
    if (secret) {
      void navigator.clipboard.writeText(secret);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  const handleCopyCodes = (): void => {
    if (backupCodes) {
      void navigator.clipboard.writeText(backupCodes.join("\n"));
      setCopiedCodes(true);
      setTimeout(() => setCopiedCodes(false), 2000);
    }
  };

  // --------------------------------------------------------------------------
  // Two-factor: disable
  // --------------------------------------------------------------------------
  const handleDisableTotp = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setDisableBusy(true);
    setTotpError(null);
    try {
      const result = await accountService.disableTotp(disablePassword);
      if (result.re_enrol_required) {
        // Mandatory role: the server revoked every session so a fresh login
        // must enrol TOTP again before business screens unlock.
        await logout();
        window.location.replace("/login?reason=totp_disabled");
        return;
      }
      setTotpEnabled(false);
      setDisableOpen(false);
      setDisablePassword("");
      setTotpNotice(t("settings:account.disabled_notice"));
    } catch (err: unknown) {
      setTotpError(
        err instanceof AccountApiError
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:account.error_disable"),
      );
    } finally {
      setDisableBusy(false);
    }
  };

  const finishEnroll = (): void => {
    setEnrollOpen(false);
    setBackupCodes(null);
    setSecret(null);
    setOtpauthUri(null);
    setTotpCode("");
  };

  return (
    <div className="flex-1 bg-slate-50 min-h-screen px-4 sm:px-8 py-6 max-w-4xl mx-auto space-y-6">
      {/* Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-3 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span>{t("common:nav.settings")}</span>
            <span className="material-symbols-outlined text-[14px] rtl:rotate-180">
              chevron_right
            </span>
            <span className="text-teal-700 font-medium">
              {t("settings:account.title")}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {t("settings:account.title")}
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            {t("settings:account.subtitle")}
          </p>
        </div>
      </div>

      {/* Temporary password warning */}
      {isTemporary && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3 text-amber-900 text-sm">
          <span className="material-symbols-outlined text-[20px] text-amber-600 shrink-0">
            warning
          </span>
          <div>
            <p className="font-semibold">{t("settings:account.temp_title")}</p>
            <p className="text-amber-800 mt-0.5">
              {t("settings:account.temp_body")}
            </p>
          </div>
        </div>
      )}

      {totpError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 text-red-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-red-600 shrink-0">
            error
          </span>
          <p className="text-red-700">{totpError}</p>
        </div>
      )}

      {totpNotice && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-emerald-600 shrink-0">
            check_circle
          </span>
          <p className="font-medium">{totpNotice}</p>
        </div>
      )}

      {/* CARD 0: Staff app language (client preference only — same preference
          as the header switcher, available to every role) */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <span className="material-symbols-outlined text-teal-700">
              translate
            </span>
            <span>{t("settings:language.title")}</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {t("settings:language.description")}
          </p>
        </div>
        <div className="p-6 space-y-6 text-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
            <div>
              <label
                htmlFor="app_language"
                className="block font-semibold text-slate-900"
              >
                {t("settings:language.field")}
              </label>
              <p className="text-xs text-slate-500 mt-0.5">
                {t("settings:language.help")}
              </p>
            </div>
            <div className="md:col-span-2">
              <select
                id="app_language"
                value={currentLanguage}
                onChange={(e) =>
                  void i18n.changeLanguage(
                    e.target.value === "ur" ? "ur" : "en",
                  )
                }
                className="w-full md:w-64 rounded-lg border border-slate-300 text-slate-900 text-sm px-3 py-2 bg-white focus:ring-2 focus:ring-teal-600 focus:outline-none font-medium"
              >
                <option value="en">{t("settings:language.english")}</option>
                <option value="ur" lang="ur" dir="rtl">
                  {t("settings:language.urdu")}
                </option>
              </select>
              <p className="text-[11px] text-slate-500 mt-1">
                {t("settings:language.saved")}
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {t("settings:language.same_as_switcher")}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* CARD 1: Change Password */}
      <form
        data-testid="account-change-password-form"
        onSubmit={handleChangePassword}
        className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden"
      >
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <span className="material-symbols-outlined text-teal-700">
              password
            </span>
            <span>{t("settings:account.change_title")}</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {t("settings:account.change_desc")}
          </p>
        </div>

        <div className="p-6 space-y-6 text-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
            <label
              htmlFor="current_password"
              className="block font-semibold text-slate-900"
            >
              {t("settings:account.current_label")}
            </label>
            <div className="md:col-span-2">
              <input
                id="current_password"
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 text-slate-900 text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start pt-4 border-t border-slate-100">
            <div>
              <label
                htmlFor="new_password"
                className="block font-semibold text-slate-900"
              >
                {t("settings:account.new_label")}
              </label>
              <p className="text-xs text-slate-500 mt-0.5">
                {t("settings:account.new_help")}
              </p>
            </div>
            <div className="md:col-span-2">
              <input
                id="new_password"
                type="password"
                autoComplete="new-password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 text-slate-900 text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start pt-4 border-t border-slate-100">
            <label
              htmlFor="confirm_password"
              className="block font-semibold text-slate-900"
            >
              {t("settings:account.confirm_label")}
            </label>
            <div className="md:col-span-2">
              <input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 text-slate-900 text-sm px-3.5 py-2 focus:ring-2 focus:ring-teal-600 focus:outline-none"
              />
            </div>
          </div>

          {passwordError && (
            <p
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              {passwordError}
            </p>
          )}
          {passwordSuccess && (
            <p
              role="status"
              className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700"
            >
              {passwordSuccess}
            </p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="submit"
              disabled={passwordBusy}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 text-white rounded-lg text-sm font-semibold shadow-sm transition-all disabled:opacity-60"
            >
              <span className="material-symbols-outlined text-[18px]">
                check
              </span>
              <span>
                {passwordBusy
                  ? t("settings:account.updating")
                  : t("settings:account.update")}
              </span>
            </button>
          </div>
        </div>
      </form>

      {/* CARD 2: Two-Factor Authentication */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <span className="material-symbols-outlined text-teal-700">
              verified_user
            </span>
            <span>{t("settings:account.totp_title")}</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {t("settings:account.totp_desc")}
          </p>
        </div>

        <div className="p-6 space-y-4 text-sm">
          {/* Enable flow */}
          {!totpEnabled && !enrollOpen && (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold text-slate-900">
                  {t("settings:account.status_off")}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("settings:account.status_off_hint")}
                </p>
              </div>
              <button
                type="button"
                onClick={handleOpenEnroll}
                className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
              >
                <span className="material-symbols-outlined text-[18px]">
                  shield
                </span>
                <span>{t("settings:account.enable")}</span>
              </button>
            </div>
          )}

          {/* Enabled summary */}
          {totpEnabled && !enrollOpen && (
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center">
                  <span className="material-symbols-outlined text-emerald-600">
                    check_circle
                  </span>
                </span>
                <div>
                  <p className="font-semibold text-slate-900">
                    {t("settings:account.status_on")}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {t("settings:account.status_on_hint")}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDisableOpen((v) => !v)}
                className="inline-flex items-center gap-2 px-4 py-2 border border-red-300 text-red-700 hover:bg-red-50 rounded-lg text-sm font-semibold transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">
                  lock
                </span>
                <span>{t("settings:account.disable")}</span>
              </button>
            </div>
          )}

          {/* Disable confirmation form */}
          {totpEnabled && disableOpen && (
            <form
              onSubmit={handleDisableTotp}
              className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-3"
            >
              <p className="text-xs font-semibold text-red-900">
                {t("settings:account.disable_help")}
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder={t("settings:account.current_placeholder")}
                  value={disablePassword}
                  onChange={(e) => setDisablePassword(e.target.value)}
                  className="flex-1 rounded-lg border border-red-300 text-slate-900 text-sm px-3.5 py-2 focus:ring-2 focus:ring-red-500 focus:outline-none"
                />
                <div className="flex items-center gap-2">
                  <button
                    type="submit"
                    disabled={disableBusy}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-60"
                  >
                    {disableBusy
                      ? t("settings:account.disabling")
                      : t("settings:account.confirm_disable")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDisableOpen(false)}
                    className="px-4 py-2 border border-red-300 text-red-700 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors"
                  >
                    {t("common:actions.cancel")}
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Enrolment wizard */}
          {enrollOpen && !backupCodes && (
            <form onSubmit={handleConfirmEnroll} className="space-y-4">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                  {t("settings:account.enroll_title")}
                </p>
                {otpauthUri ? (
                  <p
                    dir="ltr"
                    className="mt-2 break-all font-mono text-[11px] text-slate-700"
                  >
                    {otpauthUri}
                  </p>
                ) : (
                  <p className="mt-2 text-xs text-slate-500">
                    {t("settings:account.preparing")}
                  </p>
                )}
                {secret ? (
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <p className="text-[11px] text-slate-500">
                      {t("settings:account.manual_key")}{" "}
                      <span
                        dir="ltr"
                        className="font-mono text-slate-800 font-medium select-all"
                      >
                        {secret}
                      </span>
                    </p>
                    <button
                      type="button"
                      onClick={handleCopyKey}
                      className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-100 transition-colors"
                      title={t("settings:account.copy_manual_title")}
                    >
                      {copiedKey ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                          <span className="text-emerald-700 font-bold">
                            {t("settings:account.copied")}
                          </span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5 text-slate-500" />
                          <span>{t("settings:account.copy_key")}</span>
                        </>
                      )}
                    </button>
                  </div>
                ) : null}
              </div>

              <div>
                <label
                  htmlFor="totp-code"
                  className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  {t("settings:account.code_label")}
                </label>
                <input
                  id="totp-code"
                  inputMode="numeric"
                  required
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  className="w-full md:w-64 rounded-lg border border-slate-300 px-3 py-2 text-center font-mono text-lg tracking-[0.4em] focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
                  placeholder="000000"
                />
              </div>

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={finishEnroll}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-sm font-medium"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={enrollBusy || !secret}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-all disabled:opacity-60"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    shield
                  </span>
                  <span>
                    {enrollBusy
                      ? t("settings:account.activating")
                      : t("settings:account.activate")}
                  </span>
                </button>
              </div>
            </form>
          )}

          {/* Backup codes */}
          {enrollOpen && backupCodes && (
            <div className="space-y-4">
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-amber-900">
                    {t("settings:account.backup_save")}
                  </p>
                  <button
                    type="button"
                    onClick={handleCopyCodes}
                    className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-950 hover:bg-amber-100/70 transition-colors"
                    title={t("settings:account.copy_codes_title")}
                  >
                    {copiedCodes ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                        <span className="text-emerald-700 font-bold">
                          {t("settings:account.copied")}
                        </span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-amber-800" />
                        <span>{t("settings:account.copy_codes")}</span>
                      </>
                    )}
                  </button>
                </div>
                <p className="mt-1 text-xs text-amber-800">
                  {t("settings:account.backup_hint")}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-1 font-mono text-xs text-amber-950">
                  {backupCodes.map((code) => (
                    <span key={code} dir="ltr">
                      {code}
                    </span>
                  ))}
                </div>
              </div>
              <button
                type="button"
                onClick={finishEnroll}
                className="w-full rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700"
              >
                {t("settings:account.backup_done")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
