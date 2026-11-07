import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { platformService } from "./platformService";
import type { SubscriptionListItem, SubscriptionListSummary } from "./types";

export function SubscriptionsScreen() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subscriptions, setSubscriptions] = useState<SubscriptionListItem[]>([]);
  const [summary, setSummary] = useState<SubscriptionListSummary | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [planFilter, setPlanFilter] = useState("ALL");
  const [cycleFilter, setCycleFilter] = useState("ALL");
  const [quickFilter, setQuickFilter] = useState<"ALL" | "OVERDUE" | "DUE_WEEK">("ALL");

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.listSubscriptions();
      setSubscriptions(res.subscriptions);
      setSummary(res.summary);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load subscriptions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = useMemo(() => {
    return subscriptions.filter((sub) => {
      // Search
      if (search.trim()) {
        const q = search.toLowerCase();
        const matches =
          sub.tenant_name.toLowerCase().includes(q) ||
          sub.tenant_slug.toLowerCase().includes(q) ||
          sub.city?.toLowerCase().includes(q) ||
          sub.plan_name.toLowerCase().includes(q);
        if (!matches) return false;
      }

      // Quick filter
      if (quickFilter === "OVERDUE" && sub.status !== "past_due") return false;
      if (quickFilter === "DUE_WEEK") {
        if (!sub.next_due) return false;
        const due = new Date(sub.next_due).getTime();
        const now = Date.now();
        const week = 7 * 24 * 60 * 60 * 1000;
        if (due < now || due > now + week) return false;
      }

      // Dropdown filters
      if (statusFilter !== "ALL") {
        if (statusFilter === "PAID" && sub.status !== "active") return false;
        if (statusFilter === "OVERDUE" && sub.status !== "past_due") return false;
        if (statusFilter === "TRIAL" && sub.status !== "trialing") return false;
        if (statusFilter === "FOUNDING" && !sub.is_founding) return false;
      }

      if (planFilter !== "ALL" && !sub.plan_name.toLowerCase().includes(planFilter.toLowerCase())) {
        return false;
      }

      if (cycleFilter !== "ALL" && sub.billing_cycle !== cycleFilter.toLowerCase()) {
        return false;
      }

      return true;
    });
  }, [subscriptions, search, quickFilter, statusFilter, planFilter, cycleFilter]);

  const overdueLabs = useMemo(() => {
    return subscriptions.filter((s) => s.status === "past_due");
  }, [subscriptions]);

  const exportCSV = () => {
    const headers = [
      "Tenant Name",
      "Slug",
      "City",
      "Plan",
      "Billing Cycle",
      "Amount PKR",
      "Status",
      "Next Due Date",
    ];
    const rows = filtered.map((s) => [
      s.tenant_name,
      s.tenant_slug,
      s.city || "",
      s.plan_name,
      s.billing_cycle,
      s.amount,
      s.status,
      s.next_due || "N/A",
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.map((val) => `"${val}"`).join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `labflow-subscriptions-${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatPKR = (amt: string | number) => {
    const num = typeof amt === "string" ? parseFloat(amt) : amt;
    if (isNaN(num)) return "PKR 0";
    return `PKR ${num.toLocaleString()}`;
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Breadcrumb & Page Command Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md bg-surface-container-lowest p-space-md rounded shadow-sm">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs font-code-sm text-code-sm text-outline">
            <span>Platform</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-on-surface font-semibold">Subscriptions</span>
          </div>
          <div className="flex items-center gap-space-md">
            <h1 className="font-headline-lg text-headline-lg text-inverse-surface tracking-tight">
              Subscriptions
            </h1>
            <span className="font-code-sm text-code-sm px-2 py-0.5 bg-surface-container-high text-on-surface-variant rounded font-semibold">
              {subscriptions.length} Total Subscribed Nodes
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-space-sm self-start md:self-auto">
          <button
            onClick={exportCSV}
            className="h-8 px-space-md bg-surface-container-low text-on-surface font-label-sm text-label-sm hover:bg-surface-container transition-colors flex items-center gap-space-xs rounded shadow-sm"
            type="button"
          >
            <span className="material-symbols-outlined text-[16px]">file_download</span>
            Export Billing CSV
          </button>
        </div>
      </div>

      {/* Top Summary KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-md">
        {/* Card 1: MRR */}
        <div className="bg-surface-container-lowest p-space-md shadow-sm rounded flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
              Monthly Recurring Revenue
            </span>
            <span className="material-symbols-outlined text-[20px] text-primary">payments</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-inverse-surface tracking-tight tabular-nums font-bold">
              {summary ? formatPKR(summary.mrr_pkr) : "PKR 0"}
            </span>
          </div>
          <div className="flex items-center gap-space-xs">
            <span className="inline-flex items-center gap-0.5 bg-surface-container-low text-primary px-space-xs py-space-2xs font-code-sm text-code-sm font-bold rounded">
              <span className="material-symbols-outlined text-[14px]">trending_up</span>+8.4%
            </span>
            <span className="font-body-xs text-body-xs text-outline">vs last billing cycle</span>
          </div>
        </div>

        {/* Card 2: Overdue / Delinquent */}
        <div className="bg-surface-container-lowest p-space-md shadow-sm rounded flex flex-col justify-between">
          <div className="flex items-center justify-between text-error">
            <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
              Overdue / Delinquent
            </span>
            <span className="material-symbols-outlined text-[20px] text-error">warning</span>
          </div>
          <div className="my-space-xs flex items-baseline gap-space-sm">
            <span className="font-headline-xl text-headline-xl text-error tracking-tight tabular-nums font-bold">
              {summary ? formatPKR(summary.overdue_amount_pkr) : "PKR 0"}
            </span>
            <span className="bg-error-container text-on-error-container font-label-sm text-label-sm px-space-xs py-space-2xs font-bold uppercase rounded">
              {summary?.overdue_count ?? 0} Labs
            </span>
          </div>
          <div className="font-body-xs text-body-xs text-outline truncate" title={overdueLabs.map((l) => l.tenant_name).join(", ")}>
            {overdueLabs.length > 0
              ? overdueLabs.map((l) => l.tenant_name).join(", ")
              : "All accounts current in good standing"}
          </div>
        </div>

        {/* Card 3: Lifetime Licenses Sold */}
        <div className="bg-surface-container-lowest p-space-md shadow-sm rounded flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
              Lifetime Licenses Sold
            </span>
            <span className="material-symbols-outlined text-[20px] text-secondary">workspace_premium</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-inverse-surface tracking-tight tabular-nums font-bold">
              {summary?.lifetime_sold_count ?? 0}
            </span>
          </div>
          <div className="font-body-xs text-body-xs text-outline">
            Single & Multi-branch perpetual nodes
          </div>
        </div>

        {/* Card 4: Founding Member Quota */}
        <div className="bg-surface-container-lowest p-space-md shadow-sm rounded flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
              Founding Member Quota
            </span>
            <span className="material-symbols-outlined text-[20px] text-primary">pie_chart</span>
          </div>
          <div className="my-space-xs">
            <div className="flex items-baseline justify-between mb-1">
              <span className="font-headline-md text-headline-md text-inverse-surface tabular-nums font-bold">
                {summary?.founding_slots_used ?? 0} of {summary?.founding_slots_total ?? 10}
              </span>
              <span className="font-code-sm text-code-sm text-primary font-bold">
                {Math.round(((summary?.founding_slots_used ?? 0) / (summary?.founding_slots_total ?? 10)) * 100)}%
              </span>
            </div>
            <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-primary h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(
                    100,
                    ((summary?.founding_slots_used ?? 0) / (summary?.founding_slots_total ?? 10)) * 100
                  )}%`,
                }}
              />
            </div>
          </div>
          <div className="font-body-xs text-body-xs text-outline">
            {Math.max(0, (summary?.founding_slots_total ?? 10) - (summary?.founding_slots_used ?? 0))} subsidized slots remaining
          </div>
        </div>
      </div>

      {/* Filter & Search Command Section */}
      <div className="bg-surface-container-lowest p-space-md shadow-sm rounded flex flex-col gap-space-md">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-space-sm items-center">
          {/* Search Input */}
          <div className="md:col-span-5 relative">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-outline text-[18px]">
              search
            </span>
            <input
              className="w-full h-8 bg-surface-container-low pl-8 pr-2 font-body-sm text-body-sm text-on-surface placeholder:text-outline rounded focus:outline-none focus:bg-surface-container-lowest transition-colors"
              placeholder="Search by lab name, schema, city or plan..."
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Filter Dropdowns */}
          <div className="md:col-span-2">
            <select
              className="w-full h-8 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded focus:outline-none cursor-pointer"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">Status: All Statuses</option>
              <option value="PAID">Paid / Active</option>
              <option value="OVERDUE">Overdue</option>
              <option value="TRIAL">Trial</option>
              <option value="FOUNDING">Founding</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <select
              className="w-full h-8 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded focus:outline-none cursor-pointer"
              value={planFilter}
              onChange={(e) => setPlanFilter(e.target.value)}
            >
              <option value="ALL">Plan: All Plans</option>
              <option value="Starter">Starter Tier</option>
              <option value="Growth">Growth Tier</option>
              <option value="Scale">Scale Tier</option>
              <option value="Lifetime">Lifetime Tier</option>
            </select>
          </div>

          <div className="md:col-span-3">
            <select
              className="w-full h-8 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded focus:outline-none cursor-pointer"
              value={cycleFilter}
              onChange={(e) => setCycleFilter(e.target.value)}
            >
              <option value="ALL">Cycle: All Frequencies</option>
              <option value="Monthly">Monthly</option>
              <option value="Annual">Annual</option>
              <option value="Lifetime">One-Time Lifetime</option>
            </select>
          </div>
        </div>

        {/* Quick Pill Filters */}
        <div className="flex flex-wrap items-center justify-between gap-space-sm pt-space-xs border-t border-surface-container">
          <div className="flex items-center gap-space-xs">
            <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider mr-1">
              Quick Views:
            </span>
            <button
              onClick={() => setQuickFilter("ALL")}
              className={`px-space-sm py-0.5 font-code-sm text-code-sm font-semibold rounded transition-colors flex items-center gap-1 ${
                quickFilter === "ALL"
                  ? "bg-primary text-on-primary"
                  : "bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest"
              }`}
              type="button"
            >
              All Records ({subscriptions.length})
            </button>
            <button
              onClick={() => setQuickFilter("OVERDUE")}
              className={`px-space-sm py-0.5 font-code-sm text-code-sm font-bold rounded transition-colors flex items-center gap-1 ${
                quickFilter === "OVERDUE"
                  ? "bg-error text-white"
                  : "bg-error-container text-on-error-container hover:opacity-90"
              }`}
              type="button"
            >
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-error" />
              Needs Attention ({overdueLabs.length})
            </button>
            <button
              onClick={() => setQuickFilter("DUE_WEEK")}
              className={`px-space-sm py-0.5 font-code-sm text-code-sm font-semibold rounded transition-colors flex items-center gap-1 ${
                quickFilter === "DUE_WEEK"
                  ? "bg-primary text-on-primary"
                  : "bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest"
              }`}
              type="button"
            >
              Due this week
            </button>
          </div>
          <div className="flex items-center gap-space-sm font-body-xs text-body-xs text-outline">
            <button
              className="text-primary hover:underline font-semibold flex items-center gap-0.5"
              onClick={() => {
                setSearch("");
                setStatusFilter("ALL");
                setPlanFilter("ALL");
                setCycleFilter("ALL");
                setQuickFilter("ALL");
              }}
              type="button"
            >
              <span className="material-symbols-outlined text-[14px]">refresh</span> Reset Filters
            </button>
          </div>
        </div>
      </div>

      {/* Dense Clinical Data Table */}
      <div className="bg-surface-container-lowest shadow-sm rounded overflow-hidden flex flex-col">
        {loading ? (
          <div className="p-12 text-center text-outline">
            <span className="inline-block w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-2" />
            <p className="font-body-sm text-body-sm">Loading platform subscriptions...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-error bg-error/5">
            <span className="material-symbols-outlined text-[32px] mb-1">error</span>
            <p className="font-title-sm text-title-sm font-bold">{error}</p>
            <button
              onClick={loadData}
              className="mt-3 px-4 py-1.5 bg-primary text-on-primary font-label-sm text-label-sm rounded hover:bg-primary-container"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-outline">
            <span className="material-symbols-outlined text-[36px] text-outline/50 mb-2">
              receipt_long
            </span>
            <p className="font-title-sm text-title-sm text-on-surface font-semibold">
              No subscription records match filters
            </p>
            <p className="font-body-xs text-body-xs mt-1">
              Adjust your search keywords or reset filter dropdowns to view all labs.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider border-b border-surface-container">
                  <th className="px-3 py-1 font-semibold">Lab Identity & Location</th>
                  <th className="px-3 py-1 font-semibold">Plan Tier</th>
                  <th className="px-3 py-1 font-semibold">Billing Frequency</th>
                  <th className="px-3 py-1 font-semibold text-right">Amount (PKR)</th>
                  <th className="px-3 py-1 font-semibold">Status</th>
                  <th className="px-3 py-1 font-semibold">Next Due Date</th>
                  <th className="px-3 py-1 font-semibold">Billing Mode</th>
                  <th className="px-3 py-1 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                {filtered.map((sub) => {
                  const isOverdue = sub.status === "past_due";
                  const isFounding = sub.is_founding;

                  return (
                    <tr
                      key={sub.id}
                      className="h-12 hover:bg-surface-container-low transition-colors"
                    >
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-space-xs">
                            <Link
                              to={`/platform/subscriptions/${sub.id}`}
                              className="font-title-sm text-title-sm text-inverse-surface font-bold hover:text-primary transition-colors"
                            >
                              {sub.tenant_name}
                            </Link>
                            <span className="font-code-sm text-code-sm bg-surface-container-high text-on-surface-variant px-1 rounded">
                              {sub.tenant_slug}
                            </span>
                            {isFounding && (
                              <span className="bg-secondary-container text-on-secondary-fixed font-code-sm text-[10px] px-1 py-0.5 rounded font-extrabold uppercase">
                                Founding 10
                              </span>
                            )}
                          </div>
                          <span className="font-body-xs text-body-xs text-outline">
                            {sub.city ? `${sub.city}, ${sub.province || "PK"}` : "Pakistan"}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2 font-medium">
                        <span className="font-title-sm text-title-sm">{sub.plan_name}</span>
                      </td>
                      <td className="px-3 py-2 text-on-surface-variant font-code-sm capitalize">
                        {sub.billing_cycle}
                      </td>
                      <td className="px-3 py-2 text-right font-bold font-code-sm tabular-nums text-inverse-surface">
                        {parseFloat(sub.amount).toLocaleString()}
                      </td>
                      <td className="px-3 py-2">
                        {isOverdue ? (
                          <span className="inline-flex items-center px-1.5 py-0.5 bg-error-container text-on-error-container font-label-sm text-label-sm font-bold uppercase rounded">
                            OVERDUE
                          </span>
                        ) : sub.status === "trialing" ? (
                          <span className="inline-flex items-center px-1.5 py-0.5 bg-blue-100 text-blue-800 font-label-sm text-label-sm font-bold uppercase rounded">
                            TRIAL
                          </span>
                        ) : sub.status === "active" ? (
                          <span className="inline-flex items-center px-1.5 py-0.5 bg-primary-fixed text-on-primary-fixed font-label-sm text-label-sm font-bold uppercase rounded">
                            PAID
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-1.5 py-0.5 bg-surface-container-high text-outline font-label-sm text-label-sm font-bold uppercase rounded">
                            {sub.status}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-code-sm">
                        {sub.next_due ? (
                          <span className={isOverdue ? "text-error font-bold" : "text-on-surface"}>
                            {new Date(sub.next_due).toLocaleDateString("en-PK", {
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                            })}
                          </span>
                        ) : sub.is_lifetime ? (
                          <span className="text-secondary font-semibold">Perpetual License</span>
                        ) : (
                          <span className="text-outline">N/A</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-code-sm text-on-surface-variant">
                        <span className="inline-flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                          Manual Bank / Raast
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="inline-flex items-center gap-1 justify-end">
                          <button
                            onClick={() => navigate(`/platform/subscriptions/${sub.id}`)}
                            className="h-7 px-2.5 bg-primary-container text-on-primary font-label-sm text-label-sm hover:bg-primary transition-colors rounded shadow-xs"
                            type="button"
                          >
                            Mark Paid
                          </button>
                          <button
                            onClick={() => navigate(`/platform/subscriptions/${sub.id}`)}
                            className="h-7 px-2 bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest transition-colors rounded"
                            title="Manage Ledger & Plan"
                            type="button"
                          >
                            <span className="material-symbols-outlined text-[16px]">tune</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Table Footer */}
        <div className="p-space-sm bg-surface-container-low/50 border-t border-surface-container flex items-center justify-between font-body-xs text-body-xs text-outline">
          <span>
            Showing <strong>{filtered.length}</strong> of <strong>{subscriptions.length}</strong> subscription records
          </span>
          <span>Currency: Pakistani Rupee (PKR) • Public Accounting Schema Only</span>
        </div>
      </div>
    </div>
  );
}
