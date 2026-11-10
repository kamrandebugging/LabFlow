import React, { useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useAuthStore } from "../auth/authStore";
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
  const user = useAuthStore((s) => s.user);
  const setSession = useAuthStore((s) => s.setSession);

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
      setPasswordError("New password must be at least 12 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }

    setPasswordBusy(true);
    try {
      await accountService.changePassword(currentPassword, newPassword);
      setPasswordSuccess("Password changed successfully.");

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
          ? err.message
          : "Failed to change password.",
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
          ? err.message
          : "Could not start enrolment.",
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
      setTotpNotice("Two-factor authentication enabled.");
    } catch (err: unknown) {
      setTotpError(
        err instanceof AccountApiError
          ? err.message
          : "That code did not match. Check the device clock and try again.",
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
      await accountService.disableTotp(disablePassword);
      setTotpEnabled(false);
      setDisableOpen(false);
      setDisablePassword("");
      setTotpNotice("Two-factor authentication disabled.");
    } catch (err: unknown) {
      setTotpError(
        err instanceof AccountApiError
          ? err.message
          : "Could not disable two-factor authentication.",
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
            <span>Settings</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="text-teal-700 font-medium">
              Account &amp; Security
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Account &amp; Security
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Manage your password and two-factor authentication
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
            <p className="font-semibold">You are using a temporary password</p>
            <p className="text-amber-800 mt-0.5">
              Change it now to keep your lab account secure. Your temporary
              credential will be invalidated automatically.
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
            <span>Change Password</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Set a personal password to replace any temporary credential.
          </p>
        </div>

        <div className="p-6 space-y-6 text-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
            <label
              htmlFor="current_password"
              className="block font-semibold text-slate-900"
            >
              Current Password
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
                New Password
              </label>
              <p className="text-xs text-slate-500 mt-0.5">
                At least 12 characters.
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
              Confirm New Password
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
              <span>{passwordBusy ? "Updating..." : "Update Password"}</span>
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
            <span>Two-Factor Authentication</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Add an extra layer of security using an authenticator app.
          </p>
        </div>

        <div className="p-6 space-y-4 text-sm">
          {/* Enable flow */}
          {!totpEnabled && !enrollOpen && (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold text-slate-900">Status: Off</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Your account is protected by password only.
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
                <span>Enable</span>
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
                  <p className="font-semibold text-slate-900">Status: On</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Two-factor authentication is active.
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
                <span>Disable</span>
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
                Enter your current password to disable two-factor
                authentication.
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder="Current password"
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
                    {disableBusy ? "Disabling..." : "Confirm Disable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDisableOpen(false)}
                    className="px-4 py-2 border border-red-300 text-red-700 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors"
                  >
                    Cancel
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
                  Add this account to your authenticator
                </p>
                {otpauthUri ? (
                  <p className="mt-2 break-all font-mono text-[11px] text-slate-700">
                    {otpauthUri}
                  </p>
                ) : (
                  <p className="mt-2 text-xs text-slate-500">Preparing…</p>
                )}
                {secret ? (
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <p className="text-[11px] text-slate-500">
                      Manual key:{" "}
                      <span className="font-mono text-slate-800 font-medium select-all">
                        {secret}
                      </span>
                    </p>
                    <button
                      type="button"
                      onClick={handleCopyKey}
                      className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-100 transition-colors"
                      title="Copy manual key"
                    >
                      {copiedKey ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                          <span className="text-emerald-700 font-bold">
                            Copied
                          </span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5 text-slate-500" />
                          <span>Copy key</span>
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
                  Code from the app
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
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={enrollBusy || !secret}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-all disabled:opacity-60"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    shield
                  </span>
                  <span>{enrollBusy ? "Activating..." : "Activate"}</span>
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
                    Save these backup codes now
                  </p>
                  <button
                    type="button"
                    onClick={handleCopyCodes}
                    className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-950 hover:bg-amber-100/70 transition-colors"
                    title="Copy all backup codes"
                  >
                    {copiedCodes ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                        <span className="text-emerald-700 font-bold">
                          Copied
                        </span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-amber-800" />
                        <span>Copy codes</span>
                      </>
                    )}
                  </button>
                </div>
                <p className="mt-1 text-xs text-amber-800">
                  Each code works once. They are shown only here.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-1 font-mono text-xs text-amber-950">
                  {backupCodes.map((code) => (
                    <span key={code}>{code}</span>
                  ))}
                </div>
              </div>
              <button
                type="button"
                onClick={finishEnroll}
                className="w-full rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700"
              >
                I have saved my codes — done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
