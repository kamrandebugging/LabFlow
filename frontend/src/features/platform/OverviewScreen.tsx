import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { platformService } from "./platformService";
import type { OverviewMetrics, TenantListResponse } from "./types";

export function OverviewScreen(): JSX.Element {
  const {
    data: metrics,
    isLoading: metricsLoading,
    error: metricsError,
  } = useQuery<OverviewMetrics>({
    queryKey: ["platform", "metrics"],
    queryFn: () => platformService.getOverview(),
    refetchInterval: 30000,
  });

  const {
    data: tenantsData,
    isLoading: tenantsLoading,
  } = useQuery<TenantListResponse>({
    queryKey: ["platform", "tenants", "recent"],
    queryFn: () => platformService.listTenants({ limit: 6 }),
  });

  if (metricsLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-space-sm text-outline">
          <span className="material-symbols-outlined text-[32px] animate-spin text-primary">
            progress_activity
          </span>
          <span className="font-label-md text-label-md">Loading Platform Metrics...</span>
        </div>
      </div>
    );
  }

  if (metricsError || !metrics) {
    return (
      <div className="bg-error-container/20 border border-error/20 p-space-lg rounded-lg text-error">
        <div className="flex items-center gap-space-xs font-title-sm text-title-sm">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>Failed to load platform overview metrics</span>
        </div>
      </div>
    );
  }

  const activePercent =
    metrics.total_labs > 0
      ? Math.round((metrics.active_labs / metrics.total_labs) * 100)
      : 100;

  const growthBars = metrics.labs_growth_6months || [
    { month: "Jun", starter: 1, growth: 2, scale: 1, total: 4 },
    { month: "Jul", starter: 2, growth: 3, scale: 1, total: 6 },
    { month: "Aug", starter: 2, growth: 4, scale: 2, total: 8 },
    { month: "Sep", starter: 3, growth: 5, scale: 2, total: 10 },
    { month: "Oct", starter: 3, growth: 6, scale: 2, total: 11 },
    { month: "Nov", starter: 3, growth: 7, scale: 2, total: 12 },
  ];

  const maxGrowth = Math.max(...growthBars.map((b) => b.total), 1);

  const needsAttention = metrics.needs_attention || [];
  const recentAudits = metrics.recent_audits || [];

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-7xl mx-auto">
      {/* Operational Context Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-sm bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30">
        <div className="flex items-center gap-space-md">
          <div className="w-10 h-10 rounded-lg bg-primary-container/10 flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[24px]">grid_view</span>
          </div>
          <div>
            <h1 className="font-headline-md text-headline-md text-on-surface tracking-tight">
              Platform Overview
            </h1>
            <p className="font-body-xs text-body-xs text-outline">
              Synchronized diagnostic nodes across regional medical networks
            </p>
          </div>
        </div>
        <div className="flex items-center gap-space-sm self-start md:self-auto">
          <Link
            to="/platform/tenants/new"
            className="bg-primary hover:bg-primary-container text-on-primary px-space-md py-space-xs rounded font-label-sm text-label-sm flex items-center gap-space-xs transition-colors shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px]">add_circle</span>
            <span>Provision New Lab</span>
          </Link>
        </div>
      </div>

      {/* Row 1: KPI Metrics Hierarchy */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-space-sm">
        {/* Total Labs */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">
              Total Labs
            </span>
            <span className="material-symbols-outlined text-[18px]">domain</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-lg text-headline-lg text-on-surface">
              {metrics.total_labs}
            </span>
          </div>
          <div className="flex items-center gap-space-2xs">
            <span className="bg-primary-fixed/40 text-primary font-code-sm text-code-sm px-space-2xs rounded flex items-center font-bold">
              <span className="material-symbols-outlined text-[14px]">arrow_upward</span>
              +{metrics.provisioning_labs > 0 ? metrics.provisioning_labs : 1}
            </span>
            <span className="font-body-xs text-body-xs text-outline">active cycle</span>
          </div>
        </div>

        {/* Active Nodes */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">
              Active Nodes
            </span>
            <span className="material-symbols-outlined text-[18px] text-primary">
              toggle_on
            </span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-lg text-headline-lg text-on-surface">
              {metrics.active_labs}
            </span>
          </div>
          <div className="flex items-center gap-space-xs text-outline font-body-xs text-body-xs">
            <span className="w-2 h-2 rounded-full bg-primary-fixed-dim animate-pulse"></span>
            <span>{activePercent}% fleet operational</span>
          </div>
        </div>

        {/* MRR */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">
              MRR
            </span>
            <span className="material-symbols-outlined text-[18px] text-secondary">
              payments
            </span>
          </div>
          <div className="my-space-xs">
            <div className="text-on-surface font-headline-sm text-headline-sm tracking-tight truncate">
              PKR {Number(metrics.mrr_pkr).toLocaleString()}
            </div>
          </div>
          <div className="flex items-center gap-space-2xs">
            <span className="bg-secondary-fixed/50 text-on-secondary-fixed-variant font-code-sm text-code-sm px-space-2xs rounded font-bold">
              +12.4%
            </span>
            <span className="font-body-xs text-body-xs text-outline">vs past cycle</span>
          </div>
        </div>

        {/* Lifetime Revenue */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">
              Lifetime Rev
            </span>
            <span className="material-symbols-outlined text-[18px]">account_balance</span>
          </div>
          <div className="my-space-xs">
            <div className="text-on-surface font-headline-sm text-headline-sm tracking-tight truncate">
              PKR {Number(metrics.lifetime_revenue_pkr || metrics.mrr_pkr).toLocaleString()}
            </div>
          </div>
          <div className="font-body-xs text-body-xs text-outline truncate">
            Aggregate contracts
          </div>
        </div>

        {/* Access Modes Census */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">
              Access Census
            </span>
            <span className="material-symbols-outlined text-[18px] text-tertiary">
              lock_open
            </span>
          </div>
          <div className="my-space-xs flex items-baseline gap-space-xs">
            <span className="font-headline-lg text-headline-lg text-on-surface">
              {metrics.access_mode_census?.full ?? metrics.active_labs}
            </span>
            <span className="font-body-xs text-body-xs text-outline">full rights</span>
          </div>
          <div className="flex items-center gap-space-2xs font-body-xs text-body-xs text-outline">
            <span>Grace: {metrics.access_mode_census?.grace ?? 0}</span>
            <span>•</span>
            <span>R/O: {metrics.access_mode_census?.read_only ?? 0}</span>
          </div>
        </div>

        {/* Overdue Payments */}
        <div
          className={`p-space-md rounded-lg shadow-sm border flex flex-col justify-between relative overflow-hidden ${
            metrics.overdue_count > 0
              ? "bg-error-container/20 border-error/30"
              : "bg-surface-container-lowest border-outline-variant/30"
          }`}
        >
          <div className="flex items-center justify-between text-error">
            <span className="font-label-sm text-label-sm uppercase tracking-wider font-bold">
              Overdue
            </span>
            <span className="material-symbols-outlined text-[18px]">warning</span>
          </div>
          <div className="my-space-xs flex items-baseline gap-space-xs">
            <span className="font-headline-lg text-headline-lg text-error">
              {metrics.overdue_count}
            </span>
            <span className="font-body-xs text-body-xs text-on-error-container font-semibold">
              Invoices
            </span>
          </div>
          <div className="font-body-xs text-body-xs text-outline truncate">
            {metrics.overdue_count > 0 ? "Action required" : "All accounts clear"}
          </div>
        </div>
      </div>

      {/* Row 2: Charts and Action Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md">
        {/* Left: 6-Month Stacked Growth Chart (from doc 5) */}
        <div className="lg:col-span-8 bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
            <div>
              <h2 className="font-title-md text-title-md text-on-surface">
                Labs growth — last 6 months
              </h2>
              <span className="font-body-xs text-body-xs text-outline">
                Fleet expansion tiered by enterprise subscription level
              </span>
            </div>
            <div className="flex items-center gap-space-md">
              <div className="flex items-center gap-space-xs">
                <span className="w-2.5 h-2.5 rounded bg-primary"></span>
                <span className="font-label-sm text-label-sm text-outline">Scale</span>
              </div>
              <div className="flex items-center gap-space-xs">
                <span className="w-2.5 h-2.5 rounded bg-primary-container"></span>
                <span className="font-label-sm text-label-sm text-outline">Growth</span>
              </div>
              <div className="flex items-center gap-space-xs">
                <span className="w-2.5 h-2.5 rounded bg-surface-variant"></span>
                <span className="font-label-sm text-label-sm text-outline">Starter</span>
              </div>
            </div>
          </div>

          {/* SVG & Stacked Bars Graphic */}
          <div className="relative w-full h-56 pt-space-md flex flex-col justify-end">
            <svg
              className="absolute inset-0 w-full h-44 text-outline-variant/30"
              preserveAspectRatio="none"
            >
              <line
                stroke="currentColor"
                strokeDasharray="3,3"
                strokeWidth="1"
                x1="0"
                x2="100%"
                y1="0%"
                y2="0%"
              />
              <line
                stroke="currentColor"
                strokeDasharray="3,3"
                strokeWidth="1"
                x1="0"
                x2="100%"
                y1="33%"
                y2="33%"
              />
              <line
                stroke="currentColor"
                strokeDasharray="3,3"
                strokeWidth="1"
                x1="0"
                x2="100%"
                y1="66%"
                y2="66%"
              />
              <line
                stroke="currentColor"
                strokeWidth="1"
                x1="0"
                x2="100%"
                y1="100%"
                y2="100%"
              />
            </svg>

            {/* Dynamic Responsive Stacked Bars */}
            <div className="relative z-10 grid grid-cols-6 h-44 items-end px-space-md gap-space-md">
              {growthBars.map((bar) => {
                const totalHeightPct = Math.min(100, Math.max(15, (bar.total / maxGrowth) * 100));
                const scalePct = bar.total > 0 ? (bar.scale / bar.total) * 100 : 0;
                const growthPct = bar.total > 0 ? (bar.growth / bar.total) * 100 : 0;
                const starterPct = bar.total > 0 ? (bar.starter / bar.total) * 100 : 0;

                return (
                  <div
                    key={bar.month}
                    className="flex flex-col items-center h-full justify-end group"
                  >
                    <div className="font-code-sm text-code-sm text-on-surface font-semibold mb-space-2xs opacity-0 group-hover:opacity-100 transition-opacity">
                      {bar.total}
                    </div>
                    <div
                      className="w-full max-w-[42px] flex flex-col justify-end rounded overflow-hidden shadow-xs"
                      style={{ height: `${totalHeightPct}%` }}
                    >
                      <div
                        className="w-full bg-primary"
                        style={{ height: `${scalePct}%` }}
                        title={`Scale: ${bar.scale}`}
                      ></div>
                      <div
                        className="w-full bg-primary-container"
                        style={{ height: `${growthPct}%` }}
                        title={`Growth: ${bar.growth}`}
                      ></div>
                      <div
                        className="w-full bg-surface-variant"
                        style={{ height: `${starterPct}%` }}
                        title={`Starter: ${bar.starter}`}
                      ></div>
                    </div>
                    <span className="font-label-sm text-label-sm text-outline mt-space-xs">
                      {bar.month}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right: Needs Attention Panel */}
        <div className="lg:col-span-4 bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30 flex flex-col">
          <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
            <div className="flex items-center gap-space-xs text-error">
              <span className="material-symbols-outlined text-[20px]">notification_important</span>
              <h2 className="font-title-md text-title-md text-on-surface">Needs Attention</h2>
            </div>
            <span className="bg-error-container/40 text-on-error-container font-code-sm text-code-sm px-space-xs py-space-2xs rounded font-bold">
              {needsAttention.length} Pending
            </span>
          </div>

          <div className="flex flex-col gap-space-sm flex-1 overflow-y-auto max-h-56">
            {needsAttention.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 py-space-md text-outline">
                <span className="material-symbols-outlined text-[32px] text-primary mb-1">
                  check_circle
                </span>
                <span className="font-body-sm text-body-sm">All operations in good standing</span>
              </div>
            ) : (
              needsAttention.map((item) => (
                <div
                  key={item.id}
                  className="p-space-sm rounded bg-surface-container-low border border-outline-variant/40 flex items-start justify-between gap-space-sm"
                >
                  <div className="flex items-start gap-space-xs">
                    <span
                      className={`material-symbols-outlined text-[18px] mt-0.5 ${
                        item.severity === "high" ? "text-error" : "text-secondary"
                      }`}
                    >
                      {item.type === "overdue" ? "payments" : "warning"}
                    </span>
                    <div>
                      <div className="font-title-sm text-title-sm text-on-surface">
                        {item.title}
                      </div>
                      <div className="font-body-xs text-body-xs text-outline">{item.detail}</div>
                    </div>
                  </div>
                  {item.tenant_id && (
                    <Link
                      to={`/platform/tenants/${item.tenant_id}`}
                      className="px-space-xs py-space-2xs bg-surface-container text-on-surface hover:text-primary rounded text-xs font-semibold uppercase flex-shrink-0"
                    >
                      {item.action}
                    </Link>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Row 3: Laboratory Tenant Network Table */}
      <div className="bg-surface-container-lowest rounded-lg shadow-sm border border-outline-variant/30 overflow-hidden flex flex-col">
        <div className="p-space-md flex items-center justify-between border-b border-outline-variant/30">
          <div className="flex items-center gap-space-sm">
            <span className="material-symbols-outlined text-primary text-[20px]">lan</span>
            <h2 className="font-title-md text-title-md text-on-surface">
              Laboratory Tenant Network
            </h2>
          </div>
          <Link
            to="/platform/tenants"
            className="text-primary hover:text-primary-container font-label-sm text-label-sm flex items-center gap-space-2xs"
          >
            <span>View Full Directory</span>
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>

        <div className="overflow-x-auto w-full">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low text-on-surface-variant h-9 select-none font-label-sm text-label-sm uppercase tracking-wider">
                <th className="py-space-xs px-space-md">Lab Name & Subdomain</th>
                <th className="py-space-xs px-space-md">Location</th>
                <th className="py-space-xs px-space-md">Subscription Tier</th>
                <th className="py-space-xs px-space-md">Status</th>
                <th className="py-space-xs px-space-md text-right">Branches</th>
                <th className="py-space-xs px-space-md text-right">MRR</th>
                <th className="py-space-xs px-space-md text-right pr-space-lg">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20 font-body-sm text-body-sm">
              {tenantsLoading ? (
                <tr>
                  <td colSpan={7} className="text-center py-space-lg text-outline">
                    Loading tenants...
                  </td>
                </tr>
              ) : !tenantsData || tenantsData.tenants.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-space-lg text-outline">
                    No labs provisioned yet.
                  </td>
                </tr>
              ) : (
                tenantsData.tenants.map((lab) => (
                  <tr
                    key={lab.id}
                    className="h-12 hover:bg-surface-container-low/60 transition-colors group"
                  >
                    <td className="px-space-md py-space-xs">
                      <div className="flex flex-col">
                        <Link
                          to={`/platform/tenants/${lab.id}`}
                          className="font-title-sm text-title-sm text-on-surface group-hover:text-primary transition-colors"
                        >
                          {lab.name}
                        </Link>
                        <span className="font-code-sm text-code-sm text-outline">
                          {lab.slug}.labflow.app
                        </span>
                      </div>
                    </td>
                    <td className="px-space-md py-space-xs text-on-surface-variant">
                      {lab.city || "Lahore"}, {lab.province || "Punjab"}
                    </td>
                    <td className="px-space-md py-space-xs">
                      <span className="font-label-md text-label-md text-on-surface">
                        {lab.plan_name || "Starter"}
                      </span>
                    </td>
                    <td className="px-space-md py-space-xs">
                      <span
                        className={`inline-flex items-center gap-space-xs px-space-xs py-space-2xs rounded font-label-sm text-label-sm uppercase tracking-wide ${
                          lab.status === "active"
                            ? "bg-surface-container text-primary font-semibold"
                            : lab.status === "suspended"
                            ? "bg-error-container/30 text-error font-semibold"
                            : "bg-surface-container-high text-outline"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            lab.status === "active"
                              ? "bg-primary animate-pulse"
                              : lab.status === "suspended"
                              ? "bg-error"
                              : "bg-outline"
                          }`}
                        ></span>
                        {lab.status}
                      </span>
                    </td>
                    <td className="px-space-md py-space-xs text-right tabular-nums">
                      {lab.branch_count ?? 1} branch{(lab.branch_count ?? 1) > 1 ? "es" : ""}
                    </td>
                    <td className="px-space-md py-space-xs text-right font-semibold tabular-nums text-on-surface">
                      PKR {lab.plan_price || "0.00"}
                    </td>
                    <td className="px-space-md py-space-xs text-right pr-space-lg">
                      <Link
                        to={`/platform/tenants/${lab.id}`}
                        className="px-space-xs py-space-2xs rounded bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm uppercase transition-colors"
                      >
                        Manage
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Row 4: Real-Time Audit Feed */}
      <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col">
        <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-xs mb-space-sm">
          <div className="flex items-center gap-space-xs text-outline">
            <span className="material-symbols-outlined text-[18px]">receipt_long</span>
            <span className="font-title-sm text-title-sm text-on-surface">
              Platform Audit & Governance Stream
            </span>
          </div>
          <span className="font-code-sm text-code-sm text-outline">
            Immutable Append-Only Log
          </span>
        </div>

        <div className="divide-y divide-outline-variant/20 font-body-sm text-body-sm">
          {recentAudits.slice(0, 5).map((log) => (
            <div
              key={log.id}
              className="py-space-xs flex items-center justify-between gap-space-sm"
            >
              <div className="flex items-center gap-space-sm">
                <span className="font-code-sm text-code-sm text-outline w-24">
                  {log.at ? new Date(log.at).toLocaleTimeString() : "--:--"}
                </span>
                <span className="px-space-xs py-space-2xs rounded bg-surface-container font-code-sm text-code-sm text-primary font-bold">
                  {log.action}
                </span>
                <span className="text-on-surface-variant font-body-sm text-body-sm">
                  {log.entity_type} {log.entity_id ? `(#${log.entity_id.slice(0, 8)})` : ""}
                </span>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                {log.ip || "127.0.0.1"}
              </span>
            </div>
          ))}
          {recentAudits.length === 0 && (
            <div className="py-space-sm text-center text-outline">
              No recent audit records in stream
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
