/**
 * Screen 28: Patient Report Access Screen (/report-access/:token).
 * Spec: Doc 03 §5.6 RP-8/RP-9, §6.8, 28-patient-report-access.html.
 * PUBLIC route: NO auth guard, the token is the sole credential.
 * Icons: lucide-react exclusively. No emojis.
 *
 * Language: explicit choice → tenant report_default_language (when the public
 * response exposes it) → browser language → English. The PDF itself is not
 * re-rendered here; this only localises the access chrome.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download, Lock, Shield } from "lucide-react";
import { reportsService } from "./reportsService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { resolvePublicLanguage } from "../../i18n";

type MessageKey =
  | "reports:public.verifying"
  | "reports:public.verifying_token"
  | "reports:public.verified"
  | "reports:public.failed"
  | "reports:public.error";

export function PatientReportAccessScreen(): JSX.Element {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation(["reports", "common"]);

  const [checking, setChecking] = useState(true);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [statusKey, setStatusKey] = useState<MessageKey>(
    "reports:public.verifying",
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
      setStatusKey("reports:public.verifying_token");
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
        setStatusKey("reports:public.verified");
      } else {
        setServerError(t("reports:public.connect_error"));
        setStatusKey("reports:public.failed");
      }
    } catch {
      setServerError(t("reports:public.network_error"));
      setStatusKey("reports:public.error");
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    const preferred = resolvePublicLanguage();
    if (i18n.resolvedLanguage !== preferred) {
      void i18n.changeLanguage(preferred);
    }
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
              {t("common:brand.labflow")}
            </h1>
            <p className="text-xs text-slate-500">
              {t("reports:public.portal_subtitle")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <LanguageSwitcher compact />
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-teal-50 border border-teal-200 text-teal-800 text-xs font-semibold">
            <Lock className="w-3.5 h-3.5 text-teal-700" />
            <span>{t("reports:public.token_access")}</span>
          </div>
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
                  ? t("reports:public.opening")
                  : serverError
                    ? t("reports:public.connection_issue")
                    : t("reports:public.ready")}
              </span>
            </div>
            <span className="text-xs text-slate-600">
              {serverError
                ? t("reports:public.signature_check_failed")
                : t("reports:public.ready_detail")}
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
                {t("reports:public.retry")}
              </button>
            </div>
          )}

          <div className="flex items-center justify-between text-xs text-slate-600 pt-1 border-t border-slate-100">
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <Shield
                className="w-3.5 h-3.5 text-teal-700"
                aria-hidden="true"
              />
              <span>{t(statusKey)}</span>
            </div>
            <span className="font-mono text-[11px] text-slate-600">
              {checking
                ? t("reports:public.checking")
                : serverError
                  ? t("reports:public.error_short")
                  : t("reports:public.status_ok")}
            </span>
          </div>
          <div role="status" aria-live="polite" className="sr-only">
            {t(statusKey)}
          </div>
        </section>

        {/* Clinical Document Card */}
        <article className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 sm:p-10 flex flex-col gap-6 relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b-2 border-slate-800">
            <div>
              <h2 className="text-xl font-bold uppercase tracking-tight text-slate-900">
                {t("reports:public.official_report")}
              </h2>
              <p className="text-xs text-slate-600 mt-0.5">
                {t("reports:public.official_report")}
              </p>
            </div>

            {downloadUrl && (
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t("reports:public.download_pdf_aria")}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2"
              >
                <Download className="w-4 h-4" aria-hidden="true" />
                <span>{t("reports:public.download_pdf")}</span>
                <span className="sr-only">
                  {t("reports:public.opens_new_tab")}
                </span>
              </a>
            )}
          </div>

          {/* Report Information Overview */}
          <div className="p-5 bg-slate-50 rounded-xl border border-slate-200 text-xs flex flex-col sm:flex-row justify-between gap-4">
            <div>
              <span className="text-slate-400 font-medium uppercase block text-[10px]">
                {t("reports:public.authentication")}
              </span>
              <span className="font-semibold text-slate-800 text-sm block mt-0.5">
                {t("reports:public.authenticated_token")}
              </span>
              <span className="text-slate-500">
                {t("reports:public.expiry_note")}
              </span>
            </div>
            <div className="sm:text-end">
              <span className="text-slate-400 font-medium uppercase block text-[10px]">
                {t("reports:public.support")}
              </span>
              <span className="text-slate-700 block mt-0.5 font-medium">
                {t("reports:public.helpdesk")}
              </span>
            </div>
          </div>

          {/* Guidance note */}
          <div className="text-xs text-slate-500 leading-relaxed border-t border-slate-100 pt-4">
            <p>{t("reports:public.guidance")}</p>
          </div>
        </article>
      </main>

      {/* Muted Footer */}
      <footer className="w-full max-w-3xl text-center text-xs text-slate-400 pt-4">
        {t("reports:public.footer")}
      </footer>
    </div>
  );
}
