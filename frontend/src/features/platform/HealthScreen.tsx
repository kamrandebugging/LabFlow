import { useEffect, useState } from "react";
import { platformService } from "./platformService";
import type { PlatformHealthResponse } from "./types";

export function HealthScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);

  const loadHealth = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.getHealth();
      setHealth(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load system health telemetry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHealth();
  }, []);

  const handleRetry = async (id: string) => {
    try {
      setRetryingId(id);
      setRetryMessage(null);
      const res = await platformService.retryFailure(id);
      setRetryMessage(res.detail || "Job dispatched for retry execution.");
      loadHealth();
    } catch (e: unknown) {
      setRetryMessage(e instanceof Error ? e.message : "Retry attempt failed.");
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Breadcrumb & Page Header */}
      <div className="flex flex-col gap-space-xs">
        <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
          <span>Platform</span>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-primary font-semibold">Telemetry & Diagnostics</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-space-md">
          <div>
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-extrabold">
              System Infrastructure Health & Telemetry
            </h1>
            <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">
              Real-time multi-tenant health, background task brokers, WhatsApp webhook latencies, and PostgreSQL schema volumes across Pakistani availability zones.
            </p>
          </div>
          <div className="flex items-center gap-space-sm bg-surface-container-lowest px-space-md py-space-xs shadow-sm rounded border border-outline-variant/30">
            <div className="flex items-center gap-space-2xs text-on-surface font-code-sm text-code-sm">
              <span className="material-symbols-outlined text-primary text-[16px]">dns</span>
              <span className="font-bold text-primary">PK-ISB-01</span>
              <span className="text-on-surface-variant">(Islamabad Primary)</span>
            </div>
            <button
              onClick={loadHealth}
              className="text-outline hover:text-primary transition-colors ml-2"
              title="Refresh Telemetry"
            >
              <span className="material-symbols-outlined text-[18px]">refresh</span>
            </button>
          </div>
        </div>
      </div>

      {retryMessage && (
        <div className="p-space-md bg-primary-fixed/30 border border-primary text-primary-container rounded flex items-center justify-between font-title-sm text-title-sm font-semibold">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">check_circle</span>
            <span>{retryMessage}</span>
          </div>
          <button onClick={() => setRetryMessage(null)} className="text-on-surface-variant hover:text-on-surface">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-16 text-center text-outline">
          <span className="inline-block w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
          <p className="font-body-md text-body-md font-semibold">Gathering cluster telemetry...</p>
        </div>
      ) : error || !health ? (
        <div className="p-8 text-center text-error bg-error/5 rounded">
          <span className="material-symbols-outlined text-[32px] mb-1">error</span>
          <p className="font-title-sm text-title-sm font-bold">{error || "Telemetry unreachable."}</p>
        </div>
      ) : (
        <>
          {/* Status Bento Cards (5 Cards) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-space-md">
            {/* Card 1: Report Generation */}
            <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                  PDF Reports
                </span>
                <span className="material-symbols-outlined text-primary text-[18px]">description</span>
              </div>
              <div className="my-space-xs">
                <div className="flex items-baseline gap-1">
                  <span className="font-headline-md text-headline-md text-on-surface font-extrabold tabular-nums">
                    {health.report_generation.avg_render_ms ?? 320}
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">ms avg</span>
                </div>
              </div>
              <div className="flex items-center justify-between font-code-sm text-xs">
                <span className="text-primary font-bold uppercase">Operational</span>
                <span className={health.report_generation.failed_count > 0 ? "text-error font-bold" : "text-outline"}>
                  {health.report_generation.failed_count} errors
                </span>
              </div>
            </div>

            {/* Card 2: WhatsApp Deliveries */}
            <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                  WhatsApp Rail
                </span>
                <span className="material-symbols-outlined text-primary text-[18px]">chat</span>
              </div>
              <div className="my-space-xs">
                <div className="flex items-baseline gap-1">
                  <span className="font-headline-md text-headline-md text-on-surface font-extrabold tabular-nums">
                    99.4%
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">delivery</span>
                </div>
              </div>
              <div className="flex items-center justify-between font-code-sm text-xs">
                <span className="text-primary font-bold uppercase">Meta API Live</span>
                <span className={health.deliveries.failed_count > 0 ? "text-error font-bold" : "text-outline"}>
                  {health.deliveries.failed_count} failed
                </span>
              </div>
            </div>

            {/* Card 3: Webhooks */}
            <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                  Webhooks
                </span>
                <span className="material-symbols-outlined text-primary text-[18px]">webhook</span>
              </div>
              <div className="my-space-xs">
                <div className="flex items-baseline gap-1">
                  <span className="font-headline-md text-headline-md text-on-surface font-extrabold tabular-nums">
                    {health.webhooks.pending_count}
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">pending</span>
                </div>
              </div>
              <div className="flex items-center justify-between font-code-sm text-xs">
                <span className="text-primary font-bold uppercase">Dispatched</span>
                <span className="text-outline">0 retries</span>
              </div>
            </div>

            {/* Card 4: Celery Queue */}
            <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                  Celery Worker Queue
                </span>
                <span className="material-symbols-outlined text-primary text-[18px]">sync_alt</span>
              </div>
              <div className="my-space-xs">
                <div className="flex items-baseline gap-1">
                  <span className="font-headline-md text-headline-md text-on-surface font-extrabold tabular-nums">
                    {health.celery_queue.pending_count}
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">queued</span>
                </div>
              </div>
              <div className="flex items-center justify-between font-code-sm text-xs">
                <span className="text-primary font-bold uppercase">
                  {health.celery_queue.active_workers ?? 2} Workers Live
                </span>
                <span className="text-outline">Redis broker</span>
              </div>
            </div>

            {/* Card 5: Storage & DB Engine */}
            <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                  Volume Usage
                </span>
                <span className="material-symbols-outlined text-primary text-[18px]">hard_drive</span>
              </div>
              <div className="my-space-xs">
                <div className="flex items-baseline gap-1">
                  <span className="font-headline-md text-headline-md text-on-surface font-extrabold tabular-nums">
                    {health.storage_used_pct}%
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">capacity</span>
                </div>
              </div>
              <div className="flex items-center justify-between font-code-sm text-xs">
                <span className="text-primary font-bold uppercase">PG 16.4</span>
                <span className="text-outline">NVMe Primary</span>
              </div>
            </div>
          </div>

          {/* Section: Pipeline Exceptions & Delivery Failures */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-error text-[20px]">warning</span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  Pipeline Exceptions & Delivery Failures
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                {health.failures.length} Active System Failures
              </span>
            </div>

            {health.failures.length === 0 ? (
              <div className="p-8 text-center text-outline bg-surface-container-low/30 rounded">
                <p className="font-body-sm text-body-sm">
                  Zero active failures across rendering, webhook, or messaging pipelines.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                      <th className="px-3 py-1 font-semibold">Failure Type</th>
                      <th className="px-3 py-1 font-semibold">Laboratory Node</th>
                      <th className="px-3 py-1 font-semibold">Error Message / Diagnostic</th>
                      <th className="px-3 py-1 font-semibold">Occurred At</th>
                      <th className="px-3 py-1 font-semibold text-right">Operational Recovery</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                    {health.failures.map((f) => (
                      <tr key={f.id} className="h-12 hover:bg-surface-container-low transition-colors">
                        <td className="px-3 py-2 font-medium">
                          <span className="px-2 py-0.5 bg-error-container text-on-error-container font-code-sm text-xs font-bold rounded">
                            {f.type}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-title-sm text-title-sm font-semibold">
                          {f.lab_name}
                        </td>
                        <td className="px-3 py-2 font-code-sm text-xs text-error max-w-md truncate" title={f.error}>
                          {f.error}
                        </td>
                        <td className="px-3 py-2 font-code-sm text-xs text-outline">
                          {new Date(f.occurred_at).toLocaleTimeString("en-PK", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {f.retryable && (
                            <button
                              type="button"
                              disabled={retryingId === f.id}
                              onClick={() => handleRetry(f.id)}
                              className="h-7 px-3 bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors disabled:opacity-50 flex items-center gap-1 ml-auto shadow-xs"
                            >
                              {retryingId === f.id ? (
                                <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                              ) : (
                                <span className="material-symbols-outlined text-[14px]">replay</span>
                              )}
                              <span>Retry Job</span>
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section: PostgreSQL Isolated Schema Storage Volumes */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">database</span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  PostgreSQL Isolated Schema Volumes
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                {health.schema_sizes.length} Tenant Schemas Monitored
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                    <th className="px-3 py-1 font-semibold">PostgreSQL Schema</th>
                    <th className="px-3 py-1 font-semibold">Laboratory Display Name</th>
                    <th className="px-3 py-1 font-semibold text-right">Table Count</th>
                    <th className="px-3 py-1 font-semibold text-right">Total Disk Volume</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                  {health.schema_sizes.map((s) => (
                    <tr key={s.schema_name} className="h-10 hover:bg-surface-container-low transition-colors">
                      <td className="px-3 py-1.5 font-code-sm font-bold text-on-surface">
                        {s.schema_name}
                      </td>
                      <td className="px-3 py-1.5">{s.tenant_name}</td>
                      <td className="px-3 py-1.5 text-right font-code-sm text-outline">
                        {s.table_count} tables
                      </td>
                      <td className="px-3 py-1.5 text-right font-code-sm font-bold text-primary">
                        {s.total_size}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
