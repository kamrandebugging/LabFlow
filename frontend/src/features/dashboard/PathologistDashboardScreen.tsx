import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "../auth/authStore";
import { resultsService } from "../results/resultsService";
import type { ApprovalQueueItem, ResultDetailRecord } from "../results/types";
import { formatCount, isTodayInPkt } from "./dashboardService";
import {
  DashboardDateLine,
  DashboardHeader,
  DashboardLink,
  EmptyState,
  Panel,
  StatCard,
} from "./DashboardUI";

interface PathologistData {
  approvals: ApprovalQueueItem[] | null;
  approved: ResultDetailRecord[] | null;
}

export function PathologistDashboardScreen(): ReactElement {
  const { t } = useTranslation("common");
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<PathologistData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const load = async () => {
      if (!accessToken) {
        if (active) setLoading(false);
        return;
      }

      const [approvalsResult, approvedResult] = await Promise.allSettled([
        resultsService.getApprovalsQueue(controller.signal),
        resultsService.listResults("approved", controller.signal),
      ]);

      if (!active) return;

      setData({
        approvals:
          approvalsResult.status === "fulfilled" ? approvalsResult.value : null,
        approved:
          approvedResult.status === "fulfilled" ? approvedResult.value : null,
      });
      setLoading(false);
    };

    void load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken]);

  const criticalCount = data?.approvals
    ? data.approvals.filter((item) => item.is_critical).length
    : null;
  const routineCount =
    data?.approvals && criticalCount !== null
      ? data.approvals.length - criticalCount
      : null;
  const datedApprovals = data?.approved
    ? data.approved.filter((result) => Boolean(result.approved_at))
    : null;
  const approvedToday = datedApprovals
    ? datedApprovals.filter((result) => isTodayInPkt(result.approved_at)).length
    : null;
  const recentApprovals = datedApprovals
    ? [...datedApprovals]
        .sort(
          (a, b) =>
            new Date(b.approved_at ?? 0).getTime() -
            new Date(a.approved_at ?? 0).getTime(),
        )
        .slice(0, 6)
    : null;

  return (
    <div className="p-8">
      <div className="flex flex-col w-full max-w-7xl mx-auto">
        <DashboardHeader
          title={t("dashboard.pathologist.title")}
          subtitle={
            <DashboardDateLine
              suffix={t("dashboard.pathologist.subtitle_suffix")}
            />
          }
          badge={t("role.pathologist")}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-awaiting-verification"
            label={t("dashboard.stat.results_awaiting_verification")}
            value={loading ? "—" : formatCount(data?.approvals?.length ?? null)}
            hint={t("dashboard.hint.awaiting_verification")}
            icon="pending_actions"
          />
          <StatCard
            testId="stat-critical"
            label={t("status.flag.critical")}
            value={loading ? "—" : formatCount(criticalCount)}
            hint={t("dashboard.hint.critical")}
            icon="crisis_alert"
            tone="danger"
          />
          <StatCard
            testId="stat-routine"
            label={t("dashboard.stat.routine")}
            value={loading ? "—" : formatCount(routineCount)}
            hint={t("dashboard.hint.routine")}
            icon="fact_check"
          />
          <StatCard
            testId="stat-recent-approvals"
            label={t("dashboard.stat.approved_today")}
            value={loading ? "—" : formatCount(approvedToday)}
            hint={t("dashboard.hint.approved_today")}
            icon="verified"
            tone="success"
          />
        </div>

        <Panel
          title={t("dashboard.pathologist.priority_queue")}
          subtitle={t("dashboard.pathologist.priority_subtitle")}
          className="mt-6"
          testId="panel-approvals"
          action={
            <DashboardLink to="/results/approvals">
              {t("dashboard.links.open_approvals")}
            </DashboardLink>
          }
        >
          {loading ? (
            <EmptyState message={t("dashboard.loading.approvals")} />
          ) : data?.approvals === null ? (
            <EmptyState message={t("dashboard.unavailable.approvals")} />
          ) : data?.approvals.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-start text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.patient")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.accession")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.test")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.value")}
                    </th>
                    <th className="py-2 pe-3 font-semibold">
                      {t("dashboard.table.entered_by")}
                    </th>
                    <th className="py-2 font-semibold">
                      {t("dashboard.table.waiting")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.approvals.slice(0, 6).map((item) => (
                    <tr
                      key={item.result_id}
                      className={item.is_critical ? "bg-red-50/50" : undefined}
                    >
                      <td className="py-2.5 pe-3 font-medium text-slate-900">
                        <div className="flex items-center gap-2">
                          {item.patient_name}
                          {item.is_critical ? (
                            <span className="text-[10px] font-bold uppercase tracking-wide text-red-700 bg-red-100 px-1.5 py-0.5 rounded">
                              {t("dashboard.critical_badge")}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="py-2.5 pe-3 font-mono text-xs text-slate-600">
                        {item.accession_id}
                      </td>
                      <td className="py-2.5 pe-3 text-slate-700">
                        {item.test_name}
                      </td>
                      <td className="py-2.5 pe-3 font-mono text-xs text-slate-900">
                        {item.value} {item.unit}
                      </td>
                      <td className="py-2.5 pe-3 text-xs text-slate-600">
                        {item.entered_by_name}
                      </td>
                      <td className="py-2.5 font-mono text-xs text-slate-600">
                        {item.waiting_time}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              message={t("dashboard.empty.no_awaiting_verification")}
            />
          )}
        </Panel>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title={t("dashboard.pathologist.recent_title")}
            subtitle={t("dashboard.pathologist.recent_subtitle")}
            testId="panel-recent-approvals"
          >
            {loading ? (
              <EmptyState message={t("dashboard.loading.recent_approvals")} />
            ) : recentApprovals === null ? (
              <EmptyState message={t("dashboard.unavailable.results")} />
            ) : recentApprovals.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-start text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.patient")}
                      </th>
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.accession")}
                      </th>
                      <th className="py-2 pe-3 font-semibold">
                        {t("dashboard.table.test")}
                      </th>
                      <th className="py-2 font-semibold">
                        {t("dashboard.table.value")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {recentApprovals.map((result) => (
                      <tr key={result.id}>
                        <td className="py-2.5 pe-3 font-medium text-slate-900">
                          {result.patient_name}
                        </td>
                        <td className="py-2.5 pe-3 font-mono text-xs text-slate-600">
                          {result.accession_id}
                        </td>
                        <td className="py-2.5 pe-3 text-slate-700">
                          {result.test_name}
                        </td>
                        <td className="py-2.5 font-mono text-xs text-slate-900">
                          {result.value} {result.unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message={t("dashboard.empty.no_recent_approvals")} />
            )}
          </Panel>

          <Panel
            title={t("dashboard.pathologist.scope_title")}
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
                <span>{t("dashboard.scope.pathologist_approve")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  check_circle
                </span>
                <span>{t("dashboard.scope.pathologist_reference")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  block
                </span>
                <span>{t("dashboard.scope.pathologist_billing")}</span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
