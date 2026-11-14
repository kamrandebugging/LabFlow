import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2,
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import type { AuthService, AuthUser, LoginSuccessSession } from "./types";
import { defaultAuthService } from "./authService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";

export interface StaffLoginScreenProps {
  tenantName?: string;
  nodeId?: string;
  authService?: AuthService;
  onSuccess?: (session: LoginSuccessSession) => void;
  onTotpRequired?: (email: string, challengeToken?: string) => void;
  onTotpEnrollmentRequired?: (session: LoginSuccessSession) => void;
  /** An already-restored session must be surfaced, never silently resumed. */
  currentUser?: AuthUser | null;
  onContinue?: () => void;
  onLogInAsSomeoneElse?: () => void | Promise<void>;
}

export function StaffLoginScreen({
  tenantName,
  nodeId,
  authService = defaultAuthService,
  onSuccess,
  onTotpRequired,
  onTotpEnrollmentRequired,
  currentUser,
  onContinue,
  onLogInAsSomeoneElse,
}: StaffLoginScreenProps): JSX.Element {
  const { t } = useTranslation(["auth", "common"]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showResetNotice, setShowResetNotice] = useState(false);
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState<boolean>(
    () => {
      if (typeof window === "undefined") return false;
      const params = new URLSearchParams(window.location.search);
      return params.get("reason") === "session_expired";
    },
  );

  const activeName =
    currentUser?.name ||
    currentUser?.display_name ||
    currentUser?.email ||
    currentUser?.id;

  useEffect(() => {
    if (sessionExpiredNotice && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("reason");
      window.history.replaceState(
        {},
        document.title,
        url.pathname + (url.search ? url.search : ""),
      );
    }
  }, [sessionExpiredNotice]);

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    e.preventDefault();
    if (!email || !password) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await authService.login({ email, password });
      if (result.totpRequired) {
        if (result.challengeToken) {
          onTotpRequired?.(email, result.challengeToken);
        } else {
          onTotpRequired?.(email);
        }
        return;
      }

      if (result.session) {
        if (
          result.totpEnrollmentRequired ||
          result.session.totp_enrollment_required
        ) {
          onTotpEnrollmentRequired?.(result.session);
          return;
        }
        onSuccess?.(result.session);
        return;
      }
    } catch {
      setError(t("auth:errors.generic"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-[#faf8ff] p-4 text-[#131b2e] selection:bg-[#86f2e4]">
      {/* Background radial gradient */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-teal-500/10 via-[#faf8ff] to-[#faf8ff] z-0" />

      {/* Language Switcher */}
      <aside
        aria-label={t("auth:login.language_aria")}
        className="fixed top-6 end-6 z-50"
      >
        <LanguageSwitcher className="bg-slate-200/80 backdrop-blur-md shadow-sm" />
      </aside>

      <main className="relative z-10 w-full max-w-[420px] bg-white rounded-xl shadow-sm border border-slate-100 p-8 flex flex-col">
        {/* Brand Header */}
        <header className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <img
              src="/logo.svg"
              alt="LabFlow"
              className="w-9 h-9 object-contain"
            />
            <div className="flex items-baseline gap-1.5">
              <span className="text-xl font-bold tracking-tight text-slate-900">
                LabFlow
              </span>
              <span className="text-xs font-medium text-slate-500">
                LIS v4.2
              </span>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs uppercase tracking-wider font-semibold">
            {t("auth:login.portal")}
          </span>
        </header>

        {/* Tenant Banner (only rendered when tenant is resolved) */}
        {tenantName && (
          <section
            aria-label={t("auth:login.lab_node_details")}
            className="mb-6 bg-slate-50 border border-slate-100 rounded-lg p-3"
          >
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                  {tenantName}
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("auth:login.staff_sign_in")}
                </p>
              </div>
              {nodeId && (
                <span className="inline-flex items-center gap-1 text-xs text-teal-800 px-1.5 py-0.5 rounded bg-teal-100/70 font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-600 animate-pulse" />
                  {nodeId}
                </span>
              )}
            </div>
          </section>
        )}

        {/* Session Expired Notice */}
        {sessionExpiredNotice && (
          <div
            role="status"
            className="mb-4 flex items-center justify-between gap-2 py-2.5 px-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-xs font-medium"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <span>{t("auth:login.session_expired")}</span>
            </div>
            <button
              type="button"
              onClick={() => setSessionExpiredNotice(false)}
              className="text-amber-700 hover:text-amber-900 font-semibold"
              aria-label={t("auth:login.dismiss_session_expired")}
            >
              ✕
            </button>
          </div>
        )}

        {currentUser ? (
          <section
            role="status"
            aria-label={t("auth:login.session_active_aria")}
            className="flex flex-col gap-4 rounded-lg border border-teal-200 bg-teal-50/70 p-4"
          >
            <div>
              <h2 className="text-sm font-semibold text-teal-950">
                {t("auth:login.session_active_title")}
              </h2>
              <p className="mt-1 text-sm text-teal-900">
                {t("auth:login.session_active_message", {
                  name: activeName,
                  role: t(`common:role.${currentUser.role}`),
                })}
              </p>
              <p className="mt-2 text-xs text-teal-800">
                {t("auth:login.session_active_hint")}
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={onContinue}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-teal-800"
              >
                <span>{t("auth:login.continue_session")}</span>
                <ArrowRight className="w-4 h-4 rtl:rotate-180" />
              </button>
              <button
                type="button"
                onClick={() => void onLogInAsSomeoneElse?.()}
                className="flex-1 rounded-lg border border-teal-700/30 bg-white px-4 py-2.5 text-sm font-medium text-teal-800 transition-colors hover:bg-teal-100"
              >
                {t("auth:login.log_in_as_someone_else")}
              </button>
            </div>
          </section>
        ) : (
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="flex flex-col space-y-4"
            noValidate={false}
          >
            {/* Email field */}
            <div className="flex flex-col space-y-1.5">
              <label
                htmlFor="email"
                className="text-xs font-medium text-slate-800 flex justify-between items-center"
              >
                <span>{t("auth:login.email")}</span>
                <span className="text-[11px] text-slate-400">
                  {t("auth:login.email_hint")}
                </span>
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                placeholder={t("auth:login.email_placeholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-white text-slate-900 text-sm rounded-lg border border-slate-200 px-3.5 py-2.5 outline-none transition-all focus:border-teal-600 focus:ring-1 focus:ring-teal-600 placeholder:text-slate-400 shadow-sm"
              />
            </div>

            {/* Password field */}
            <div className="flex flex-col space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="password"
                  className="text-xs font-medium text-slate-800"
                >
                  {t("auth:login.password")}
                </label>
                <button
                  type="button"
                  onClick={() => setShowResetNotice(true)}
                  className="text-xs text-teal-700 hover:text-teal-900 transition-colors"
                >
                  {t("auth:login.reset_via_admin")}
                </button>
              </div>
              <div className="relative flex items-center">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder={t("auth:login.password_placeholder")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-white text-slate-900 text-sm rounded-lg border border-slate-200 ps-3.5 pe-10 py-2.5 outline-none transition-all focus:border-teal-600 focus:ring-1 focus:ring-teal-600 placeholder:text-slate-400 shadow-sm text-start"
                />
                <button
                  type="button"
                  aria-label={t("auth:login.toggle_password")}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute end-2.5 p-1 rounded text-slate-400 hover:text-slate-700 focus:outline-none"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Reset Notice Modal / Banner */}
            {showResetNotice && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex flex-col gap-1.5">
                <p>{t("auth:login.reset_help")}</p>
                <button
                  type="button"
                  onClick={() => setShowResetNotice(false)}
                  className="self-end text-[11px] text-amber-700 font-semibold underline hover:text-amber-900"
                >
                  {t("common:actions.dismiss")}
                </button>
              </div>
            )}

            {/* Submit Button */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-teal-700 hover:bg-teal-800 active:bg-teal-900 disabled:opacity-70 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 px-4 rounded-lg transition-colors shadow-sm flex items-center justify-center gap-2 cursor-pointer"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{t("auth:login.authenticating")}</span>
                  </>
                ) : (
                  <>
                    <span>{t("auth:login.sign_in")}</span>
                    <ArrowRight className="w-4 h-4 rtl:rotate-180" />
                  </>
                )}
              </button>
            </div>

            {/* Generic Error Notice */}
            {error && (
              <div
                role="alert"
                className="flex items-center justify-center gap-2 py-2 px-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs font-medium transition-all"
              >
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </form>
        )}

        {/* Compliance Footer */}
        <footer className="mt-8 pt-5 border-t border-slate-100 text-center">
          <div className="flex items-center justify-center gap-1.5 text-slate-500 mb-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-700" />
            <span className="text-[11px] font-semibold tracking-wide uppercase">
              {t("auth:login.secured_node")}
            </span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            {t("auth:login.compliance")}
          </p>
        </footer>
      </main>
    </div>
  );
}
