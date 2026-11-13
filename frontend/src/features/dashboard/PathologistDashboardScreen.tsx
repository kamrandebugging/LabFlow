import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useAuthStore } from "../auth/authStore";
import { resultsService } from "../results/resultsService";
import type { ApprovalQueueItem, ResultDetailRecord } from "../results/types";
import {
  formatCount,
  isTodayInPkt,
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

interface PathologistData {
  approvals: ApprovalQueueItem[] | null;
  approved: ResultDetailRecord[] | null;
}

export function PathologistDashboardScreen(): ReactElement {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<PathologistData | null>(null);
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
          title="Clinical approvals"
          subtitle={`${dateLabel} · results awaiting your verification`}
          badge="Pathologist"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-awaiting-verification"
            label="Results awaiting verification"
            value={loading ? "—" : formatCount(data?.approvals?.length ?? null)}
            hint="Entered result rows waiting for a clinical decision."
            icon="pending_actions"
          />
          <StatCard
            testId="stat-critical"
            label="Critical"
            value={loading ? "—" : formatCount(criticalCount)}
            hint="Critical panic values in the queue."
            icon="crisis_alert"
            tone="danger"
          />
          <StatCard
            testId="stat-routine"
            label="Routine"
            value={loading ? "—" : formatCount(routineCount)}
            hint="Non-critical result rows in the queue."
            icon="fact_check"
          />
          <StatCard
            testId="stat-recent-approvals"
            label="Approved today"
            value={loading ? "—" : formatCount(approvedToday)}
            hint="Approved result rows whose approval timestamp is today (PKT)."
            icon="verified"
            tone="success"
          />
        </div>

        <Panel
          title="Priority approvals queue"
          subtitle="Critical first, then longest waiting — real result rows"
          className="mt-6"
          testId="panel-approvals"
          action={
            <DashboardLink to="/results/approvals">
              Open approvals
            </DashboardLink>
          }
        >
          {loading ? (
            <EmptyState message="Loading approvals…" />
          ) : data?.approvals === null ? (
            <EmptyState message="Unavailable — the approvals API did not respond." />
          ) : data?.approvals.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                    <th className="py-2 pr-3 font-semibold">Patient</th>
                    <th className="py-2 pr-3 font-semibold">Accession</th>
                    <th className="py-2 pr-3 font-semibold">Test</th>
                    <th className="py-2 pr-3 font-semibold">Value</th>
                    <th className="py-2 pr-3 font-semibold">Entered by</th>
                    <th className="py-2 font-semibold">Waiting</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.approvals.slice(0, 6).map((item) => (
                    <tr
                      key={item.result_id}
                      className={item.is_critical ? "bg-red-50/50" : undefined}
                    >
                      <td className="py-2.5 pr-3 font-medium text-slate-900">
                        <div className="flex items-center gap-2">
                          {item.patient_name}
                          {item.is_critical ? (
                            <span className="text-[10px] font-bold uppercase tracking-wide text-red-700 bg-red-100 px-1.5 py-0.5 rounded">
                              critical
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">
                        {item.accession_id}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-700">
                        {item.test_name}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-900">
                        {item.value} {item.unit}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-slate-600">
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
            <EmptyState message="No results are awaiting verification." />
          )}
        </Panel>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title="Recent approvals"
            subtitle="Newest approval first — real rows from the results API"
            testId="panel-recent-approvals"
          >
            {loading ? (
              <EmptyState message="Loading recent approvals…" />
            ) : recentApprovals === null ? (
              <EmptyState message="Unavailable — the results API did not respond." />
            ) : recentApprovals.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                      <th className="py-2 pr-3 font-semibold">Patient</th>
                      <th className="py-2 pr-3 font-semibold">Accession</th>
                      <th className="py-2 pr-3 font-semibold">Test</th>
                      <th className="py-2 font-semibold">Value</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {recentApprovals.map((result) => (
                      <tr key={result.id}>
                        <td className="py-2.5 pr-3 font-medium text-slate-900">
                          {result.patient_name}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">
                          {result.accession_id}
                        </td>
                        <td className="py-2.5 pr-3 text-slate-700">
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
              <EmptyState message="No approved results are available yet." />
            )}
          </Panel>

          <Panel
            title="Clinical scope"
            subtitle="What this role can and cannot do"
          >
            <ul className="space-y-3 text-sm text-slate-700">
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  check_circle
                </span>
                <span>
                  Approve or reject entered results, amend results, and record
                  critical notifications.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  check_circle
                </span>
                <span>
                  Review each result against its reference range before
                  approving.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-teal-700"
                >
                  block
                </span>
                <span>
                  Invoicing, payments and partner settlements are not part of
                  this role.
                </span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
