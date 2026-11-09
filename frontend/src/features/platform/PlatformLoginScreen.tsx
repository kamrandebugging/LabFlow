import type { ReactElement } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { usePlatformAuthStore } from "./platformAuthStore";

export function PlatformLoginScreen(): ReactElement {
  const navigate = useNavigate();
  const login = usePlatformAuthStore((state) => state.login);
  const error = usePlatformAuthStore((state) => state.error);
  const isLoading = usePlatformAuthStore((state) => state.isLoading);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = await login(email.trim(), password);
    if (result.kind === "totp") {
      navigate("/platform/login/2fa", { replace: true });
    } else if (result.kind === "session") {
      navigate("/platform/overview", { replace: true });
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center bg-slate-950 px-4"
      style={{
        fontFamily: "'Inter', 'Plus Jakarta Sans', system-ui, sans-serif",
      }}
    >
      <div className="w-full max-w-sm rounded-xl bg-surface-container-lowest p-8 shadow-xl border border-outline-variant/40">
        <div className="mb-6 flex items-center gap-3">
          <img
            src="/logo.svg"
            alt="LabFlow"
            className="h-8 w-8 rounded object-contain"
          />
          <div>
            <p
              className="text-lg font-bold leading-tight text-on-surface"
              style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
            >
              LabFlow Platform
            </p>
            <p className="text-[11px] uppercase tracking-widest text-primary font-semibold">
              Apex Master Console
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label
              htmlFor="platform-email"
              className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
            >
              Operator email
            </label>
            <input
              id="platform-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
            />
          </div>

          <div>
            <label
              htmlFor="platform-password"
              className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
            >
              Password
            </label>
            <input
              id="platform-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
            />
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-[#0E6B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0A522C] disabled:opacity-60"
          >
            {isLoading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-[11px] leading-relaxed text-slate-500">
          Super Admin accounts are global: they are not scoped to any tenant and
          carry no tenant claim. TOTP enrolment is mandatory before any write.
        </p>
      </div>
    </div>
  );
}
