import type { ReactElement } from "react";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { usePlatformAuthStore } from "./platformAuthStore";

export function PlatformTotpScreen(): ReactElement {
  const navigate = useNavigate();
  const verifyTotp = usePlatformAuthStore((state) => state.verifyTotp);
  const error = usePlatformAuthStore((state) => state.error);
  const isLoading = usePlatformAuthStore((state) => state.isLoading);
  const pendingEmail = usePlatformAuthStore((state) => state.pendingEmail);
  const platformUser = usePlatformAuthStore((state) => state.platformUser);
  const [code, setCode] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const ok = await verifyTotp(code.trim());
    if (!ok) return;
    const enrolled = usePlatformAuthStore.getState().platformUser?.totp_enabled;
    navigate(enrolled ? "/platform/overview" : "/platform/enroll", {
      replace: true,
    });
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center bg-slate-950 px-4"
      style={{
        fontFamily: "'Inter', 'Plus Jakarta Sans', system-ui, sans-serif",
      }}
    >
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-6 flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-[#0E6B3A]" aria-hidden="true" />
          <div>
            <p
              className="text-lg font-bold leading-tight text-slate-900"
              style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
            >
              Two-factor verification
            </p>
            <p className="text-xs text-slate-500">
              {pendingEmail ?? platformUser?.email ?? ""}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label
              htmlFor="platform-totp-code"
              className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
            >
              Authenticator code
            </label>
            <input
              id="platform-totp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-center font-mono text-lg tracking-[0.4em] focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
              placeholder="000000"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              A single-use backup code also works here.
            </p>
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
            {isLoading ? "Verifying…" : "Verify"}
          </button>
        </form>

        <Link
          to="/platform/login"
          className="mt-6 block text-xs font-medium text-slate-500 hover:text-slate-800"
        >
          ← Back to sign in
        </Link>
      </div>
    </div>
  );
}
