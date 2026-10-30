import React, { useState, useRef } from "react";
import {
  Loader2,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  ArrowLeft,
  KeyRound,
} from "lucide-react";
import type { AuthService, LoginSuccessSession } from "./types";
import { defaultAuthService } from "./authService";
import { GENERIC_AUTH_ERROR } from "./authStore";

export interface TwoFactorAuthScreenProps {
  email?: string;
  tenantName?: string;
  terminalId?: string;
  authService?: AuthService;
  onSuccess?: (session: LoginSuccessSession) => void;
  onBack?: () => void;
}

export function TwoFactorAuthScreen({
  email = "ali.raza@citylab.pk",
  tenantName = "City Diagnostic Lab — Lahore",
  terminalId = "PK-LHE-04",
  authService = defaultAuthService,
  onSuccess,
  onBack,
}: TwoFactorAuthScreenProps): JSX.Element {
  const [digits, setDigits] = useState<string[]>(["", "", "", "", "", ""]);
  const [isBackupMode, setIsBackupMode] = useState<boolean>(false);
  const [backupCode, setBackupCode] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  const handleDigitChange = (index: number, value: string): void => {
    const cleanVal = value.replace(/[^0-9]/g, "");
    if (!cleanVal) {
      const next = [...digits];
      next[index] = "";
      setDigits(next);
      return;
    }

    const digit = cleanVal.slice(-1);
    const next = [...digits];
    next[index] = digit;
    setDigits(next);

    // Auto-advance focus to next digit
    if (index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (
    index: number,
    e: React.KeyboardEvent<HTMLInputElement>,
  ): void => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>): void => {
    e.preventDefault();
    const pasted = e.clipboardData
      .getData("text")
      .replace(/[^0-9]/g, "")
      .slice(0, 6);
    if (!pasted) return;

    const next = [...digits];
    for (let i = 0; i < 6; i++) {
      next[i] = pasted[i] ?? "";
    }
    setDigits(next);

    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();
  };

  const handleVerify = async (): Promise<void> => {
    const code = isBackupMode ? backupCode.trim() : digits.join("");
    if (!code) return;

    setIsLoading(true);
    setError(null);

    try {
      const session = await authService.verifyTotp({
        code,
        isBackupCode: isBackupMode,
      });
      onSuccess?.(session);
    } catch {
      setError(GENERIC_AUTH_ERROR);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-[#faf8ff] p-4 text-[#131b2e] selection:bg-[#86f2e4]">
      {/* Background radial gradient */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-teal-500/10 via-[#faf8ff] to-[#faf8ff] z-0" />

      <main className="relative z-10 w-full max-w-[420px] bg-white rounded-xl shadow-md border border-slate-100 p-6 flex flex-col gap-4">
        {/* Brand Header */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-teal-700 flex items-center justify-center text-white shadow-sm">
              <KeyRound className="w-4 h-4" />
            </div>
            <span className="text-xl font-bold tracking-tight text-slate-900">
              LabFlow
            </span>
          </div>
          <div className="flex items-center gap-1.5 bg-slate-100 px-2 py-1 rounded text-xs font-mono text-slate-600">
            <span className="uppercase tracking-wider text-teal-800 font-semibold">
              Portal
            </span>
            <span>•</span>
            <span>LIS v4.2</span>
          </div>
        </header>

        {/* Tenant & User Context Banner */}
        <section
          aria-label="Tenant and session identity"
          className="bg-slate-50 border border-slate-100 p-3 rounded-lg flex flex-col gap-1"
        >
          <div className="flex items-center gap-1.5 text-teal-800 font-medium text-xs">
            <span className="font-semibold text-slate-900">{tenantName}</span>
          </div>
          <div className="text-xs text-slate-500">
            Signing in as{" "}
            <strong className="font-medium text-slate-800">{email}</strong>
          </div>
        </section>

        {/* Title & Guidance */}
        <div className="flex flex-col gap-0.5">
          <h1 className="text-lg font-bold text-slate-900">
            Two-factor authentication
          </h1>
          <p className="text-xs text-slate-600">
            Enter the 6-digit code from your authenticator app.
          </p>
        </div>

        {/* Verification Inputs */}
        {!isBackupMode ? (
          <div className="flex flex-col gap-2">
            {/* 6-digit OTP Inputs */}
            <div
              className="flex items-center justify-between gap-2"
              id="otp-container"
            >
              {digits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => {
                    inputRefs.current[idx] = el;
                  }}
                  aria-label={`Digit ${idx + 1}`}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleDigitChange(idx, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(idx, e)}
                  onPaste={handlePaste}
                  className="w-12 h-12 text-center text-xl font-bold bg-slate-50 border border-slate-200 text-slate-900 rounded-lg outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-700/20 transition-all"
                />
              ))}
            </div>

            {/* Live sync / validity feedback hint */}
            <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-teal-600" />
                Time-synced TOTP
              </span>
              <span className="text-slate-500">SHA-1 / 30s</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="backup-code"
              className="text-xs font-medium text-slate-800"
            >
              Backup code
            </label>
            <input
              id="backup-code"
              type="text"
              placeholder="Enter backup code"
              value={backupCode}
              onChange={(e) => setBackupCode(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-lg px-3.5 py-2.5 outline-none focus:border-teal-700 focus:ring-1 focus:ring-teal-700 font-mono"
            />
          </div>
        )}

        {/* Mode Toggle Button */}
        <div className="text-right">
          <button
            type="button"
            onClick={() => {
              setIsBackupMode(!isBackupMode);
              setError(null);
            }}
            className="text-xs text-teal-700 hover:text-teal-900 font-medium transition-colors"
          >
            {isBackupMode ? "Use authenticator app" : "Use a backup code"}
          </button>
        </div>

        {/* Generic Error Notification */}
        {error && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 p-2.5 rounded-lg flex items-center gap-2 text-xs font-medium"
          >
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2 pt-1">
          <button
            type="button"
            disabled={isLoading}
            onClick={() => void handleVerify()}
            className="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 active:bg-teal-900 disabled:opacity-70 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Verifying...</span>
              </>
            ) : (
              <>
                <span>Verify Session</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          <button
            type="button"
            onClick={onBack}
            className="text-center text-xs text-slate-500 hover:text-slate-800 transition-colors py-1 flex items-center justify-center gap-1 cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to sign in</span>
          </button>
        </div>

        {/* Compliance / Node Security Footer */}
        <footer className="mt-2 bg-slate-50 border border-slate-100 rounded-lg p-2.5 flex items-center justify-between text-slate-600">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-teal-700" />
            <div className="flex flex-col">
              <span className="text-[11px] font-semibold text-slate-800 uppercase tracking-wide">
                ISO 15189 Certified Node
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                Encrypted Terminal {terminalId}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1 bg-white border border-slate-200 px-2 py-0.5 rounded text-[11px] font-mono text-slate-700">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-600" />
            <span>Secure</span>
          </div>
        </footer>
      </main>
    </div>
  );
}
