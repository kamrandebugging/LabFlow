import type { ReactElement } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Building2, CircleDot, PauseCircle, Timer } from "lucide-react";
import { Link } from "react-router-dom";

import { platformService } from "./platformService";
import type { OverviewMetrics } from "./types";

function MetricCard({
  label,
  value,
  source,
  tone = "slate",
  Icon,
}: {
  label: string;
  value: string;
  source: string;
  tone?: "slate" | "emerald" | "amber" | "rose" | "sky";
  Icon: typeof Building2;
}): ReactElement {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    emerald: "bg-emerald-50 text-[#0E6B3A]",
    amber: "bg-amber-50 text-amber-700",
    rose: "bg-rose-50 text-rose-700",
    sky: "bg-sky-50 text-sky-700",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
        </div>
        <span
          className={`flex h-9 w-9 items-center justify-center rounded-lg ${tones[tone]}`}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      {/* Every figure names its source next to it. */}
      <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-400">
        {source}
      </p>
    </div>
  );
}

export function OverviewScreen(): ReactElement {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => platformService.getOverview(),
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1
          className="text-2xl font-bold tracking-tight text-slate-900"
          style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
        >
          Platform overview
        </h1>
        <p className="text-sm text-slate-600">
          Aggregate platform state, computed from public-schema records only.
          Tenant business data is never read here.
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading metrics…</p>
      ) : isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error instanceof Error ? error.message : "Could not load metrics."}
        </div>
      ) : data ? (
        <OverviewBody metrics={data} />
      ) : (
        <p className="text-sm text-slate-500">No metrics available.</p>
      )}
    </div>
  );
}

function OverviewBody({ metrics }: { metrics: OverviewMetrics }): ReactElement {
  const census = metrics.access_mode_census;
  return (
    <>
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total provisioned"
          value={String(metrics.total_labs)}
          source="public.tenant (excluding the platform schema)"
          Icon={Building2}
          tone="slate"
        />
        <MetricCard
          label="Active"
          value={String(metrics.active_labs)}
          source="public.tenant.status = active"
          Icon={CircleDot}
          tone="emerald"
        />
        <MetricCard
          label="Provisioning"
          value={String(metrics.provisioning_labs)}
          source="public.tenant.status = provisioning"
          Icon={Timer}
          tone="sky"
        />
        <MetricCard
          label="Suspended"
          value={String(metrics.suspended_labs)}
          source="public.tenant.status = suspended"
          Icon={PauseCircle}
          tone="amber"
        />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Monthly recurring revenue
          </p>
          <p className="mt-1 text-3xl font-bold text-slate-900">
            PKR {metrics.mrr_pkr}
          </p>
          <p className="mt-2 text-[11px] text-slate-500">
            Sum of plan price over active subscriptions. Computed on request, never
            stored.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Overdue subscriptions
          </p>
          <p className="mt-1 text-3xl font-bold text-slate-900">
            {metrics.overdue_count}
          </p>
          <p className="mt-2 text-[11px] text-slate-500">
            Subscriptions in past_due. {metrics.lifetime_sold} subscription(s)
            created to date.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Access mode census
          </p>
          <dl className="mt-2 space-y-1 text-sm text-slate-700">
            <div className="flex justify-between">
              <dt>Full access</dt>
              <dd className="font-semibold">{census.full}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Read-only</dt>
              <dd className="font-semibold">{census.read_only}</dd>
            </div>
            <div className="flex justify-between">
              <dt>In grace period</dt>
              <dd className="font-semibold">{census.grace}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Founding offer
            </p>
            <p className="mt-1 text-lg font-semibold text-slate-900">
              {metrics.founding_slots_used} of {metrics.founding_slots_total}{" "}
              slots used
            </p>
          </div>
          {metrics.founding_slots_total === 0 ? (
            <span className="flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              Slot total not configured
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Used counts active subscriptions on the configured founding plan; the
          total comes from platform configuration. Snapshot generated{" "}
          {new Date(metrics.generated_at).toLocaleString()} (60-second cache).
        </p>
      </section>

      <p className="text-xs text-slate-500">
        Looking for a specific lab?{" "}
        <Link to="/platform/tenants" className="font-semibold text-[#0E6B3A]">
          Open the labs registry →
        </Link>
      </p>
    </>
  );
}
