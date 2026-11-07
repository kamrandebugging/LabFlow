import { useEffect, useState } from "react";
import { platformService } from "./platformService";
import type { AuditEntry } from "./types";

export function AuditLogScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<AuditEntry[]>([]);

  // Filters
  const [actionFilter, setActionFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const loadAudits = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.getAuditLog({
        action: actionFilter || undefined,
        tenant_id: tenantFilter || undefined,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
        limit: 100,
      });
      setAudits(res.audit || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load audit records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudits();
  }, [actionFilter, startDate, endDate]);

  const getActionBadge = (action: string) => {
    if (action.includes("suspended") || action.includes("disabled")) {
      return (
        <span className="px-2 py-0.5 bg-error-container text-on-error-container font-code-sm text-xs font-bold rounded">
          {action}
        </span>
      );
    }
    if (action.includes("payment")) {
      return (
        <span className="px-2 py-0.5 bg-primary-fixed text-on-primary-fixed font-code-sm text-xs font-bold rounded">
          {action}
        </span>
      );
    }
    if (action.includes("plan") || action.includes("settings")) {
      return (
        <span className="px-2 py-0.5 bg-secondary-container text-on-secondary-fixed font-code-sm text-xs font-bold rounded">
          {action}
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 bg-surface-container-high text-on-surface font-code-sm text-xs font-bold rounded">
        {action}
      </span>
    );
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Breadcrumb & Header */}
      <div className="flex flex-col gap-space-2xs">
        <div className="flex items-center gap-space-xs text-outline font-label-sm text-label-sm">
          <span>Platform Governance</span>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-primary font-semibold">Audit Trail</span>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md mt-space-xs">
          <div>
            <div className="flex items-center gap-space-xs">
              <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-extrabold">
                Immutable Platform Audit Log
              </h1>
              <span className="px-2 py-0.5 bg-primary-fixed text-primary font-code-sm text-xs font-bold uppercase rounded flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">lock</span>
                Append-Only Ledger
              </span>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
              Cryptographically timestamped record of administrative interventions, payment settlements, quota changes, and platform configurations.
            </p>
          </div>

          <button
            type="button"
            onClick={loadAudits}
            className="h-8 px-space-sm bg-surface-container-low hover:bg-surface-container text-on-surface rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors self-start md:self-auto shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px]">refresh</span>
            Refresh Log
          </button>
        </div>
      </div>

      {/* Filter Ribbon */}
      <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col md:flex-row items-center justify-between gap-space-sm">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-space-sm w-full md:w-auto flex-1">
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="h-8 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded border border-outline-variant/40 focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="">All Administrative Actions</option>
            <option value="payment.recorded">payment.recorded</option>
            <option value="plan.changed">plan.changed</option>
            <option value="role.updated">role.updated</option>
            <option value="tenant.provisioned">tenant.provisioned</option>
            <option value="tenant.suspended">tenant.suspended</option>
            <option value="tenant.reactivated">tenant.reactivated</option>
            <option value="settings.updated">settings.updated</option>
            <option value="user.invited">user.invited</option>
            <option value="user.disabled">user.disabled</option>
            <option value="failure.retried">failure.retried</option>
          </select>

          <input
            type="text"
            placeholder="Filter by Tenant / Entity UUID..."
            value={tenantFilter}
            onChange={(e) => setTenantFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadAudits()}
            className="h-8 bg-surface-container-low px-3 font-code-sm text-code-sm text-on-surface rounded border border-outline-variant/40 focus:outline-none focus:border-primary"
          />

          <input
            type="date"
            placeholder="From Date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-8 bg-surface-container-low px-2 font-code-sm text-xs text-on-surface rounded border border-outline-variant/40 focus:outline-none focus:border-primary cursor-pointer"
          />

          <input
            type="date"
            placeholder="To Date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-8 bg-surface-container-low px-2 font-code-sm text-xs text-on-surface rounded border border-outline-variant/40 focus:outline-none focus:border-primary cursor-pointer"
          />
        </div>

        <button
          type="button"
          onClick={() => {
            setActionFilter("");
            setTenantFilter("");
            setStartDate("");
            setEndDate("");
          }}
          className="font-body-xs text-body-xs text-primary hover:underline font-semibold flex items-center gap-0.5 whitespace-nowrap self-end md:self-center"
        >
          <span className="material-symbols-outlined text-[14px]">refresh</span>
          Reset Filters
        </button>
      </div>

      {/* Audit Timeline Table */}
      <div className="bg-surface-container-lowest shadow-sm rounded overflow-hidden flex flex-col">
        {loading ? (
          <div className="p-12 text-center text-outline">
            <span className="inline-block w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-2" />
            <p className="font-body-sm text-body-sm">Reading tamper-evident audit ledger...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-error bg-error/5">
            <span className="material-symbols-outlined text-[32px] mb-1">error</span>
            <p className="font-title-sm text-title-sm font-bold">{error}</p>
          </div>
        ) : audits.length === 0 ? (
          <div className="p-12 text-center text-outline">
            <span className="material-symbols-outlined text-[36px] text-outline/50 mb-2">
              history_edu
            </span>
            <p className="font-title-sm text-title-sm text-on-surface font-semibold">
              No audit entries match filter criteria
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                  <th className="px-3 py-1 font-semibold">Timestamp (UTC)</th>
                  <th className="px-3 py-1 font-semibold">Actor</th>
                  <th className="px-3 py-1 font-semibold">Event Action</th>
                  <th className="px-3 py-1 font-semibold">Target Entity</th>
                  <th className="px-3 py-1 font-semibold">Structured Mutation (Before → After)</th>
                  <th className="px-3 py-1 font-semibold text-right">Client IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                {audits.map((a) => (
                  <tr key={a.id} className="h-12 hover:bg-surface-container-low transition-colors">
                    <td className="px-3 py-2 font-code-sm text-xs text-outline whitespace-nowrap">
                      {a.at
                        ? new Date(a.at).toLocaleString("en-PK", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })
                        : "—"}
                    </td>
                    <td className="px-3 py-2 font-code-sm text-xs font-semibold text-on-surface">
                      {a.actor_id ? a.actor_id.slice(0, 8) : "system"}
                    </td>
                    <td className="px-3 py-2">{getActionBadge(a.action)}</td>
                    <td className="px-3 py-2 font-code-sm text-xs text-outline">
                      <span className="font-semibold text-on-surface">{a.entity_type}</span>
                      <span className="block text-[11px] truncate max-w-[120px]">{a.entity_id}</span>
                    </td>
                    <td className="px-3 py-2 font-code-sm text-xs max-w-lg">
                      <div className="flex flex-col gap-0.5">
                        {a.before && Object.keys(a.before).length > 0 && (
                          <div className="text-outline truncate" title={JSON.stringify(a.before)}>
                            <span className="font-bold text-error">-</span> {JSON.stringify(a.before)}
                          </div>
                        )}
                        {a.after && Object.keys(a.after).length > 0 && (
                          <div className="text-on-surface font-semibold truncate" title={JSON.stringify(a.after)}>
                            <span className="font-bold text-primary">+</span> {JSON.stringify(a.after)}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-code-sm text-xs text-outline">
                      {a.ip || "127.0.0.1"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="p-space-sm bg-surface-container-low/50 border-t border-surface-container flex items-center justify-between font-body-xs text-body-xs text-outline">
          <span>Audit entries are immutable. Direct writes and updates are prohibited by database security triggers.</span>
          <span>Ledger Node: PK-ISB-01</span>
        </div>
      </div>
    </div>
  );
}
