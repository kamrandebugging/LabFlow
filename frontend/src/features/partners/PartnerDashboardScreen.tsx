import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Layers,
  Receipt,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { formatMoney, statusLabel } from "../../lib/format";
import { PartnerApiError, partnersService } from "./partnersService";
import type { PartnerDashboardData } from "./types";

export const PartnerDashboardScreen: React.FC = () => {
  const { t, i18n } = useTranslation(["partners", "common"]);
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "owner";

  const [dashboard, setDashboard] = useState<PartnerDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchDashboard = useCallback(async (): Promise<void> => {
    if (!id || !isOwner) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await partnersService.getPartnerDashboard(id);
      setDashboard(data);
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof PartnerApiError
          ? messageForError(err, t)
          : t("partners:errors.load_dashboard"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [id, isOwner, t]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  if (!isOwner) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 text-xs text-slate-600">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md text-center shadow-xs">
          <ShieldAlert className="w-8 h-8 text-amber-600 mx-auto mb-3" />
          <h2 className="text-sm font-bold text-slate-900 mb-1">
            {t("partners:dashboard.restricted_title")}
          </h2>
          <p className="text-slate-600 mb-4">
            {t("partners:dashboard.restricted_body")}
          </p>
          <Link
            to={`/partners/${id || ""}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 text-white rounded-lg font-semibold hover:bg-teal-700 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
            <span>{t("partners:dashboard.back_to_partner")}</span>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-teal-100 selection:text-teal-900">
      <main className="flex-1 p-6 md:p-8 max-w-6xl mx-auto w-full space-y-6">
        {/* BREADCRUMB */}
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-x-2">
            <Link
              to={`/partners/${id}`}
              className="hover:text-slate-800 transition-colors flex items-center gap-1 font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>{t("partners:nav.partner")}</span>
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 rtl:rotate-180" />
            <span className="font-medium text-slate-700">
              {dashboard?.partner_name || "..."}
            </span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 rtl:rotate-180" />
            <span className="text-slate-900 font-semibold">
              {t("partners:nav.dashboard")}
            </span>
          </div>
          <div className="text-slate-400 text-[11px] font-mono" dir="ltr">
            {t("partners:nav.record_id", { id })}
          </div>
        </div>

        {/* ERROR BANNER */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* HEADER */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">
              {t("partners:dashboard.title_prefix")}
              {" — "}
              <bdi dir="ltr">{dashboard?.partner_name || "..."}</bdi>
            </h1>
            <p className="text-xs text-slate-600 mt-1">
              {t("partners:dashboard.subtitle")}
            </p>
          </div>

          {/* Quick links */}
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/partners/${id}/rules`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <Layers className="w-3.5 h-3.5 text-slate-500" />
              <span>{t("partners:nav.rules")}</span>
            </Link>
            <Link
              to={`/partners/ledger?partner_id=${id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <Receipt className="w-3.5 h-3.5 text-slate-500" />
              <span>{t("partners:dashboard.ledger_entries")}</span>
            </Link>
            <Link
              to={`/settlements?partner_id=${id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <Wallet className="w-3.5 h-3.5 text-slate-500" />
              <span>{t("common:nav.settlements")}</span>
            </Link>
          </div>
        </div>

        {/* 4 SUMMARY KPI CARDS */}
        {isLoading ? (
          <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-xl border border-slate-200">
            {t("partners:dashboard.loading")}
          </div>
        ) : dashboard ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* YTD Earned */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-medium">
                    {t("partners:dashboard.ytd_earned")}
                  </span>
                  <Receipt className="w-4 h-4 text-slate-400" />
                </div>
                <div className="font-mono text-2xl font-bold text-slate-900 tracking-tight">
                  <bdi dir="ltr">{formatMoney(dashboard.ytd_earned, lang)}</bdi>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {t("partners:dashboard.ytd_earned_hint")}
                </p>
              </div>

              {/* YTD Settled */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-medium">
                    {t("partners:dashboard.ytd_settled")}
                  </span>
                  <Wallet className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="font-mono text-2xl font-bold text-slate-900 tracking-tight">
                  <bdi dir="ltr">
                    {formatMoney(dashboard.ytd_settled, lang)}
                  </bdi>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {t("partners:dashboard.ytd_settled_hint")}
                </p>
              </div>

              {/* Pending Total */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-medium">
                    {t("partners:dashboard.pending_total")}
                  </span>
                  <Clock className="w-4 h-4 text-amber-500" />
                </div>
                <div className="font-mono text-2xl font-bold text-slate-900 tracking-tight">
                  <bdi dir="ltr">
                    {formatMoney(dashboard.pending_total, lang)}
                  </bdi>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {t("partners:dashboard.pending_hint")}
                </p>
              </div>

              {/* Late Entries */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-medium">
                    {t("partners:dashboard.late_entries")}
                  </span>
                  <AlertCircle className="w-4 h-4 text-slate-400" />
                </div>
                <div className="font-mono text-2xl font-bold text-slate-900 tracking-tight">
                  {dashboard.late_entries}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {t("partners:dashboard.late_entries_hint")}
                </p>
              </div>
            </div>

            {/* SETTLEMENTS HISTORY CARD */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-slate-900">
                    {t("partners:shared.recent_settlements")}
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {t("partners:dashboard.recent_subtitle_before")}{" "}
                    <bdi dir="ltr">{dashboard.partner_name}</bdi>
                    {t("partners:dashboard.recent_subtitle_after")}
                  </p>
                </div>
                <Link
                  to={`/settlements?partner_id=${id}`}
                  className="text-xs font-medium text-teal-700 hover:text-teal-800 flex items-center gap-1"
                >
                  <span>{t("partners:dashboard.view_all")}</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>

              {dashboard.last_6_settlements.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  {t("partners:dashboard.empty")}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-start border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                        <th className="py-3 px-4 w-36 font-mono">
                          {t("partners:shared.period")}
                        </th>
                        <th className="py-3 px-4 w-40 text-end font-mono">
                          {t("partners:dashboard.total_pkr")}
                        </th>
                        <th className="py-3 px-4 w-32 text-center">
                          {t("common:labels.status")}
                        </th>
                        <th className="py-3 px-4 text-end w-28">
                          {t("common:labels.actions")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      {dashboard.last_6_settlements.map((s) => (
                        <tr
                          key={s.id}
                          className="hover:bg-slate-50/70 transition-colors"
                          data-testid={`settlement-row-${s.id}`}
                        >
                          <td className="py-3.5 px-4 font-mono font-medium text-slate-900">
                            <bdi dir="ltr">{s.period}</bdi>
                          </td>
                          <td className="py-3.5 px-4 text-end font-mono font-semibold text-slate-900">
                            <bdi dir="ltr">{formatMoney(s.total, lang)}</bdi>
                          </td>
                          <td className="py-3.5 px-4 text-center">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-teal-50 text-teal-700 border border-teal-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-teal-600"></span>
                              <span>
                                {statusLabel(
                                  "settlement",
                                  s.status.toLowerCase(),
                                  (key) => t(`common:${key}`),
                                )}
                              </span>
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-end">
                            <Link
                              to={`/settlements/${s.id}`}
                              className="text-teal-700 hover:text-teal-900 font-semibold"
                            >
                              {t("partners:dashboard.view_details")}
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
};
