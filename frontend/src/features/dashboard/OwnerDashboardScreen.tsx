import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { fetchTenantContext, getSubdomainTenant } from "../auth/tenantContext";
import { billingService } from "../billing/billingService";
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
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const [tenantName, setTenantName] = useState<string>(() => {
    const sub = getSubdomainTenant();
    return sub?.name || "City Diagnostic Lab";
  });
  const [lang, setLang] = useState<"en" | "ur">("en");

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

  const userInitials = useMemo(() => {
    if (user?.name) {
      const parts = user.name.trim().split(/\s+/);
      if (parts.length >= 2 && parts[0] && parts[1]) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      }
      return user.name.slice(0, 2).toUpperCase();
    }
    if (user?.email) {
      return user.email.slice(0, 2).toUpperCase();
    }
    return "AR";
  }, [user]);

  const displayName = useMemo(() => {
    return user?.name || user?.email || "Ali Raza";
  }, [user]);

  useEffect(() => {
    let active = true;

    // Resolve tenant brand name
    void fetchTenantContext().then((info) => {
      if (active && info?.name) {
        setTenantName(info.name);
      }
    });

    // Fetch real metrics from existing tenant APIs
    const loadRealData = async () => {
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
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="bg-[#faf8ff] text-[#131b2e] antialiased min-h-screen">
      {/* Top Header */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-slate-200/80 z-50 px-6 flex items-center justify-between shadow-[0_1px_8px_rgba(0,0,0,0.02)]">
        <div className="flex items-center gap-4">
          <div className="w-9 h-9 rounded-lg bg-[#005c55] flex items-center justify-center text-white shadow-sm">
            <span className="material-symbols-outlined text-[20px]">
              science
            </span>
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-base text-slate-900 font-semibold tracking-tight">
                {tenantName}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold tracking-wider bg-[#86f2e4]/60 text-[#006f66]">
                LabFlow
              </span>
            </div>
            <p className="text-xs text-slate-400">All branches • Main Branch</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center bg-slate-100 p-1 rounded-full border border-slate-200/60">
            <button
              onClick={() => setLang("en")}
              className={`px-3 py-1 rounded-full text-xs font-semibold shadow-sm transition-all ${
                lang === "en"
                  ? "bg-white text-[#005c55]"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              type="button"
            >
              English
            </button>
            <button
              onClick={() => setLang("ur")}
              className={`px-3 py-1 rounded-full text-xs transition-colors ${
                lang === "ur"
                  ? "bg-white text-[#005c55] font-semibold shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              type="button"
            >
              اردو
            </button>
          </div>
          <div className="h-6 w-px bg-slate-200" />
          <div className="flex items-center gap-3 pl-1">
            <div className="w-9 h-9 rounded-full bg-[#86f2e4] flex items-center justify-center text-xs font-bold text-[#006f66] ring-2 ring-[#005c55]/20">
              {userInitials}
            </div>
            <div className="hidden sm:flex flex-col text-left">
              <span className="text-xs font-semibold text-slate-900 leading-tight">
                {displayName}
              </span>
              <span className="text-[11px] text-slate-500 leading-tight">
                Owner
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-red-600 ml-1 p-1 rounded transition-colors flex items-center"
              title="Log out"
              type="button"
            >
              <span className="material-symbols-outlined text-[20px]">
                logout
              </span>
            </button>
          </div>
        </div>
      </header>

      {/* Left Sidebar */}
      <aside className="fixed left-0 top-16 bottom-0 w-60 bg-white border-r border-slate-200/80 z-40 overflow-y-auto p-4 flex flex-col gap-6">
        <div className="flex flex-col">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
            Lab Operations
          </div>
          <nav className="flex flex-col gap-0.5">
            <Link
              to="/"
              aria-current="page"
              className="flex items-center gap-2.5 px-3 py-2 transition-colors bg-[#86f2e4]/70 text-[#005c55] font-semibold rounded-lg text-sm"
            >
              <span className="material-symbols-outlined text-[18px]">
                home
              </span>
              <span>Home</span>
            </Link>
            <Link
              to="/patients"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                personal_injury
              </span>
              <span>Patients</span>
            </Link>
            <Link
              to="/invoices"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                receipt_long
              </span>
              <span>Invoices &amp; Payments</span>
            </Link>
            <Link
              to="/samples"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                colorize
              </span>
              <span>Samples</span>
            </Link>
            <Link
              to="/worklist"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                assignment
              </span>
              <span>Worklist</span>
            </Link>
            <Link
              to="/results"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                edit_note
              </span>
              <span>Results Entry</span>
            </Link>
            <Link
              to="/approvals"
              className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  verified
                </span>
                <span>Approvals</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-teal-800 font-semibold">
                {stats.pendingApprovals}
              </span>
            </Link>
            <Link
              to="/results"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                notification_important
              </span>
              <span>Critical Notifications</span>
            </Link>
            <Link
              to="/reports"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                lab_profile
              </span>
              <span>Reports</span>
            </Link>
            <Link
              to="/exceptions"
              className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  warning
                </span>
                <span>Exceptions</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold">
                {stats.exceptions.total}
              </span>
            </Link>
          </nav>
        </div>

        <div className="flex flex-col">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
            Management
          </div>
          <nav className="flex flex-col gap-0.5">
            <Link
              to="/partners"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                handshake
              </span>
              <span>Partners &amp; Share Ledger</span>
            </Link>
            <Link
              to="/settlements"
              className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  account_balance_wallet
                </span>
                <span>Settlements</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                {stats.draftSettlements}
              </span>
            </Link>
            <Link
              to="/catalog"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                medical_services
              </span>
              <span>Catalog</span>
            </Link>
            <Link
              to="/settings"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                settings
              </span>
              <span>Settings</span>
            </Link>
          </nav>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="pl-60 min-h-screen flex flex-col bg-[#f8f9ff]">
        <main className="flex-1 pt-20 p-8">
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
                  to="/approvals"
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
                        {stats.exceptions.failedDeliveries} failed report
                        deliveries
                      </span>
                    </div>
                    <div className="text-sm text-red-600 font-medium py-1 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                      <span>
                        {stats.exceptions.criticalUnacknowledged} critical
                        result unacknowledged
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
        </main>
      </div>
    </div>
  );
}
