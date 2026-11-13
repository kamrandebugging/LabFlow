import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import {
  fetchSampleStatusCounts,
  formatCount,
  formatPkr,
  isTodayInPkt,
  listAllInvoices,
  PKT_LABEL,
  pktDateLabel,
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
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const accessToken = useAuthStore((s) => s.accessToken);

  const pktDateString = useMemo(() => `${pktDateLabel()} · ${PKT_LABEL}`, []);

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
              Business overview
            </h1>
            <p className="text-sm text-slate-500 font-normal mt-1">
              {pktDateString}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 font-mono">
              <span
                aria-hidden="true"
                className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"
              />
              Live tenant data
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 lg:col-span-2 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4 flex items-center justify-between">
                <span>Today&apos;s business</span>
                <span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                  Day-to-date batch
                </span>
              </div>
              <div className="space-y-3.5">
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    Invoices
                  </span>
                  <span className="text-lg font-bold text-slate-900">
                    {formatCount(stats.invoicesCount)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    Invoiced total
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    {formatPkr(stats.invoicedTotal)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium text-slate-600">
                    Collections (on today&apos;s invoices)
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    {formatPkr(stats.collectionsTotal)}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-xs text-slate-400 mt-4 pt-2 border-t border-slate-50">
              Server rows for the current Asia/Karachi day. A failed read shows
              an em dash, never a zero.
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4">
                Samples by status
              </div>
              {stats.samples ? (
                <div className="space-y-2.5">
                  {[
                    ["Collected", stats.samples.collected, "bg-blue-600"],
                    ["Received", stats.samples.received, "bg-cyan-600"],
                    ["In process", stats.samples.inProcess, "bg-orange-600"],
                    ["Ready", stats.samples.ready, "bg-green-600"],
                    ["Rejected", stats.samples.rejected, "bg-red-600"],
                    ["Cancelled", stats.samples.cancelled, "bg-slate-500"],
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
                  Unavailable — the samples API did not respond.
                </p>
              )}
            </div>
            <div className="text-[11px] text-slate-400 mt-3 pt-2 border-t border-slate-50">
              {stats.samples
                ? `${stats.samples.total} total accessions in scope`
                : "Sample totals unavailable"}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                Pending approvals
              </div>
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-bold text-slate-900">
                  {formatCount(stats.pendingApprovals)}
                </span>
                <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded tracking-wide uppercase border border-amber-200 bg-[#fef3c7] text-[#b45309]">
                  review
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                results awaiting your decision, critical first
              </p>
            </div>
            <Link
              to="/results/approvals"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>Open approvals</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform"
              >
                →
              </span>
            </Link>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                Settlements
              </div>
              <div className="text-4xl font-bold text-slate-900">
                {formatCount(stats.draftSettlements)}
              </div>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                DRAFT settlements awaiting approval
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Counts only — no partner names or partner figures on this
                screen.
              </p>
            </div>
            <Link
              to="/settlements"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>Review settlements</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform"
              >
                →
              </span>
            </Link>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3 flex items-center justify-between">
                <span>Exceptions</span>
                <span className="text-xs px-2 py-0.5 rounded bg-red-50 text-red-700 font-medium">
                  Requires action
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
                    {formatCount(stats.exceptions?.lateTransfers ?? null)} late
                    sample transfers
                  </span>
                </div>
                <div className="text-sm text-slate-700 py-1 border-b border-slate-100 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 rounded-full bg-slate-400"
                  />
                  <span>
                    {formatCount(stats.exceptions?.failedDeliveries ?? null)}{" "}
                    failed report deliveries
                  </span>
                </div>
                <div className="text-sm text-red-600 font-medium py-1 flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 rounded-full bg-red-600"
                  />
                  <span>
                    {formatCount(
                      stats.exceptions?.criticalUnacknowledged ?? null,
                    )}{" "}
                    critical result unacknowledged
                  </span>
                </div>
              </div>
            </div>
            <Link
              to="/exceptions"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>View all</span>
              <span
                aria-hidden="true"
                className="group-hover:translate-x-0.5 transition-transform"
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
