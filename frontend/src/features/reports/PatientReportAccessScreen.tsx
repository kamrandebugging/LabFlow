/**
 * Screen 28: Patient Report Access Screen (/report-access/:token).
 * Spec: Doc 03 §5.6 RP-8/RP-9, §6.8, 28-patient-report-access.html.
 * PUBLIC route: NO auth guard, the token is the sole credential.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Download, Lock, Shield } from "lucide-react";
import { reportsService } from "./reportsService";

export function PatientReportAccessScreen(): JSX.Element {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const [checking, setChecking] = useState(true);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState(
    "Verifying digital signature…",
  );

  const [serverError, setServerError] = useState<string | null>(null);

  const verify = async () => {
    if (!token) {
      navigate("/link-expired", { replace: true });
      return;
    }
    try {
      setChecking(true);
      setServerError(null);
      setStatusMessage("Verifying digital signature and security token…");
      const res = await reportsService.checkPublicReportAccess(token);

      if (res.status === 410 || res.status === 404) {
        // Token expired or revoked — navigate to Screen 29
        const phone = res.error?.details?.phone || null;
        navigate("/link-expired", {
          replace: true,
          state: { phone, reason: res.error?.code },
        });
        return;
      }

      if (res.status === 200) {
        setDownloadUrl(`/api/v1/report-access/${encodeURIComponent(token)}`);
        setStatusMessage("Official medical report verified and ready.");
      } else {
        setServerError(
          res.error?.message ||
            "Unable to connect to diagnostic server. Please try again.",
        );
        setStatusMessage("Verification failed.");
      }
    } catch {
      setServerError(
        "Network error connecting to diagnostic portal. Please check connection.",
      );
      setStatusMessage("Verification error.");
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    verify();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col justify-between items-center px-4 py-8">
      {/* Top Header */}
      <header className="w-full max-w-3xl flex flex-col sm:flex-row items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 font-bold">
            LF
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-900 leading-tight">
              City Diagnostic Lab
            </h1>
            <p className="text-xs text-slate-500">
              Central Pathology & Molecular Diagnostics
            </p>
          </div>
        </div>

        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-teal-50 border border-teal-200 text-teal-800 text-xs font-semibold">
          <Lock className="w-3.5 h-3.5 text-teal-700" />
          <span>Direct Token Access · Verified</span>
        </div>
      </header>

      {/* Main Container */}
      <main className="w-full max-w-3xl my-8 flex flex-col gap-6">
        {/* Status Strip */}
        <section
          aria-live="polite"
          className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col gap-3"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  checking
                    ? "bg-teal-600 animate-pulse"
                    : serverError
                      ? "bg-rose-600"
                      : "bg-emerald-600"
                }`}
              ></span>
              <span className="font-semibold text-slate-900 text-sm">
                {checking
                  ? "Opening your report…"
                  : serverError
                    ? "Connection Issue"
                    : "Diagnostic report ready"}
              </span>
            </div>
            <span className="text-xs text-slate-600">
              {serverError
                ? "Unable to complete digital signature check."
                : "Your official diagnostic document is ready for viewing & download."}
            </span>
          </div>

          {serverError && (
            <div
              role="alert"
              className="p-3 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between gap-3"
            >
              <span>{serverError}</span>
              <button
                type="button"
                onClick={verify}
                className="px-3 py-1 bg-white border border-rose-300 rounded font-semibold text-rose-800 hover:bg-rose-100 transition-colors shrink-0"
              >
                Retry
              </button>
            </div>
          )}

          <div className="flex items-center justify-between text-xs text-slate-600 pt-1 border-t border-slate-100">
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <Shield
                className="w-3.5 h-3.5 text-teal-700"
                aria-hidden="true"
              />
              <span>{statusMessage}</span>
            </div>
            <span className="font-mono text-[11px] text-slate-600">
              {checking
                ? "Checking…"
                : serverError
                  ? "Error"
                  : "Status: 200 OK"}
            </span>
          </div>
          <div role="status" aria-live="polite" className="sr-only">
            {statusMessage}
          </div>
        </section>

        {/* Clinical Document Card */}
        <article className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 sm:p-10 flex flex-col gap-6 relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b-2 border-slate-800">
            <div>
              <h2 className="text-xl font-bold uppercase tracking-tight text-slate-900">
                Official Clinical Report
              </h2>
              <p className="text-xs text-slate-600 mt-0.5">
                Official Clinical Report
              </p>
            </div>

            {downloadUrl && (
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Download Official PDF (opens in a new tab)"
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2"
              >
                <Download className="w-4 h-4" aria-hidden="true" />
                <span>Download Official PDF</span>
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            )}
          </div>

          {/* Report Information Overview */}
          <div className="p-5 bg-slate-50 rounded-xl border border-slate-200 text-xs flex flex-col sm:flex-row justify-between gap-4">
            <div>
              <span className="text-slate-400 font-medium uppercase block text-[10px]">
                Authentication
              </span>
              <span className="font-semibold text-slate-800 text-sm block mt-0.5">
                Authenticated Patient Token
              </span>
              <span className="text-slate-500">
                Expires after validity window for patient privacy.
              </span>
            </div>
            <div className="sm:text-right">
              <span className="text-slate-400 font-medium uppercase block text-[10px]">
                Support
              </span>
              <span className="text-slate-700 block mt-0.5 font-medium">
                City Diagnostic Lab Helpdesk
              </span>
              <span className="text-teal-700 font-mono">+92 42 35712345</span>
            </div>
          </div>

          {/* Guidance note */}
          <div className="text-xs text-slate-500 leading-relaxed border-t border-slate-100 pt-4">
            <p>
              Please review these diagnostic findings with your consulting
              physician. If you suspect any discrepancies or require an updated
              copy, contact the front desk at City Diagnostic Lab.
            </p>
          </div>
        </article>
      </main>

      {/* Muted Footer */}
      <footer className="w-full max-w-3xl text-center text-xs text-slate-400 pt-4">
        City Diagnostic Lab · End-to-End Encrypted Access
      </footer>
    </div>
  );
}
