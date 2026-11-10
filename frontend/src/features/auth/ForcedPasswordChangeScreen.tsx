import type { ReactElement } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "./authStore";
import { needsTotpEnrolment, roleHome } from "./access";
import { accountService, AccountApiError } from "../settings/accountService";

/**
 * Full-screen gate for a temporary-password session.
 *
 * The backend refuses business endpoints while `password_is_temporary` is true
 * (S7); this screen is the only route the user can meaningfully use. It is not
 * dismissible, unlike the old warning modal.
 */
export function ForcedPasswordChangeScreen(): ReactElement {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const setSession = useAuthStore((state) => state.setSession);
  const logout = useAuthStore((state) => state.logout);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    if (newPassword.length < 12) {
      setError("New password must be at least 12 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      await accountService.changePassword(currentPassword, newPassword);
      if (user) {
        setSession(accessToken ?? "", {
          ...user,
          must_change_password: false,
        });
      }
      if (needsTotpEnrolment(user?.role, user?.totp_enabled)) {
        navigate("/login/enroll", { replace: true });
      } else {
        navigate(roleHome(user?.role), { replace: true });
      }
    } catch (err: unknown) {
      setError(
        err instanceof AccountApiError
          ? err.message
          : "Could not change the password.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-50">
            <span className="material-symbols-outlined text-[24px] text-amber-600">
              lock
            </span>
          </span>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-900">
              Set your permanent password
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              You signed in with a temporary credential. Business screens stay
              locked until you replace it.
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
              Current temporary password
            </label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
              New password
            </label>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              At least 12 characters.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
              Confirm new password
            </label>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
            />
          </div>

          {error && (
            <p
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              {error}
            </p>
          )}

          <div className="flex items-center justify-between gap-3 pt-2">
            <button
              type="button"
              onClick={() => {
                void logout().then(() => navigate("/login", { replace: true }));
              }}
              className="text-xs font-semibold text-slate-500 hover:text-red-600"
            >
              Sign out
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-[#005c55] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#0f766e] disabled:opacity-60"
            >
              {busy ? "Saving…" : "Set password and continue"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
