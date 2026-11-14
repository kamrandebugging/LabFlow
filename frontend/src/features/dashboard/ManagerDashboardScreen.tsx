import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

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
  type SampleStatusCounts,
} from "./dashboardService";
import {
  DashboardDateLine,
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
  const { t, i18n } = useTranslation("common");
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<ManagerData | null>(null);
  const [loading, setLoading] = useState(true);

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
          title={t("dashboard.manager.title")}
          subtitle={
            <DashboardDateLine
              suffix={t("dashboard.manager.subtitle_suffix")}
            />
          }
          badge={t("dashboard.manager.badge")}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-registrations-today"
            label={t("dashboard.stat.registrations_today")}
            value={loading ? "—" : (data?.registrationsToday ?? "—")}
            hint={t("dashboard.hint.registrations_manager")}
            icon="personal_injury"
          />
          <StatCard
            testId="stat-revenue-today"
            label={t("dashboard.stat.revenue_today")}
            value={loading ? "—" : formatPkr(data?.revenueToday, lang)}
            hint={t("dashboard.hint.revenue_today")}
            icon="payments"
          />
          <StatCard
            testId="stat-pending-approvals"
            label={t("dashboard.stat.pending_approvals")}
            value={loading ? "—" : formatCount(data?.pendingApprovals)}
            hint={t("dashboard.hint.pending_approvals")}
            icon="verified"
            tone="warning"
          />
          <StatCard
            testId="stat-exceptions"
            label={t("dashboard.exceptions")}
            value={loading ? "—" : formatCount(data?.exceptions?.total)}
            hint={t("dashboard.hint.exceptions")}
            icon="warning"
            tone="danger"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <Panel
            title={t("dashboard.samples_by_status")}
            subtitle={
              data?.samples ? (
                <Trans
                  i18nKey="dashboard.samples.accessions_in_scope"
                  values={{ total: data.samples.total }}
                  components={{ acc: <bdi dir="ltr" /> }}
                />
              ) : (
                <Trans
                  i18nKey="dashboard.samples.live_accession_counts"
                  components={{ acc: <bdi dir="ltr" /> }}
                />
              )
            }
            className="lg:col-span-2"
            testId="panel-samples-by-status"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.sample_counts")} />
            ) : data?.samples ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  [t("status.sample.collected"), data.samples.collected],
                  [t("status.sample.received"), data.samples.received],
                  [t("status.sample.in_process"), data.samples.inProcess],
                  [t("status.sample.ready"), data.samples.ready],
                  [t("status.sample.rejected"), data.samples.rejected],
                  [t("status.sample.cancelled"), data.samples.cancelled],
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
              <EmptyState message={t("dashboard.unavailable.samples")} />
            )}
            <div className="mt-4">
              <DashboardLink to="/samples">
                {t("dashboard.links.open_samples")}
              </DashboardLink>
            </div>
          </Panel>

          <Panel
            title={t("dashboard.exceptions")}
            subtitle={t("dashboard.manager.triage_subtitle")}
            testId="panel-exceptions"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.exception_counts")} />
            ) : data?.exceptions ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-slate-900">
                    {data.exceptions.total}
                  </span>
                  <span className="text-xs font-semibold uppercase tracking-wide text-red-700 bg-red-50 px-2 py-0.5 rounded">
                    {t("dashboard.requires_action_inline")}
                  </span>
                </div>
                <ul className="space-y-2 text-sm text-slate-700">
                  <li>
                    {t("dashboard.counts.late_transfers", {
                      count: data.exceptions.late_transfer,
                    })}
                  </li>
                  <li>
                    {t("dashboard.counts.failed_deliveries", {
                      count: data.exceptions.failed_delivery,
                    })}
                  </li>
                  <li>
                    {t("dashboard.counts.critical_results_unacknowledged", {
                      count: data.exceptions.critical_unacknowledged,
                    })}
                  </li>
                  <li>
                    {t("dashboard.counts.failed_generations", {
                      count: data.exceptions.failed_generation,
                    })}
                  </li>
                  <li>
                    {t("dashboard.counts.stuck_samples", {
                      count: data.exceptions.stuck_sample,
                    })}
                  </li>
                </ul>
              </div>
            ) : (
              <EmptyState message={t("dashboard.unavailable.exceptions")} />
            )}
            <div className="mt-4">
              <DashboardLink to="/exceptions">
                {t("dashboard.links.open_exceptions")}
              </DashboardLink>
            </div>
          </Panel>
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
                    {data.todayPatients.slice(0, 5).map((patient) => (
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
            title={t("dashboard.manager.scope_title")}
            subtitle={t("dashboard.manager.scope_subtitle")}
          >
            <ul className="space-y-3 text-sm text-slate-700">
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>{t("dashboard.scope.manager_restricted")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>{t("dashboard.scope.manager_catalog_owner")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  lock
                </span>
                <span>{t("dashboard.scope.manager_partner_ledger")}</span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
