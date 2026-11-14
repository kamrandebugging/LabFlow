import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import { DashboardDateLine } from "./DashboardUI";
import {
  fetchSampleStatusCounts,
  formatCount,
  formatPkr,
  isTodayInPkt,
  listAllInvoices,
  type SampleStatusCounts,
} from "./dashboardService";

interface DashboardStats {
  invoicesCount: number | null;
  invoicedTotal: number | null;
  collectionsTotal: number | null;
  samples: SampleStatusCounts | null;
  pendingApprovals: number | null;
  draftSettlements: number | null;
  exceptions: {
    total: number;
    lateTransfers: number;
    failedDeliveries: number;
    criticalUnacknowledged: number;
  } | null;
}

const INITIAL_STATS: DashboardStats = {
  invoicesCount: null,
  invoicedTotal: null,
  collectionsTotal: null,
  samples: null,
  pendingApprovals: null,
  draftSettlements: null,
  exceptions: null,
};

export function OwnerDashboardScreen(): ReactElement {
  const { t, i18n } = useTranslation("common");
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const loadRealData = async () => {
      if (!accessToken) return;

      const [
        invoicesResult,
        samplesResult,
        approvalsResult,
        settlementsResult,
        exceptionsResult,
      ] = await Promise.allSettled([
        listAllInvoices({ signal: controller.signal }),
        fetchSampleStatusCounts(controller.signal),
        resultsService.getApprovalsQueue(controller.signal),
        partnersService.getSettlements({
          status: "draft",
          signal: controller.signal,
        }),
        reportsService.getExceptions(controller.signal),
      ]);

      if (!active) return;

      let invoicesCount: number | null = null;
      let invoicedTotal: number | null = null;
      let collectionsTotal: number | null = null;
      if (invoicesResult.status === "fulfilled") {
        const todayInvoices = invoicesResult.value.filter((invoice) =>
          isTodayInPkt(invoice.created_at),
        );
        invoicesCount = todayInvoices.length;
        invoicedTotal = todayInvoices.reduce(
          (sum, invoice) => sum + Number.parseFloat(invoice.total || "0"),
          0,
        );
        const paidRows = todayInvoices
          .map((invoice) =>
            invoice.net_paid === undefined || invoice.net_paid === null
              ? null
              : Number.parseFloat(invoice.net_paid),
          )
          .filter((value): value is number => value !== null);
        collectionsTotal =
          paidRows.length === todayInvoices.length
            ? paidRows.reduce((sum, value) => sum + value, 0)
            : null;
      }

      setStats({
        invoicesCount,
        invoicedTotal,
        collectionsTotal,
        samples:
          samplesResult.status === "fulfilled" ? samplesResult.value : null,
        pendingApprovals:
          approvalsResult.status === "fulfilled"
            ? approvalsResult.value.length
            : null,
        draftSettlements:
          settlementsResult.status === "fulfilled"
            ? (settlementsResult.value.results?.length ?? 0)
            : null,
        exceptions:
          exceptionsResult.status === "fulfilled" &&
          exceptionsResult.value?.counts
            ? {
                total: exceptionsResult.value.counts.total || 0,
                lateTransfers: exceptionsResult.value.counts.late_transfer || 0,
                failedDeliveries:
                  exceptionsResult.value.counts.failed_delivery || 0,
                criticalUnacknowledged:
                  exceptionsResult.value.counts.critical_unacknowledged || 0,
              }
            : null,
      });
    };

    void loadRealData();

    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken]);

  return (
    <div className="p-8">
      <div className="flex flex-col w-full max-w-7xl mx-auto">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              {t("dashboard.owner.title")}
            </h1>
            <p className="text-sm text-slate-500 font-normal mt-1">
              <DashboardDateLine />
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 font-mono">
              <span
                aria-hidden="true"
                className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"
              />
              {t("dashboard.live_data")}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 lg:col-span-2 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4 flex items-center justify-between">
                <span>{t("dashboard.owner.today_business")}</span>
                <span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                  {t("dashboard.owner.day_to_date_batch")}
                </span>
              </div>
              <div className="space-y-3.5">
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    {t("dashboard.owner.invoices_label")}
                  </span>
                  <span className="text-lg font-bold text-slate-900">
                    {formatCount(stats.invoicesCount)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    {t("dashboard.owner.invoiced_total")}
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    {formatPkr(stats.invoicedTotal, lang)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium text-slate-600">
                    {t("dashboard.owner.collections_today")}
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    {formatPkr(stats.collectionsTotal, lang)}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-xs text-slate-400 mt-4 pt-2 border-t border-slate-50">
              <Trans
                i18nKey="dashboard.owner.business_footer"
                components={{ zone: <bdi dir="ltr" /> }}
              />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4">
                {t("dashboard.samples_by_status")}
              </div>
              {stats.samples ? (
                <div className="space-y-2.5">
                  {[
                    [
                      t("status.sample.collected"),
                      stats.samples.collected,
                      "bg-blue-600",
                    ],
                    [
                      t("status.sample.received"),
                      stats.samples.received,
                      "bg-cyan-600",
                    ],
                    [
                      t("status.sample.in_process"),
                      stats.samples.inProcess,
                      "bg-orange-600",
                    ],
                    [
                      t("status.sample.ready"),
                      stats.samples.ready,
                      "bg-green-600",
                    ],
                    [
                      t("status.sample.rejected"),
                      stats.samples.rejected,
                      "bg-red-600",
                    ],
                    [
                      t("status.sample.cancelled"),
                      stats.samples.cancelled,
                      "bg-slate-500",
                    ],
                  ].map(([label, value, colour]) => (
                    <div
                      key={String(label)}
                      className="flex items-center justify-between py-1"
                    >
                      <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                        <span
                          aria-hidden="true"
                          className={`w-2 h-2 rounded-full ${colour}`}
                        />
                        {label}
                      </span>
                      <span className="font-medium text-slate-900 font-mono text-sm">
                        {value}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  {t("dashboard.unavailable.samples")}
                </p>
              )}
            </div>
            <div className="text-[11px] text-slate-400 mt-3 pt-2 border-t border-slate-50">
              {stats.samples ? (
                <Trans
                  i18nKey="dashboard.samples.total_accessions_scope"
                  values={{ total: stats.samples.total }}
                  components={{ acc: <bdi dir="ltr" /> }}
                />
              ) : (
                t("dashboard.samples.totals_unavailable")
              )}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                {t("dashboard.stat.pending_approvals")}
              </div>
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-bold text-slate-900">
                  {formatCount(stats.pendingApprovals)}
                </span>
                <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded tracking-wide uppercase border border-amber-200 bg-[#fef3c7] text-[#b45309]">
                  {t("dashboard.owner.review_badge")}
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {t("dashboard.owner.pending_hint")}
              </p>
            </div>
            <Link
              to="/results/approvals"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>{t("dashboard.links.open_approvals")}</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform rtl:-scale-x-100"
              >
                →
              </span>
            </Link>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                {t("dashboard.owner.settlements")}
              </div>
              <div className="text-4xl font-bold text-slate-900">
                {formatCount(stats.draftSettlements)}
              </div>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {t("dashboard.owner.draft_settlements")}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {t("dashboard.owner.counts_only")}
              </p>
            </div>
            <Link
              to="/settlements"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>{t("dashboard.links.review_settlements")}</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform rtl:-scale-x-100"
              >
                →
              </span>
            </Link>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3 flex items-center justify-between">
                <span>{t("dashboard.exceptions")}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-red-50 text-red-700 font-medium">
                  {t("dashboard.requires_action")}
                </span>
              </div>
              <div className="text-4xl font-bold text-slate-900 mb-3">
                {formatCount(stats.exceptions?.total ?? null)}
              </div>
              <div className="space-y-1">
                <div className="text-sm text-slate-700 py-1 border-b border-slate-100 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 rounded-full bg-slate-400"
                  />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.late_transfers", {
                          count: stats.exceptions.lateTransfers,
                        })
                      : t("dashboard.counts.late_transfers_unknown")}
                  </span>
                </div>
                <div className="text-sm text-slate-700 py-1 border-b border-slate-100 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 rounded-full bg-slate-400"
                  />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.failed_deliveries", {
                          count: stats.exceptions.failedDeliveries,
                        })
                      : t("dashboard.counts.failed_deliveries_unknown")}
                  </span>
                </div>
                <div className="text-sm text-red-600 font-medium py-1 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 rounded-full bg-red-600"
                  />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.critical_unacknowledged", {
                          count: stats.exceptions.criticalUnacknowledged,
                        })
                      : t("dashboard.counts.critical_unacknowledged_unknown")}
                  </span>
                </div>
              </div>
            </div>
            <Link
              to="/exceptions"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>{t("dashboard.view_all")}</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform rtl:-scale-x-100"
              >
                →
              </span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
