import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2,
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import type { AuthService, LoginSuccessSession } from "./types";
import { defaultAuthService } from "./authService";
import { GENERIC_AUTH_ERROR } from "./authStore";

export interface StaffLoginScreenProps {
  tenantName?: string;
  nodeId?: string;
  authService?: AuthService;
  onSuccess?: (session: LoginSuccessSession) => void;
  onTotpRequired?: (email: string) => void;
}

export function StaffLoginScreen({
  tenantName = "City Diagnostic Lab — Lahore",
  nodeId = "PK-LHE-01",
  authService = defaultAuthService,
  onSuccess,
  onTotpRequired,
}: StaffLoginScreenProps): JSX.Element {
  const { i18n } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showResetNotice, setShowResetNotice] = useState(false);

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
        onTotpRequired?.(email);
        return;
      }

      if (result.session) {
        onSuccess?.(result.session);
        return;
      }
    } catch {
      setError(GENERIC_AUTH_ERROR);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLanguageChange = (lang: "en" | "ur"): void => {
    void i18n.changeLanguage(lang);
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-[#faf8ff] p-4 text-[#131b2e] selection:bg-[#86f2e4]">
      {/* Background radial gradient */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-teal-500/10 via-[#faf8ff] to-[#faf8ff] z-0" />

      {/* Language Switcher */}
      <aside
        aria-label="Language selection"
        className="fixed top-6 right-6 z-50"
      >
        <div className="bg-slate-200/80 backdrop-blur-md p-1 rounded-lg shadow-sm flex items-center space-x-1">
          <button
            type="button"
            onClick={() => handleLanguageChange("en")}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              i18n.language === "en"
                ? "bg-white text-[#131b2e] shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            English
          </button>
          <button
            type="button"
            onClick={() => handleLanguageChange("ur")}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              i18n.language === "ur"
                ? "bg-white text-[#131b2e] shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            اردو
          </button>
        </div>
      </aside>

      <main className="relative z-10 w-full max-w-[420px] bg-white rounded-xl shadow-sm border border-slate-100 p-8 flex flex-col">
        {/* Brand Header */}
        <header className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-lg bg-teal-700/10 flex items-center justify-center text-teal-800">
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path d="M10 2v7.31L4.1 19.34A2 2 0 0 0 5.8 22h12.4a2 2 0 0 0 1.7-2.66L14 9.31V2" />
                <path d="M8.5 2h7" />
                <path d="M7 16h10" />
              </svg>
            </div>
            <div className="flex items-baseline space-x-1.5">
              <span className="text-xl font-bold tracking-tight text-slate-900">
                LabFlow
              </span>
              <span className="text-xs font-medium text-slate-500">
                LIS v4.2
              </span>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs uppercase tracking-wider font-semibold">
            Portal
          </span>
        </header>

        {/* Tenant Banner */}
        <section
          aria-label="Lab node details"
          className="mb-6 bg-slate-50 border border-slate-100 rounded-lg p-3"
        >
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                {tenantName}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">Staff sign in</p>
            </div>
            <span className="inline-flex items-center gap-1 text-xs text-teal-800 px-1.5 py-0.5 rounded bg-teal-100/70 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-600 animate-pulse" />
              {nodeId}
            </span>
          </div>
        </section>

        {/* Login Form */}
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
              <span>Email</span>
              <span className="text-[11px] text-slate-400">
                Lab ID or Official Mail
              </span>
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              placeholder="staff@citylab.pk"
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
                Password
              </label>
              <button
                type="button"
                onClick={() => setShowResetNotice(true)}
                className="text-xs text-teal-700 hover:text-teal-900 transition-colors"
              >
                Reset via Lab Admin
              </button>
            </div>
            <div className="relative flex items-center">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                placeholder="Enter your security credentials"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-white text-slate-900 text-sm rounded-lg border border-slate-200 pl-3.5 pr-10 py-2.5 outline-none transition-all focus:border-teal-600 focus:ring-1 focus:ring-teal-600 placeholder:text-slate-400 shadow-sm"
              />
              <button
                type="button"
                aria-label="Toggle password visibility"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 p-1 rounded text-slate-400 hover:text-slate-700 focus:outline-none"
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
              <p>
                Please contact your Lab Supervisor or Technical Administrator to
                trigger an authorized credential reissue.
              </p>
              <button
                type="button"
                onClick={() => setShowResetNotice(false)}
                className="self-end text-[11px] text-amber-700 font-semibold underline hover:text-amber-900"
              >
                Dismiss
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
                  <span>Authenticating...</span>
                </>
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="w-4 h-4" />
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

        {/* Compliance Footer */}
        <footer className="mt-8 pt-5 border-t border-slate-100 text-center">
          <div className="flex items-center justify-center gap-1.5 text-slate-500 mb-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-700" />
            <span className="text-[11px] font-semibold tracking-wide uppercase">
              Secured Clinical Node
            </span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Authorized staff access only. Activity is monitored and logged under
            ISO 15189 compliance.
          </p>
        </footer>
      </main>
    </div>
  );
}
