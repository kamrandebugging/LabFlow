import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Check, Copy, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "./authStore";
import { roleHome } from "./access";

/**
 * Tenant Owner / Staff mandatory TOTP enrolment screen.
 * Mirrors PlatformEnrollScreen.tsx at route /login/enroll.
 * Open only when flagged with totp_enrollment_required.
 */
export function TenantEnrollScreen(): ReactElement {
  const { t } = useTranslation(["auth", "common"]);
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
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number>(
    () => 30 - (Math.floor(Date.now() / 1000) % 30),
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsLeft(30 - (Math.floor(Date.now() / 1000) % 30));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleCopyKey = () => {
    if (secret) {
      void navigator.clipboard.writeText(secret);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  const handleCopyCodes = () => {
    if (backupCodes) {
      void navigator.clipboard.writeText(backupCodes.join("\n"));
      setCopiedCodes(true);
      setTimeout(() => setCopiedCodes(false), 2000);
    }
  };

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
        if (!res.ok) throw new Error("start_enrolment_failed");
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setSecret(data.secret);
        setOtpauthUri(data.otpauth_uri);
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("auth:enroll.start_failed"));
        }
      });

    return () => {
      cancelled = true;
    };
    // t changes identity on language switch; re-running would issue a NEW
    // enrolment secret, so this effect intentionally runs once per session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        throw new Error("invalid_code");
      }

      const data = await res.json();
      setBackupCodes(data.backup_codes);
      if (user) {
        setSession(accessToken, { ...user, totp_enabled: true });
      }
    } catch {
      setError(t("auth:enroll.code_mismatch"));
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
              {t("auth:enroll.title")}
            </p>
            <p className="text-xs text-slate-500">
              {t("auth:enroll.subtitle")}
            </p>
          </div>
        </div>

        {backupCodes ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-amber-900">
                  {t("auth:enroll.save_codes")}
                </p>
                <button
                  type="button"
                  onClick={handleCopyCodes}
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-950 hover:bg-amber-100/70 transition-colors shadow-xs"
                  title={t("auth:enroll.copy_title")}
                >
                  {copiedCodes ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="text-emerald-700 font-bold">
                        {t("common:toast.copied")}
                      </span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5 text-amber-800" />
                      <span>{t("auth:enroll.copy_codes")}</span>
                    </>
                  )}
                </button>
              </div>
              <p className="mt-1 text-xs text-amber-800">
                {t("auth:enroll.codes_once")}
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
                navigate(roleHome(user?.role), {
                  replace: true,
                })
              }
              className="w-full rounded-lg bg-[#0E6B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0A522C]"
            >
              {t("auth:enroll.codes_saved")}
            </button>
          </div>
        ) : (
          <form onSubmit={handleConfirm} className="space-y-4" noValidate>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t("auth:enroll.add_account")}
              </p>
              {otpauthUri ? (
                <p className="mt-2 break-all font-mono text-[11px] text-slate-700">
                  {otpauthUri}
                </p>
              ) : (
                <p className="mt-2 text-xs text-slate-500">
                  {t("auth:enroll.preparing")}
                </p>
              )}
              {secret ? (
                <div className="mt-2 flex items-center justify-between gap-2">
                  <p className="text-[11px] text-slate-500">
                    {t("auth:enroll.manual_key")}{" "}
                    <span className="font-mono text-slate-800 font-medium select-all">
                      {secret}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={handleCopyKey}
                    className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-xs"
                    title={t("auth:enroll.copy_key_title")}
                  >
                    {copiedKey ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                        <span className="text-emerald-700 font-semibold">
                          {t("common:toast.copied")}
                        </span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-slate-500" />
                        <span>{t("auth:enroll.copy_key")}</span>
                      </>
                    )}
                  </button>
                </div>
              ) : null}
            </div>

            <div>
              <div className="mb-2 rounded-lg border border-teal-200 bg-teal-50/80 p-3">
                <p className="text-xs font-medium text-teal-950">
                  {t("auth:enroll.enter_code_for")}{" "}
                  <strong className="font-semibold text-slate-900">
                    <bdi dir="ltr">
                      {user?.email || t("auth:enroll.your_account")}
                    </bdi>
                  </strong>
                </p>
                <div className="mt-1 flex items-center justify-between text-[11px] text-teal-800">
                  <span>{t("auth:enroll.valid_for")}</span>
                  <span className="font-mono font-bold text-teal-900">
                    {secondsLeft}s
                  </span>
                </div>
              </div>
              <label
                htmlFor="enroll-code"
                className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t("auth:enroll.code_label")}
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
              {busy ? t("auth:enroll.activating") : t("auth:enroll.activate")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
