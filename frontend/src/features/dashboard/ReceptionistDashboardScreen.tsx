import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

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
} from "./dashboardService";
import {
  DashboardDateLine,
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
  const { t, i18n } = useTranslation("common");
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<ReceptionData | null>(null);
  const [loading, setLoading] = useState(true);

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
          title={t("dashboard.reception.title")}
          subtitle={
            <DashboardDateLine
              suffix={t("dashboard.reception.subtitle_suffix")}
            />
          }
          badge={t("dashboard.reception.badge")}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-registrations-today"
            label={t("dashboard.stat.registrations_today")}
            value={loading ? "—" : (data?.registrationsToday ?? "—")}
            hint={t("dashboard.hint.registrations_reception")}
            icon="person_add"
          />
          <StatCard
            testId="stat-unpaid-invoices"
            label={t("dashboard.stat.unpaid_invoices")}
            value={
              loading
                ? "—"
                : data?.openInvoices
                  ? String(data.openInvoices.length)
                  : "—"
            }
            hint={
              loading ? (
                t("dashboard.stat.outstanding_unavailable")
              ) : data?.outstanding === null ||
                data?.outstanding === undefined ? (
                t("dashboard.stat.outstanding_unavailable")
              ) : (
                <Trans
                  i18nKey="dashboard.stat.outstanding"
                  values={{ amount: formatPkr(data.outstanding, lang) }}
                  components={{ amt: <bdi dir="ltr" /> }}
                />
              )
            }
            icon="receipt_long"
            tone="warning"
          />
          <StatCard
            testId="stat-awaiting-receipt"
            label={t("dashboard.stat.collected_awaiting_receipt")}
            value={loading ? "—" : (data?.collectedCount?.toString() ?? "—")}
            hint={t("dashboard.hint.collected_awaiting_receipt")}
            icon="science"
          />
          <StatCard
            testId="stat-awaiting-collection"
            label={t("dashboard.stat.awaiting_collection")}
            value={
              loading ? "—" : (data?.awaitingCollectionCount?.toString() ?? "—")
            }
            hint={t("dashboard.hint.awaiting_collection")}
            icon="pending_actions"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title={t("dashboard.panel.today_registrations")}
            subtitle={t("dashboard.panel.today_registrations_subtitle")}
            testId="panel-today-registrations"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.registrations")} />
            ) : data?.todayPatients === null ? (
              <EmptyState message={t("dashboard.unavailable.patients")} />
            ) : data?.todayPatients.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-start text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.patient")}
                      </th>
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.mrn")}
                      </th>
                      <th className="py-2 font-semibold">
                        {t("dashboard.table.branch")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.todayPatients.slice(0, 6).map((patient) => (
                      <tr key={patient.id}>
                        <td className="py-2.5 pe-3 font-medium text-slate-900">
                          {patient.name}
                        </td>
                        <td className="py-2.5 pe-3 font-mono text-xs text-slate-600">
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
              <EmptyState message={t("dashboard.empty.no_patients_today")} />
            )}
            <div className="mt-4">
              <DashboardLink to="/patients">
                {t("dashboard.links.open_patients")}
              </DashboardLink>
            </div>
          </Panel>

          <Panel
            title={t("dashboard.stat.unpaid_invoices")}
            subtitle={t("dashboard.reception.unpaid_subtitle")}
            testId="panel-unpaid-invoices"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.invoices")} />
            ) : data?.openInvoices === null ? (
              <EmptyState message={t("dashboard.unavailable.invoices")} />
            ) : data?.openInvoices.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-start text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.patient")}
                      </th>
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.mrn")}
                      </th>
                      <th className="py-2 text-end font-semibold">
                        {t("dashboard.table.balance")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.openInvoices.slice(0, 6).map((invoice) => (
                      <tr key={invoice.id}>
                        <td className="py-2.5 pe-3 font-medium text-slate-900">
                          {invoice.patient_name ?? "—"}
                        </td>
                        <td className="py-2.5 pe-3 font-mono text-xs text-slate-600">
                          {invoice.patient_mrn ?? "—"}
                        </td>
                        <td className="py-2.5 text-end font-mono text-xs font-semibold text-slate-900">
                          {formatPkr(outstandingBalance(invoice), lang)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message={t("dashboard.empty.no_unpaid_invoices")} />
            )}
            <div className="mt-4">
              <DashboardLink to="/invoices">
                {t("dashboard.links.open_invoices")}
              </DashboardLink>
            </div>
          </Panel>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title={t("dashboard.reception.awaiting_receipt_title")}
            subtitle={t("dashboard.reception.awaiting_receipt_subtitle")}
            testId="panel-awaiting-receipt"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.sample_handoff")} />
            ) : data?.collectedSamples === null ? (
              <EmptyState message={t("dashboard.unavailable.samples")} />
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
                      {t("dashboard.reception.collected_badge")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("dashboard.empty.no_collected_waiting")} />
            )}
            {data?.collectedCount !== null &&
            data?.collectedCount !== undefined &&
            data.collectedCount > (data.collectedSamples?.length ?? 0) ? (
              <p className="text-xs text-slate-500 mt-3">
                {t("dashboard.reception.showing_first", {
                  shown: data.collectedSamples?.length ?? 0,
                  total: data.collectedCount,
                })}
              </p>
            ) : null}
            <div className="mt-4">
              <DashboardLink to="/samples">
                {t("dashboard.links.open_samples")}
              </DashboardLink>
            </div>
          </Panel>

          <Panel
            title={t("dashboard.stat.awaiting_collection")}
            subtitle={t("dashboard.reception.awaiting_collection_subtitle")}
            testId="panel-awaiting-collection"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.collection_queue")} />
            ) : data?.awaitingCollection === null ? (
              <EmptyState message={t("dashboard.unavailable.samples")} />
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
                      <bdi dir="ltr">
                        {new Date(item.ordered_at).toLocaleDateString("en-PK", {
                          day: "numeric",
                          month: "short",
                        })}
                      </bdi>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                message={t("dashboard.empty.no_awaiting_collection")}
              />
            )}
            <div className="mt-4">
              <DashboardLink to="/samples">
                {t("dashboard.links.open_samples")}
              </DashboardLink>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
