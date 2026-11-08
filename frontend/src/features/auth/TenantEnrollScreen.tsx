import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "./authStore";

/**
 * Tenant Owner / Staff mandatory TOTP enrolment screen.
 * Mirrors PlatformEnrollScreen.tsx at route /login/enroll.
 * Open only when flagged with totp_enrollment_required.
 */
export function TenantEnrollScreen(): ReactElement {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const setSession = useAuthStore((state) => state.setSession);

  const [secret, setSecret] = useState<string | null>(null);
  const [otpauthUri, setOtpauthUri] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number>(
    () => 30 - (Math.floor(Date.now() / 1000) % 30),
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsLeft(30 - (Math.floor(Date.now() / 1000) % 30));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!accessToken) {
      navigate("/login", { replace: true });
      return;
    }

    let cancelled = false;
    fetch("/api/v1/auth/totp/enroll", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      credentials: "include",
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to start enrolment");
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setSecret(data.secret);
        setOtpauthUri(data.otpauth_uri);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not start enrolment. Please sign in again.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken, navigate]);

  const handleConfirm = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!accessToken) return;

    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/auth/totp/enroll/confirm", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        credentials: "include",
        body: JSON.stringify({ code: code.trim() }),
      });

      if (!res.ok) {
        throw new Error("Invalid code");
      }

      const data = await res.json();
      setBackupCodes(data.backup_codes);
      if (user) {
        setSession(accessToken, { ...user });
      }
    } catch {
      setError(
        "That code did not match. Check the device clock and try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10"
      style={{
        fontFamily: "'Inter', 'Plus Jakarta Sans', system-ui, sans-serif",
      }}
    >
      <div className="w-full max-w-lg rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-5 flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-[#0E6B3A]" aria-hidden="true" />
          <div>
            <p
              className="text-lg font-bold leading-tight text-slate-900"
              style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
            >
              Enable two-factor authentication
            </p>
            <p className="text-xs text-slate-500">
              Required for security compliance before opening your lab console.
            </p>
          </div>
        </div>

        {backupCodes ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">
                Save these backup codes now
              </p>
              <p className="mt-1 text-xs text-amber-800">
                Each code works once. They are shown only on this screen.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-1 font-mono text-xs text-amber-950">
                {backupCodes.map((backupCode) => (
                  <span key={backupCode}>{backupCode}</span>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                navigate(user?.role === "owner" ? "/" : "/invoices", {
                  replace: true,
                })
              }
              className="w-full rounded-lg bg-[#0E6B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0A522C]"
            >
              I have saved my codes — continue
            </button>
          </div>
        ) : (
          <form onSubmit={handleConfirm} className="space-y-4" noValidate>
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
                <p className="mt-2 text-[11px] text-slate-500">
                  Manual key:{" "}
                  <span className="font-mono text-slate-800">{secret}</span>
                </p>
              ) : null}
            </div>

            <div>
              <div className="mb-2 rounded-lg border border-teal-200 bg-teal-50/80 p-3">
                <p className="text-xs font-medium text-teal-950">
                  Enter the code for{" "}
                  <strong className="font-semibold text-slate-900">
                    {user?.email || "your account"}
                  </strong>
                </p>
                <div className="mt-1 flex items-center justify-between text-[11px] text-teal-800">
                  <span>Current code valid for</span>
                  <span className="font-mono font-bold text-teal-900">
                    {secondsLeft}s
                  </span>
                </div>
              </div>
              <label
                htmlFor="enroll-code"
                className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                Code from the app
              </label>
              <input
                id="enroll-code"
                inputMode="numeric"
                required
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-center font-mono text-lg tracking-[0.4em] focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
                placeholder="000000"
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
              disabled={busy || !secret}
              className="w-full rounded-lg bg-[#0E6B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0A522C] disabled:opacity-60"
            >
              {busy ? "Activating…" : "Activate two-factor"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
