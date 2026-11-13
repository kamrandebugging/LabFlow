/**
 * Screen 29: Link Expired Screen (/link-expired).
 * Spec: Doc 03 §5.6 RP-9, 29-link-expired.html.
 * Icons: lucide-react exclusively. No emojis.
 *
 * The lab phone is only rendered when the API supplied one (410 details).
 * There is no invented fallback number.
 */

import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Clock, Phone, ArrowLeft } from "lucide-react";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";

export function LinkExpiredScreen(): JSX.Element {
  const { t } = useTranslation(["reports", "common"]);
  const location = useLocation();
  const state = location.state as
    { phone?: string | null; reason?: string } | undefined;
  const labPhone = state?.phone?.trim() || null;

  return (
    <div className="bg-slate-50 text-slate-900 min-h-screen flex flex-col justify-between items-center px-4 py-8">
      {/* Brand Indicator */}
      <header className="w-full max-w-md pt-4 sm:pt-8 flex justify-between items-center gap-3">
        <div className="inline-flex items-center gap-2.5 text-slate-700">
          <div className="w-8 h-8 rounded-lg bg-teal-50 border border-teal-200/70 flex items-center justify-center text-teal-700 font-bold text-xs">
            LF
          </div>
          <span className="font-semibold text-sm tracking-tight text-slate-800">
            {t("common:brand.labflow")}
          </span>
        </div>
        <LanguageSwitcher compact />
      </header>

      {/* Centered Calm Minimal Card */}
      <main className="w-full max-w-md my-auto">
        <div className="bg-white border border-slate-200 rounded-2xl p-8 sm:p-10 shadow-sm text-center">
          {/* Calm Icon Badge */}
          <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500 mb-6">
            <Clock className="w-6 h-6 text-slate-600" />
          </div>

          {/* Headline */}
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mb-3">
            {t("reports:expired.title")}
          </h1>

          {/* Guidance */}
          <p className="text-slate-600 text-sm leading-relaxed mb-6">
            {t("reports:expired.guidance")}
          </p>

          {/* Lab Contact Box — only when the API supplied a real phone */}
          {labPhone && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-8 text-start">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
                {t("common:brand.labflow")}
              </div>
              <div className="flex items-center justify-between gap-3">
                <a
                  href={`tel:${labPhone.replace(/\s+/g, "")}`}
                  className="text-slate-900 font-semibold text-base hover:text-teal-700 transition-colors flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-teal-600 rounded"
                >
                  <Phone className="w-4 h-4 text-teal-600" />
                  <bdi dir="ltr">{labPhone}</bdi>
                </a>
                <span className="text-xs text-slate-500 font-medium">
                  {t("reports:expired.front_desk")}
                </span>
              </div>
            </div>
          )}

          {/* Back to Home Action */}
          <div>
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-teal-600 hover:text-teal-700 transition-colors focus:outline-none focus:underline"
            >
              <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
              {t("reports:expired.back_home")}
            </Link>
          </div>
        </div>
      </main>

      {/* Muted Footer */}
      <footer className="w-full max-w-md pb-4 text-center">
        <p className="text-xs text-slate-400">{t("common:brand.labflow")}</p>
      </footer>
    </div>
  );
}
