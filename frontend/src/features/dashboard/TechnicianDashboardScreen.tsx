import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { useAuthStore } from "../auth/authStore";
import { resultsService } from "../results/resultsService";
import type { ResultDetailRecord, WorklistItem } from "../results/types";
import {
  fetchSampleStatusCounts,
  formatCount,
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

interface TechnicianData {
  worklist: WorklistItem[] | null;
  sampleCounts: SampleStatusCounts | null;
  criticalResults: ResultDetailRecord[] | null;
}

export function TechnicianDashboardScreen(): ReactElement {
  const { t } = useTranslation("common");
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<TechnicianData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const load = async () => {
      if (!accessToken) {
        if (active) setLoading(false);
        return;
      }

      const [worklistResult, countsResult, enteredResult] =
        await Promise.allSettled([
          resultsService.getWorklist({ signal: controller.signal }),
          fetchSampleStatusCounts(controller.signal),
          resultsService.listResults("entered", controller.signal),
        ]);

      if (!active) return;

      setData({
        worklist:
          worklistResult.status === "fulfilled" ? worklistResult.value : null,
        sampleCounts:
          countsResult.status === "fulfilled" ? countsResult.value : null,
        criticalResults:
          enteredResult.status === "fulfilled"
            ? enteredResult.value.filter((result) => result.is_critical)
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

  const worklistCount = data?.sampleCounts
    ? data.sampleCounts.collected +
      data.sampleCounts.received +
      data.sampleCounts.inProcess +
      data.sampleCounts.rejected
    : null;
  const awaitingResultEntry = data?.sampleCounts
    ? data.sampleCounts.received + data.sampleCounts.inProcess
    : null;

  return (
    <div className="p-8">
      <div className="flex flex-col w-full max-w-7xl mx-auto">
        <DashboardHeader
          title={t("dashboard.technician.title")}
          subtitle={
            <DashboardDateLine
              suffix={t("dashboard.technician.subtitle_suffix")}
            />
          }
          badge={t("dashboard.technician.badge")}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-worklist"
            label={t("nav.worklist")}
            value={loading ? "—" : formatCount(worklistCount)}
            hint={
              <Trans
                i18nKey="dashboard.hint.worklist"
                components={{ acc: <bdi dir="ltr" /> }}
              />
            }
            icon="assignment"
          />
          <StatCard
            testId="stat-awaiting-receipt"
            label={t("dashboard.stat.awaiting_receipt")}
            value={
              loading ? "—" : formatCount(data?.sampleCounts?.collected ?? null)
            }
            hint={t("dashboard.hint.awaiting_receipt")}
            icon="inventory"
            tone="warning"
          />
          <StatCard
            testId="stat-awaiting-result-entry"
            label={t("dashboard.stat.awaiting_result_entry")}
            value={loading ? "—" : formatCount(awaitingResultEntry)}
            hint={t("dashboard.hint.awaiting_result_entry")}
            icon="edit_note"
          />
          <StatCard
            testId="stat-critical-pending"
            label={t("dashboard.stat.critical_pending")}
            value={
              loading ? "—" : formatCount(data?.criticalResults?.length ?? null)
            }
            hint={t("dashboard.hint.critical_pending")}
            icon="crisis_alert"
            tone="danger"
          />
        </div>

        <Panel
          title={t("nav.worklist")}
          subtitle={
            <Trans
              i18nKey="dashboard.technician.worklist_subtitle"
              components={{ acc: <bdi dir="ltr" /> }}
            />
          }
          className="mt-6"
          testId="panel-worklist"
          action={
            <DashboardLink to="/worklist">
              {t("dashboard.links.open_worklist")}
            </DashboardLink>
          }
        >
          {loading ? (
            <EmptyState message={t("dashboard.loading.worklist")} />
          ) : data?.worklist === null ? (
            <EmptyState message={t("dashboard.unavailable.worklist")} />
          ) : data?.worklist.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-start text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.accession")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.patient")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.tests")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.waiting")}
                    </th>
                    <th className="py-2 font-semibold">{t("labels.status")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.worklist.slice(0, 6).map((item) => (
                    <tr key={item.sample_id}>
                      <td className="py-2.5 pe-3 font-mono text-xs text-slate-700">
                        {item.accession_id}
                      </td>
                      <td className="py-2.5 pe-3 font-medium text-slate-900">
                        {item.patient_name}
                      </td>
                      <td className="py-2.5 pe-3 text-slate-600">
                        {item.tests.length ? item.tests.join(", ") : "—"}
                      </td>
                      <td className="py-2.5 pe-3 font-mono text-xs text-slate-600">
                        {item.waiting_time}
                      </td>
                      <td className="py-2.5">
                        <span className="text-xs font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                          {t(
                            `status.sample.${item.sample_status ?? item.status}`,
                          )}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message={t("dashboard.empty.no_bench_samples")} />
          )}
        </Panel>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title={t("dashboard.technician.critical_title")}
            subtitle={t("dashboard.technician.critical_subtitle")}
            testId="panel-critical-results"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.critical_results")} />
            ) : data?.criticalResults === null ? (
              <EmptyState message={t("dashboard.unavailable.results")} />
            ) : data?.criticalResults.length ? (
              <ul className="divide-y divide-slate-100">
                {data.criticalResults.slice(0, 6).map((result) => (
                  <li
                    key={result.id}
                    className="py-2.5 flex items-center justify-between gap-3 text-sm"
                  >
                    <div>
                      <p className="font-medium text-slate-900">
                        {result.patient_name}
                      </p>
                      <p className="text-xs text-slate-500">
                        {result.test_name} · {result.value} {result.unit}
                      </p>
                    </div>
                    <span className="text-xs font-semibold text-red-700 bg-red-50 px-2 py-0.5 rounded uppercase">
                      {result.flag}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("dashboard.empty.no_critical_pending")} />
            )}
          </Panel>

          <Panel
            title={t("dashboard.technician.scope_title")}
            subtitle={t("dashboard.scope.subtitle")}
          >
            <ul className="space-y-3 text-sm text-slate-700">
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  check_circle
                </span>
                <span>{t("dashboard.scope.technician_receive")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  block
                </span>
                <span>{t("dashboard.scope.technician_billing_hidden")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  block
                </span>
                <span>{t("dashboard.scope.technician_approval_owner")}</span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
