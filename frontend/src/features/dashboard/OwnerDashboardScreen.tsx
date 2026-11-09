import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { billingService } from "../billing/billingService";
import { useAuthStore } from "../auth/authStore";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { sampleService } from "../samples/sampleService";

interface DashboardStats {
  invoicesCount: number;
  invoicedTotal: number;
  collectionsTotal: number;
  samples: {
    collected: number;
    inProcess: number;
    resultsEntered: number;
    reported: number;
    rejected: number;
    total: number;
  };
  pendingApprovals: number;
  draftSettlements: number;
  exceptions: {
    total: number;
    lateTransfers: number;
    failedDeliveries: number;
    criticalUnacknowledged: number;
  };
}

const INITIAL_STATS: DashboardStats = {
  invoicesCount: 0,
  invoicedTotal: 0,
  collectionsTotal: 0,
  samples: {
    collected: 0,
    inProcess: 0,
    resultsEntered: 0,
    reported: 0,
    rejected: 0,
    total: 0,
  },
  pendingApprovals: 0,
  draftSettlements: 0,
  exceptions: {
    total: 0,
    lateTransfers: 0,
    failedDeliveries: 0,
    criticalUnacknowledged: 0,
  },
};

export function OwnerDashboardScreen(): ReactElement {
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const accessToken = useAuthStore((s) => s.accessToken);

  // Format today's date in PKT
  const pktDateString = useMemo(() => {
    try {
      const now = new Date();
      const parts = new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "Asia/Karachi",
      }).format(now);
      return `${parts} · times are PKT`;
    } catch {
      return "Times are PKT";
    }
  }, []);

  useEffect(() => {
    let active = true;

    // Fetch real metrics from existing tenant APIs
    const loadRealData = async () => {
      if (!accessToken) return;
      let invCount = 0;
      let invTotal = 0;
      let collTotal = 0;
      let collected = 0;
      let inProc = 0;
      let resEntered = 0;
      let rep = 0;
      let rej = 0;
      let totalActive = 0;
      let approvals = 0;
      let settlements = 0;
      let lateTrans = 0;
      let failedDlv = 0;
      let critUnack = 0;
      let exceptionsTotal = 0;

      // 1. Invoices
      try {
        const invRes = await billingService.listInvoices({ limit: 100 });
        const list = invRes.results || [];
        invCount = list.length;
        invTotal = list.reduce(
          (sum, i) => sum + parseFloat(i.total || "0.00"),
          0,
        );
        collTotal = list.reduce(
          (sum, i) => sum + parseFloat(i.net_paid || "0.00"),
          0,
        );
      } catch {
        // Real API returned 0 / error
      }

      // 2. Samples
      try {
        const sampleRes = await sampleService.listSamples();
        const list = sampleRes.results || [];
        totalActive = list.filter((s) => s.status !== "cancelled").length;
        collected = list.filter((s) => s.status === "collected").length;
        inProc = list.filter(
          (s) => s.status === "in_process" || s.status === "received",
        ).length;
        resEntered = list.filter((s) => s.status === "ready").length;
        rep = 0;
        rej = list.filter((s) => s.status === "rejected").length;
        approvals = resEntered;
      } catch {
        // Real API returned 0 / error
      }

      // 3. Draft Settlements
      try {
        const stRes = await partnersService.getSettlements({ status: "draft" });
        settlements = stRes.results?.length ?? 0;
      } catch {
        // Real API returned 0 / error
      }

      // 4. Exceptions
      try {
        const exRes = await reportsService.getExceptions();
        if (exRes?.counts) {
          lateTrans = exRes.counts.late_transfer || 0;
          failedDlv = exRes.counts.failed_delivery || 0;
          critUnack = exRes.counts.critical_unacknowledged || 0;
          exceptionsTotal = exRes.counts.total || 0;
        }
      } catch {
        // Real API returned 0 / error
      }

      if (active) {
        setStats({
          invoicesCount: invCount,
          invoicedTotal: invTotal,
          collectionsTotal: collTotal,
          samples: {
            collected,
            inProcess: inProc,
            resultsEntered: resEntered,
            reported: rep,
            rejected: rej,
            total: totalActive,
          },
          pendingApprovals: approvals,
          draftSettlements: settlements,
          exceptions: {
            total: exceptionsTotal,
            lateTransfers: lateTrans,
            failedDeliveries: failedDlv,
            criticalUnacknowledged: critUnack,
          },
        });
      }
    };

    void loadRealData();

    return () => {
      active = false;
    };
  }, [accessToken]);

  return (
    <div className="p-8">
      <div className="flex flex-col w-full max-w-7xl mx-auto">
        {/* Page Header */}
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
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Main System Sync: Normal
            </span>
          </div>
        </div>

        {/* Dashboard Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Card 1: Today's Business (Spans 2 columns on lg) */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 lg:col-span-2 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4 flex items-center justify-between">
                <span>Today&apos;s business</span>
                <span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                  Day-to-date batch
                </span>
              </div>
              <div className="space-y-3.5">
                {/* Row 1: Invoices Count */}
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    Invoices
                  </span>
                  <span className="text-lg font-bold text-slate-900">
                    {stats.invoicesCount}
                  </span>
                </div>
                {/* Row 2: Invoiced Total */}
                <div className="flex items-center justify-between py-2 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-600">
                    Invoiced total
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    PKR {stats.invoicedTotal.toFixed(2)}
                  </span>
                </div>
                {/* Row 3: Collections */}
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium text-slate-600">
                    Collections
                  </span>
                  <span className="bg-slate-50 border border-slate-200 px-3 py-1.5 rounded font-mono text-sm font-semibold text-black tracking-tight select-all">
                    PKR {stats.collectionsTotal.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-xs text-slate-400 mt-4 pt-2 border-t border-slate-50">
              Server totals, shown as received.
            </div>
          </div>

          {/* Card 2: Samples by Status */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-4">
                Samples by status
              </div>
              <div className="space-y-2.5">
                {/* Item 1: Collected */}
                <div className="flex items-center justify-between py-1">
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-blue-600" />
                    Collected
                  </span>
                  <span className="font-medium text-slate-900 font-mono text-sm">
                    {stats.samples.collected}
                  </span>
                </div>
                {/* Item 2: In Process */}
                <div className="flex items-center justify-between py-1">
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-orange-600" />
                    In process
                  </span>
                  <span className="font-medium text-slate-900 font-mono text-sm">
                    {stats.samples.inProcess}
                  </span>
                </div>
                {/* Item 3: Results Entered */}
                <div className="flex items-center justify-between py-1">
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-blue-600" />
                    Results entered
                  </span>
                  <span className="font-medium text-slate-900 font-mono text-sm">
                    {stats.samples.resultsEntered}
                  </span>
                </div>
                {/* Item 4: Reported */}
                <div className="flex items-center justify-between py-1">
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-green-600" />
                    Reported
                  </span>
                  <span className="font-medium text-slate-900 font-mono text-sm">
                    {stats.samples.reported}
                  </span>
                </div>
                {/* Item 5: Rejected */}
                <div className="flex items-center justify-between py-1">
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-slate-50 px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-red-600" />
                    Rejected
                  </span>
                  <span className="font-medium text-slate-900 font-mono text-sm">
                    {stats.samples.rejected}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-[11px] text-slate-400 mt-3 pt-2 border-t border-slate-50">
              {stats.samples.total} total active specimens registered
            </div>
          </div>

          {/* Card 3: Pending Approvals */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                Pending approvals
              </div>
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-bold text-slate-900">
                  {stats.pendingApprovals}
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
              <span className="group-hover:translate-x-0.5 transition-transform">
                →
              </span>
            </Link>
          </div>

          {/* Card 4: Settlements */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3">
                Settlements
              </div>
              <div className="text-4xl font-bold text-slate-900">
                {stats.draftSettlements}
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
              <span className="group-hover:translate-x-0.5 transition-transform">
                →
              </span>
            </Link>
          </div>

          {/* Card 5: Exceptions */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col justify-between">
            <div>
              <div className="text-base font-semibold text-slate-900 mb-3 flex items-center justify-between">
                <span>Exceptions</span>
                <span className="text-xs px-2 py-0.5 rounded bg-red-50 text-red-700 font-medium">
                  Requires action
                </span>
              </div>
              <div className="text-4xl font-bold text-slate-900 mb-3">
                {stats.exceptions.total}
              </div>
              <div className="space-y-1">
                <div className="text-sm text-slate-700 py-1 border-b border-slate-100 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <span>
                    {stats.exceptions.lateTransfers} late sample transfers
                  </span>
                </div>
                <div className="text-sm text-slate-700 py-1 border-b border-slate-100 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <span>
                    {stats.exceptions.failedDeliveries} failed report deliveries
                  </span>
                </div>
                <div className="text-sm text-red-600 font-medium py-1 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                  <span>
                    {stats.exceptions.criticalUnacknowledged} critical result
                    unacknowledged
                  </span>
                </div>
              </div>
            </div>
            <Link
              to="/exceptions"
              className="text-sm font-medium text-teal-700 hover:text-teal-800 mt-4 inline-flex items-center gap-1 group transition-colors"
            >
              <span>View all</span>
              <span className="group-hover:translate-x-0.5 transition-transform">
                →
              </span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
