import type { ReactElement } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldAlert } from "lucide-react";

import { useAuthStore } from "./authStore";

/**
 * One-time "change your password" warning shown after a staff member signs in
 * while still on the provisioning-issued temporary master credential.
 *
 * Rendered once from the tenant shell; dismissing it only hides it for the
 * current mount. The persistent amber banner lives on the Account & Security
 * screen until the password is actually changed.
 */
export function MustChangePasswordModal(): ReactElement | null {
  const { t } = useTranslation(["auth", "common"]);
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const [dismissed, setDismissed] = useState(false);

  if (!user?.must_change_password || dismissed) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-label={t("auth:modal.title")}
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 rounded-full bg-amber-50 flex items-center justify-center shrink-0">
            <ShieldAlert className="h-6 w-6 text-amber-600" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              {t("auth:modal.title")}
            </h2>
            <p className="text-sm text-slate-600 mt-1">
              {t("auth:modal.body")}
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-sm font-medium transition-colors"
          >
            {t("auth:modal.later")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/settings/account")}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
          >
            <span className="material-symbols-outlined text-[18px]">lock</span>
            <span>{t("auth:modal.now")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
