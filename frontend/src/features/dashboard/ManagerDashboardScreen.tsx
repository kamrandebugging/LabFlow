import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useAuthStore } from "../auth/authStore";
import { billingService } from "../billing/billingService";
import { patientService } from "../patients/patientService";
import type { PatientSummary } from "../patients/types";
import { reportsService } from "../reports/reportsService";
import type { ExceptionCounts } from "../reports/types";
import { resultsService } from "../results/resultsService";
import {
  fetchSampleStatusCounts,
  formatCount,
  formatPkr,
  isTodayInPkt,
  PKT_LABEL,
  pktDateLabel,
  type SampleStatusCounts,
} from "./dashboardService";
import {
  DashboardHeader,
  DashboardLink,
  EmptyState,
  Panel,
  StatCard,
} from "./DashboardUI";

interface ManagerData {
  registrationsToday: string | null;
  todayPatients: PatientSummary[] | null;
  revenueToday: string | null;
  pendingApprovals: number | null;
  exceptions: ExceptionCounts | null;
  samples: SampleStatusCounts | null;
}

export function ManagerDashboardScreen(): ReactElement {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<ManagerData | null>(null);
  const [loading, setLoading] = useState(true);

  const dateLabel = `${pktDateLabel()} · ${PKT_LABEL}`;

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const load = async () => {
      if (!accessToken) {
        if (active) setLoading(false);
        return;
      }

      const [
        patientsResult,
        invoicesResult,
        approvalsResult,
        exceptionsResult,
        samplesResult,
      ] = await Promise.allSettled([
        patientService.listPatients({ signal: controller.signal }),
        billingService.listInvoices({ limit: 1, signal: controller.signal }),
        resultsService.getApprovalsQueue(controller.signal),
        reportsService.getExceptions(controller.signal),
        fetchSampleStatusCounts(controller.signal),
      ]);

      if (!active) return;

      const todayPatients =
        patientsResult.status === "fulfilled"
          ? patientsResult.value.filter((patient) =>
              isTodayInPkt(patient.created_at),
            )
          : null;

      setData({
        registrationsToday:
          todayPatients === null
            ? null
            : todayPatients.length >= 100
              ? "100+"
              : String(todayPatients.length),
        todayPatients,
        revenueToday:
          invoicesResult.status === "fulfilled"
            ? (invoicesResult.value.daily_total ?? null)
            : null,
        pendingApprovals:
          approvalsResult.status === "fulfilled"
            ? approvalsResult.value.length
            : null,
        exceptions:
          exceptionsResult.status === "fulfilled"
            ? exceptionsResult.value.counts
            : null,
        samples:
          samplesResult.status === "fulfilled" ? samplesResult.value : null,
      });
      setLoading(false);
    };

    void load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken]);

  return (
    <div className="p-8">
      <div className="flex flex-col w-full max-w-7xl mx-auto">
        <DashboardHeader
          title="Branch operations"
          subtitle={`${dateLabel} · read-only overview`}
          badge="Manager view"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-registrations-today"
            label="Registrations today"
            value={loading ? "—" : (data?.registrationsToday ?? "—")}
            hint="Patients registered in your branches today (PKT)."
            icon="personal_injury"
          />
          <StatCard
            testId="stat-revenue-today"
            label="Invoiced today"
            value={loading ? "—" : formatPkr(data?.revenueToday)}
            hint="Server total of today's non-cancelled invoices; not cash collected."
            icon="payments"
          />
          <StatCard
            testId="stat-pending-approvals"
            label="Pending approvals"
            value={loading ? "—" : formatCount(data?.pendingApprovals)}
            hint="Results awaiting a Pathologist or Owner decision."
            icon="verified"
            tone="warning"
          />
          <StatCard
            testId="stat-exceptions"
            label="Exceptions"
            value={loading ? "—" : formatCount(data?.exceptions?.total)}
            hint="Open operational exceptions across the lab."
            icon="warning"
            tone="danger"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <Panel
            title="Samples by status"
            subtitle={
              data?.samples
                ? `${data.samples.total} accessions in scope`
                : "Live accession counts"
            }
            className="lg:col-span-2"
            testId="panel-samples-by-status"
          >
            {loading ? (
              <EmptyState message="Loading sample counts…" />
            ) : data?.samples ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  ["Collected", data.samples.collected],
                  ["Received", data.samples.received],
                  ["In process", data.samples.inProcess],
                  ["Ready", data.samples.ready],
                  ["Rejected", data.samples.rejected],
                  ["Cancelled", data.samples.cancelled],
                ].map(([label, value]) => (
                  <div
                    key={String(label)}
                    className="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 flex items-center justify-between"
                  >
                    <span className="text-sm font-medium text-slate-600">
                      {label}
                    </span>
                    <span className="font-mono text-sm font-semibold text-slate-900">
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="Unavailable — the samples API did not respond." />
            )}
            <div className="mt-4">
              <DashboardLink to="/samples">Open samples</DashboardLink>
            </div>
          </Panel>

          <Panel
            title="Exceptions"
            subtitle="Read-only operational triage"
            testId="panel-exceptions"
          >
            {loading ? (
              <EmptyState message="Loading exception counts…" />
            ) : data?.exceptions ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-slate-900">
                    {data.exceptions.total}
                  </span>
                  <span className="text-xs font-semibold uppercase tracking-wide text-red-700 bg-red-50 px-2 py-0.5 rounded">
                    requires action
                  </span>
                </div>
                <ul className="space-y-2 text-sm text-slate-700">
                  <li>{data.exceptions.late_transfer} late sample transfers</li>
                  <li>
                    {data.exceptions.failed_delivery} failed report deliveries
                  </li>
                  <li>
                    {data.exceptions.critical_unacknowledged} critical results
                    unacknowledged
                  </li>
                  <li>
                    {data.exceptions.failed_generation} failed report
                    generations
                  </li>
                  <li>{data.exceptions.stuck_sample} stuck samples</li>
                </ul>
              </div>
            ) : (
              <EmptyState message="Unavailable — the exceptions API did not respond." />
            )}
            <div className="mt-4">
              <DashboardLink to="/exceptions">Open exceptions</DashboardLink>
            </div>
          </Panel>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title="Today's registrations"
            subtitle="Real patient rows created today (PKT)"
            testId="panel-today-registrations"
          >
            {loading ? (
              <EmptyState message="Loading registrations…" />
            ) : data?.todayPatients === null ? (
              <EmptyState message="Unavailable — the patient API did not respond." />
            ) : data?.todayPatients.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pr-3 font-semibold">Patient</th>
                      <th className="py-2 pr-3 font-semibold">MRN</th>
                      <th className="py-2 font-semibold">Branch</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.todayPatients.slice(0, 5).map((patient) => (
                      <tr key={patient.id}>
                        <td className="py-2.5 pr-3 font-medium text-slate-900">
                          {patient.name}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">
                          {patient.mrn}
                        </td>
                        <td className="py-2.5 text-slate-600">
                          {patient.branch_name ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No patients were registered today." />
            )}
            <div className="mt-4">
              <DashboardLink to="/patients">Open patients</DashboardLink>
            </div>
          </Panel>

          <Panel
            title="Manager scope"
            subtitle="Summaries only — clinical and financial decisions stay with their roles"
          >
            <ul className="space-y-3 text-sm text-slate-700">
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>
                  Result approval is restricted to Pathologists and the Owner.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>
                  Catalog and price edits are Owner-only; this dashboard never
                  exposes an edit action.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>
                  Partner registry and share-ledger writes stay with the Owner.
                </span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
