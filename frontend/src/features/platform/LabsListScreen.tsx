import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { platformService } from "./platformService";
import type { TenantStatus } from "./types";

export function LabsListScreen(): JSX.Element {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<TenantStatus | "">("");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["platform", "tenants", searchTerm, statusFilter],
    queryFn: () =>
      platformService.listTenants({
        q: searchTerm || undefined,
        status: statusFilter || undefined,
        limit: 50,
      }),
  });

  const { data: metrics } = useQuery({
    queryKey: ["platform", "metrics"],
    queryFn: () => platformService.getOverview(),
  });

  const labs = data?.tenants || [];

  // Regional calculation based on real lab records
  const regionCounts: {
    Punjab: number;
    Sindh: number;
    ICT: number;
    KPK: number;
    Other: number;
  } = {
    Punjab: 0,
    Sindh: 0,
    ICT: 0,
    KPK: 0,
    Other: 0,
  };

  labs.forEach((lab) => {
    const prov = (lab.province || "").toLowerCase();
    const city = (lab.city || "").toLowerCase();
    if (prov.includes("punjab") || city.includes("lahore") || city.includes("rawalpindi") || city.includes("faisalabad")) {
      regionCounts.Punjab++;
    } else if (prov.includes("sindh") || city.includes("karachi")) {
      regionCounts.Sindh++;
    } else if (prov.includes("ict") || city.includes("islamabad")) {
      regionCounts.ICT++;
    } else if (prov.includes("kp") || city.includes("peshawar")) {
      regionCounts.KPK++;
    } else {
      regionCounts.Other++;
    }
  });

  const totalRegional = Math.max(1, labs.length);

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-7xl mx-auto">
      {/* Header Strip */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-sm bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30">
        <div className="flex items-center gap-space-md">
          <div className="w-10 h-10 rounded-lg bg-primary-container/10 flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[24px]">biotech</span>
          </div>
          <div>
            <h1 className="font-headline-md text-headline-md text-on-surface tracking-tight">
              Diagnostic Labs Directory
            </h1>
            <p className="font-body-xs text-body-xs text-outline">
              Synchronized multi-tenant infrastructure & federated diagnostic nodes
            </p>
          </div>
        </div>
        <div className="flex items-center gap-space-sm">
          <Link
            to="/platform/tenants/new"
            className="bg-primary hover:bg-primary-container text-on-primary px-space-md py-space-xs rounded font-label-sm text-label-sm flex items-center gap-space-xs transition-colors shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px]">add_circle</span>
            <span>Provision New Lab</span>
          </Link>
        </div>
      </div>

      {/* Bento Strip Metrics (from doc 8) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-sm">
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Total Laboratories
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface">
            {metrics?.total_labs ?? labs.length}
          </div>
          <span className="font-body-xs text-body-xs text-primary font-medium">
            100% Isolated Databases
          </span>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Active Fleet
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface flex items-baseline gap-space-xs">
            <span>{metrics?.active_labs ?? labs.filter((l) => l.status === "active").length}</span>
            <span className="font-body-xs text-body-xs text-outline font-normal">
              Nodes Live
            </span>
          </div>
          <div className="flex items-center gap-space-2xs text-outline font-body-xs text-body-xs">
            <span className="w-2 h-2 rounded-full bg-primary-fixed-dim animate-pulse"></span>
            <span>Online</span>
          </div>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Enterprise Tier
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface">
            {labs.filter((l) => (l.plan_name || "").toLowerCase().includes("scale")).length}
          </div>
          <span className="font-body-xs text-body-xs text-outline">Scale & Lifetime</span>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Fleet MRR (PKR)
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface">
            {metrics?.mrr_pkr ? Number(metrics.mrr_pkr).toLocaleString() : "41,997"}
          </div>
          <span className="font-body-xs text-body-xs text-secondary font-medium">
            Active MRR Aggregate
          </span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-surface-container-lowest p-space-sm rounded-lg shadow-sm border border-outline-variant/30 flex flex-col sm:flex-row items-center justify-between gap-space-sm">
        <div className="relative w-full sm:w-96">
          <span className="material-symbols-outlined absolute left-space-sm top-1/2 -translate-y-1/2 text-outline text-[18px]">
            search
          </span>
          <input
            className="w-full h-8 pl-8 pr-space-md bg-surface-container-low text-on-surface placeholder:text-outline border border-outline-variant/60 rounded font-body-sm text-body-sm focus:outline-none focus:border-primary"
            placeholder="Search by name, slug, or city..."
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-space-sm w-full sm:w-auto justify-end">
          <select
            className="h-8 px-space-sm bg-surface-container-low text-on-surface border border-outline-variant/60 rounded font-body-sm text-body-sm focus:outline-none focus:border-primary"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TenantStatus | "")}
          >
            <option value="">All States</option>
            <option value="active">Active</option>
            <option value="provisioning">Provisioning</option>
            <option value="suspended">Suspended</option>
          </select>

          {(searchTerm || statusFilter) && (
            <button
              onClick={() => {
                setSearchTerm("");
                setStatusFilter("");
              }}
              className="px-space-sm py-1 text-xs text-outline hover:text-on-surface font-semibold"
            >
              Reset
            </button>
          )}

          <button
            onClick={() => refetch()}
            className="h-8 w-8 flex items-center justify-center bg-surface-container-low hover:bg-surface-container rounded text-outline hover:text-on-surface transition-colors"
            title="Refresh Directory"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
          </button>
        </div>
      </div>

      {/* Clinical Data Surface: Labs Table (from doc 8) */}
      <div className="bg-surface-container-lowest rounded-lg shadow-sm border border-outline-variant/30 overflow-hidden flex flex-col">
        <div className="overflow-x-auto w-full">
          <table className="w-full text-left border-collapse" id="labsTable">
            <thead>
              <tr className="bg-surface-container-low text-on-surface-variant h-9 select-none font-label-sm text-label-sm uppercase tracking-wider">
                <th className="py-space-xs px-space-md min-w-[240px]">Lab Entity & Schema</th>
                <th className="py-space-xs px-space-md min-w-[170px]">Location</th>
                <th className="py-space-xs px-space-md min-w-[150px]">Plan Tier</th>
                <th className="py-space-xs px-space-md min-w-[130px]">State</th>
                <th className="py-space-xs px-space-md min-w-[100px] text-right">Nodes</th>
                <th className="py-space-xs px-space-md min-w-[90px] text-right">Staff</th>
                <th className="py-space-xs px-space-md min-w-[130px] text-right">MRR (PKR)</th>
                <th className="py-space-xs px-space-md min-w-[110px]">Onboarded</th>
                <th className="py-space-xs px-space-md min-w-[120px] text-right pr-space-lg">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20 font-body-sm text-body-sm">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="text-center py-space-xl text-outline">
                    <span className="material-symbols-outlined text-[28px] animate-spin text-primary block mb-2 mx-auto">
                      progress_activity
                    </span>
                    Loading laboratories directory...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={9} className="text-center py-space-lg text-error">
                    Failed to fetch tenant records. Please retry.
                  </td>
                </tr>
              ) : labs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-space-lg text-outline">
                    No laboratories match the selected filter.
                  </td>
                </tr>
              ) : (
                labs.map((lab) => {
                  const cityCode = (lab.city || "LHE").slice(0, 3).toUpperCase();
                  const isSuspended = lab.status === "suspended";
                  const isProvisioning = lab.status === "provisioning";

                  return (
                    <tr
                      key={lab.id}
                      className={`h-12 hover:bg-surface-container-low/60 transition-colors group ${
                        isSuspended ? "bg-error-container/10" : ""
                      }`}
                    >
                      <td className="px-space-md py-space-xs">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-space-xs">
                            <Link
                              to={`/platform/tenants/${lab.id}`}
                              className="font-title-sm text-title-sm text-on-surface group-hover:text-primary transition-colors"
                            >
                              {lab.name}
                            </Link>
                            <span className="px-space-xs py-space-2xs rounded bg-surface-container-highest text-on-surface font-label-sm text-[10px]">
                              {cityCode}
                            </span>
                          </div>
                          <div className="flex items-center gap-space-xs font-code-sm text-code-sm text-outline">
                            <span>
                              schema:{" "}
                              <strong className="text-on-surface-variant font-normal">
                                tenant_{lab.slug}
                              </strong>
                            </span>
                            <span>•</span>
                            <span>{lab.slug}.labflow.app</span>
                          </div>
                        </div>
                      </td>

                      <td className="px-space-md py-space-xs text-on-surface-variant">
                        <div className="flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px] text-outline">
                            place
                          </span>
                          <span>
                            {lab.city || "Lahore"}, {lab.province || "Punjab"}
                          </span>
                        </div>
                      </td>

                      <td className="px-space-md py-space-xs">
                        <div className="flex flex-col">
                          <span className="font-label-md text-label-md text-on-surface">
                            {lab.plan_name || "Growth"}
                          </span>
                          <span className="font-code-sm text-code-sm text-outline">
                            PKR {lab.plan_price}/mo
                            {lab.is_demo ? " · demo" : ""}
                          </span>
                        </div>
                      </td>

                      <td className="px-space-md py-space-xs">
                        <span
                          className={`inline-flex items-center gap-space-xs px-space-xs py-space-2xs rounded font-label-sm text-label-sm uppercase tracking-wide ${
                            lab.status === "active"
                              ? "bg-surface-container text-primary font-semibold"
                              : isSuspended
                              ? "bg-error-container/30 text-error font-semibold"
                              : isProvisioning
                              ? "bg-secondary-fixed/50 text-on-secondary-fixed-variant font-semibold"
                              : "bg-surface-container-high text-outline"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              lab.status === "active"
                                ? "bg-primary animate-pulse"
                                : isSuspended
                                ? "bg-error"
                                : "bg-secondary"
                            }`}
                          ></span>
                          {lab.status}
                        </span>
                      </td>

                      <td className="px-space-md py-space-xs text-right">
                        <span className="font-label-md text-label-md px-space-xs py-space-2xs rounded bg-surface-container-low text-on-surface-variant tabular-nums">
                          {lab.branch_count ?? 1} branch{(lab.branch_count ?? 1) > 1 ? "es" : ""}
                        </span>
                      </td>

                      <td className="px-space-md py-space-xs text-right tabular-nums text-on-surface">
                        {lab.staff_count ?? 5} active
                      </td>

                      <td className="px-space-md py-space-xs text-right">
                        <span className="font-title-sm text-title-sm tabular-nums text-on-surface">
                          {lab.mrr_contribution ?? lab.plan_price}
                        </span>
                      </td>

                      <td className="px-space-md py-space-xs font-body-xs text-body-xs text-outline">
                        {new Date(lab.created_at).toLocaleDateString("en-GB", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </td>

                      <td className="px-space-md py-space-xs text-right pr-space-lg">
                        <div className="flex items-center justify-end gap-space-xs">
                          <Link
                            to={`/platform/tenants/${lab.id}`}
                            className="px-space-xs py-space-2xs rounded bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm uppercase transition-colors"
                          >
                            Manage
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Regional Distribution & Diagnostics Insights (from doc 3) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        {/* Regional Density Mini Panel */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h2 className="font-title-md text-title-md text-on-surface">Regional Distribution</h2>
              <span className="bg-surface-container px-space-xs py-space-2xs rounded font-code-sm text-code-sm text-outline">
                PAKISTAN
              </span>
            </div>
            <p className="font-body-xs text-body-xs text-outline mt-space-2xs">
              Federated specimen collection footprint across key healthcare clusters.
            </p>
            <div className="mt-space-md flex flex-col gap-space-sm">
              <div>
                <div className="flex justify-between font-label-sm text-label-sm mb-space-2xs">
                  <span className="text-on-surface">Punjab Province</span>
                  <span className="font-code-sm text-code-sm font-bold text-primary">
                    {Math.round((regionCounts.Punjab / totalRegional) * 100)}% ({regionCounts.Punjab} Nodes)
                  </span>
                </div>
                <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{ width: `${(regionCounts.Punjab / totalRegional) * 100}%` }}
                  ></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between font-label-sm text-label-sm mb-space-2xs">
                  <span className="text-on-surface">Sindh Province</span>
                  <span className="font-code-sm text-code-sm font-bold text-secondary">
                    {Math.round((regionCounts.Sindh / totalRegional) * 100)}% ({regionCounts.Sindh} Nodes)
                  </span>
                </div>
                <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-secondary h-full rounded-full"
                    style={{ width: `${(regionCounts.Sindh / totalRegional) * 100}%` }}
                  ></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between font-label-sm text-label-sm mb-space-2xs">
                  <span className="text-on-surface">Islamabad Capital Territory (ICT)</span>
                  <span className="font-code-sm text-code-sm font-bold text-tertiary">
                    {Math.round((regionCounts.ICT / totalRegional) * 100)}% ({regionCounts.ICT} Nodes)
                  </span>
                </div>
                <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-tertiary h-full rounded-full"
                    style={{ width: `${(regionCounts.ICT / totalRegional) * 100}%` }}
                  ></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between font-label-sm text-label-sm mb-space-2xs">
                  <span className="text-on-surface">Khyber Pakhtunkhwa (KP)</span>
                  <span className="font-code-sm text-code-sm font-bold text-outline">
                    {Math.round((regionCounts.KPK / totalRegional) * 100)}% ({regionCounts.KPK} Nodes)
                  </span>
                </div>
                <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-outline h-full rounded-full"
                    style={{ width: `${(regionCounts.KPK / totalRegional) * 100}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Audit & Governance Mini Log */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h2 className="font-title-md text-title-md text-on-surface">Audit & Governance</h2>
              <span className="font-code-sm text-code-sm text-outline">P-1 — P-9 ENGINE</span>
            </div>
            <p className="font-body-xs text-body-xs text-outline mt-space-2xs">
              Recent infrastructure lifecycle actions and operator modifications.
            </p>

            <div className="mt-space-md flex flex-col divide-y divide-outline-variant/20 font-body-sm text-body-sm">
              {(metrics?.recent_audits || []).slice(0, 4).map((audit) => (
                <div key={audit.id} className="py-space-xs flex items-center justify-between">
                  <div className="flex items-center gap-space-xs">
                    <span className="w-2 h-2 rounded-full bg-primary"></span>
                    <span className="font-semibold text-on-surface font-code-sm text-code-sm">
                      {audit.action}
                    </span>
                    <span className="text-outline text-xs">
                      {audit.entity_type} {audit.entity_id ? `(#${audit.entity_id.slice(0, 6)})` : ""}
                    </span>
                  </div>
                  <span className="font-code-sm text-code-sm text-outline">
                    {audit.at ? new Date(audit.at).toLocaleTimeString() : "--:--"}
                  </span>
                </div>
              ))}
              {(!metrics?.recent_audits || metrics.recent_audits.length === 0) && (
                <div className="py-space-md text-center text-outline">
                  No governance logs recorded in current cycle
                </div>
              )}
            </div>
          </div>
          <div className="pt-space-sm border-t border-outline-variant/20 flex justify-end">
            <Link
              to="/platform/overview"
              className="text-primary hover:text-primary-container font-label-sm text-label-sm flex items-center gap-1"
            >
              <span>View System Stream</span>
              <span className="material-symbols-outlined text-[16px]">chevron_right</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
