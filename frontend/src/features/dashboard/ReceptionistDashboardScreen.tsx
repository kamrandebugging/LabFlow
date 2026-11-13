import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useAuthStore } from "../auth/authStore";
import { patientService } from "../patients/patientService";
import type { PatientSummary } from "../patients/types";
import { sampleService } from "../samples/sampleService";
import type { AwaitingCollectionItem, SampleSummary } from "../samples/types";
import {
  formatPkr,
  isTodayInPkt,
  listOpenInvoices,
  outstandingBalance,
  PKT_LABEL,
  pktDateLabel,
} from "./dashboardService";
import {
  DashboardHeader,
  DashboardLink,
  EmptyState,
  Panel,
  StatCard,
} from "./DashboardUI";
import type { InvoiceSummary } from "../billing/types";

interface ReceptionData {
  registrationsToday: string | null;
  todayPatients: PatientSummary[] | null;
  openInvoices: InvoiceSummary[] | null;
  outstanding: number | null;
  collectedCount: number | null;
  collectedSamples: SampleSummary[] | null;
  awaitingCollectionCount: number | null;
  awaitingCollection: AwaitingCollectionItem[] | null;
}

export function ReceptionistDashboardScreen(): ReactElement {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<ReceptionData | null>(null);
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

      const [patientsResult, invoicesResult, samplesResult, awaitingResult] =
        await Promise.allSettled([
          patientService.listPatients({ signal: controller.signal }),
          listOpenInvoices(controller.signal),
          sampleService.listSamples({ status: "collected" }, controller.signal),
          sampleService.listAwaitingCollection(controller.signal),
        ]);

      if (!active) return;

      const todayPatients =
        patientsResult.status === "fulfilled"
          ? patientsResult.value.filter((patient) =>
              isTodayInPkt(patient.created_at),
            )
          : null;

      const openInvoices =
        invoicesResult.status === "fulfilled" ? invoicesResult.value : null;

      let outstanding: number | null = null;
      if (openInvoices) {
        const balances = openInvoices.map(outstandingBalance);
        outstanding = balances.some((value) => value === null)
          ? null
          : balances.reduce<number>((sum, value) => sum + (value ?? 0), 0);
      }

      setData({
        registrationsToday:
          todayPatients === null
            ? null
            : todayPatients.length >= 100
              ? "100+"
              : String(todayPatients.length),
        todayPatients,
        openInvoices,
        outstanding,
        collectedCount:
          samplesResult.status === "fulfilled"
            ? samplesResult.value.total
            : null,
        collectedSamples:
          samplesResult.status === "fulfilled"
            ? samplesResult.value.results
            : null,
        awaitingCollectionCount:
          awaitingResult.status === "fulfilled"
            ? awaitingResult.value.total
            : null,
        awaitingCollection:
          awaitingResult.status === "fulfilled"
            ? awaitingResult.value.results
            : null,
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
          title="Front desk"
          subtitle={`${dateLabel} · registrations, billing and sample handoff`}
          badge="Reception"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-registrations-today"
            label="Registrations today"
            value={loading ? "—" : (data?.registrationsToday ?? "—")}
            hint="Patients registered at your desk today (PKT)."
            icon="person_add"
          />
          <StatCard
            testId="stat-unpaid-invoices"
            label="Unpaid invoices"
            value={
              loading
                ? "—"
                : data?.openInvoices
                  ? String(data.openInvoices.length)
                  : "—"
            }
            hint={
              loading
                ? "Outstanding balance unavailable"
                : data?.outstanding === null || data?.outstanding === undefined
                  ? "Outstanding balance unavailable"
                  : `${formatPkr(data.outstanding)} outstanding`
            }
            icon="receipt_long"
            tone="warning"
          />
          <StatCard
            testId="stat-awaiting-receipt"
            label="Collected, awaiting receipt"
            value={loading ? "—" : (data?.collectedCount?.toString() ?? "—")}
            hint="Samples collected at the desk and not yet received by the lab."
            icon="science"
          />
          <StatCard
            testId="stat-awaiting-collection"
            label="Awaiting collection"
            value={
              loading ? "—" : (data?.awaitingCollectionCount?.toString() ?? "—")
            }
            hint="Ordered tests with no accession yet (branch scope)."
            icon="pending_actions"
          />
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
                    {data.todayPatients.slice(0, 6).map((patient) => (
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
            title="Unpaid invoices"
            subtitle="Unpaid and partially paid invoices in your branch scope"
            testId="panel-unpaid-invoices"
          >
            {loading ? (
              <EmptyState message="Loading invoices…" />
            ) : data?.openInvoices === null ? (
              <EmptyState message="Unavailable — the invoice API did not respond." />
            ) : data?.openInvoices.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pr-3 font-semibold">Patient</th>
                      <th className="py-2 pr-3 font-semibold">MRN</th>
                      <th className="py-2 text-right font-semibold">Balance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.openInvoices.slice(0, 6).map((invoice) => (
                      <tr key={invoice.id}>
                        <td className="py-2.5 pr-3 font-medium text-slate-900">
                          {invoice.patient_name ?? "—"}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">
                          {invoice.patient_mrn ?? "—"}
                        </td>
                        <td className="py-2.5 text-right font-mono text-xs font-semibold text-slate-900">
                          {formatPkr(outstandingBalance(invoice))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No unpaid invoices in your branch scope." />
            )}
            <div className="mt-4">
              <DashboardLink to="/invoices">Open invoices</DashboardLink>
            </div>
          </Panel>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title="Samples awaiting lab receipt"
            subtitle="Collected specimens currently held at the desk"
            testId="panel-awaiting-receipt"
          >
            {loading ? (
              <EmptyState message="Loading sample handoff…" />
            ) : data?.collectedSamples === null ? (
              <EmptyState message="Unavailable — the samples API did not respond." />
            ) : data?.collectedSamples.length ? (
              <ul className="divide-y divide-slate-100">
                {data.collectedSamples.slice(0, 6).map((sample) => (
                  <li
                    key={sample.id}
                    className="py-2.5 flex items-center justify-between gap-3 text-sm"
                  >
                    <div>
                      <p className="font-medium text-slate-900">
                        {sample.patient_name}
                      </p>
                      <p className="font-mono text-xs text-slate-500">
                        {sample.accession_id}
                      </p>
                    </div>
                    <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
                      collected
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="No collected samples are waiting for receipt." />
            )}
            {data?.collectedCount !== null &&
            data?.collectedCount !== undefined &&
            data.collectedCount > (data.collectedSamples?.length ?? 0) ? (
              <p className="text-xs text-slate-500 mt-3">
                Showing the first {data.collectedSamples?.length ?? 0} of{" "}
                {data.collectedCount} collected samples.
              </p>
            ) : null}
            <div className="mt-4">
              <DashboardLink to="/samples">Open samples</DashboardLink>
            </div>
          </Panel>

          <Panel
            title="Awaiting collection"
            subtitle="Requested tests with no accession yet"
            testId="panel-awaiting-collection"
          >
            {loading ? (
              <EmptyState message="Loading collection queue…" />
            ) : data?.awaitingCollection === null ? (
              <EmptyState message="Unavailable — the samples API did not respond." />
            ) : data?.awaitingCollection.length ? (
              <ul className="divide-y divide-slate-100">
                {data.awaitingCollection.slice(0, 6).map((item) => (
                  <li
                    key={item.invoice_item_id}
                    className="py-2.5 flex items-center justify-between gap-3 text-sm"
                  >
                    <div>
                      <p className="font-medium text-slate-900">
                        {item.patient_name}
                      </p>
                      <p className="font-mono text-xs text-slate-500">
                        {item.patient_mrn} ·{" "}
                        {item.test_name ?? item.panel_name ?? item.description}
                      </p>
                    </div>
                    <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded whitespace-nowrap">
                      {new Date(item.ordered_at).toLocaleDateString("en-PK", {
                        day: "numeric",
                        month: "short",
                      })}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="No ordered tests are awaiting collection." />
            )}
            <div className="mt-4">
              <DashboardLink to="/samples">Open samples</DashboardLink>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
