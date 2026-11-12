import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useAuthStore } from "../auth/authStore";
import { resultsService } from "../results/resultsService";
import type { ResultDetailRecord, WorklistItem } from "../results/types";
import {
  fetchSampleStatusCounts,
  formatCount,
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

interface TechnicianData {
  worklist: WorklistItem[] | null;
  sampleCounts: SampleStatusCounts | null;
  criticalResults: ResultDetailRecord[] | null;
}

export function TechnicianDashboardScreen(): ReactElement {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [data, setData] = useState<TechnicianData | null>(null);
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
          title="Bench worklist"
          subtitle={`${dateLabel} · samples awaiting receipt or result entry`}
          badge="Technician"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            testId="stat-worklist"
            label="Worklist"
            value={loading ? "—" : formatCount(worklistCount)}
            hint="Collected, received, in-process and rejected accessions."
            icon="assignment"
          />
          <StatCard
            testId="stat-awaiting-receipt"
            label="Awaiting receipt"
            value={
              loading ? "—" : formatCount(data?.sampleCounts?.collected ?? null)
            }
            hint="Collected samples not yet received into the lab."
            icon="inventory"
            tone="warning"
          />
          <StatCard
            testId="stat-awaiting-result-entry"
            label="Awaiting result entry"
            value={loading ? "—" : formatCount(awaitingResultEntry)}
            hint="Status count of received and in-process samples on the bench."
            icon="edit_note"
          />
          <StatCard
            testId="stat-critical-pending"
            label="Critical results pending"
            value={
              loading ? "—" : formatCount(data?.criticalResults?.length ?? null)
            }
            hint="Entered results flagged critical and awaiting verification."
            icon="crisis_alert"
            tone="danger"
          />
        </div>

        <Panel
          title="Worklist"
          subtitle="Oldest accession first — real rows from the worklist API"
          className="mt-6"
          testId="panel-worklist"
          action={<DashboardLink to="/worklist">Open worklist</DashboardLink>}
        >
          {loading ? (
            <EmptyState message="Loading worklist…" />
          ) : data?.worklist === null ? (
            <EmptyState message="Unavailable — the worklist API did not respond." />
          ) : data?.worklist.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-100">
                    <th className="py-2 pr-3 font-semibold">Accession</th>
                    <th className="py-2 pr-3 font-semibold">Patient</th>
                    <th className="py-2 pr-3 font-semibold">Tests</th>
                    <th className="py-2 pr-3 font-semibold">Waiting</th>
                    <th className="py-2 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.worklist.slice(0, 6).map((item) => (
                    <tr key={item.sample_id}>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-700">
                        {item.accession_id}
                      </td>
                      <td className="py-2.5 pr-3 font-medium text-slate-900">
                        {item.patient_name}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-600">
                        {item.tests.length ? item.tests.join(", ") : "—"}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">
                        {item.waiting_time}
                      </td>
                      <td className="py-2.5">
                        <span className="text-xs font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                          {item.sample_status ?? item.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="No samples are waiting on the bench." />
          )}
        </Panel>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Panel
            title="Critical results awaiting verification"
            subtitle="Entered rows flagged critical by the reference-range engine"
            testId="panel-critical-results"
          >
            {loading ? (
              <EmptyState message="Loading critical results…" />
            ) : data?.criticalResults === null ? (
              <EmptyState message="Unavailable — the results API did not respond." />
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
              <EmptyState message="No critical results are awaiting verification." />
            )}
          </Panel>

          <Panel
            title="Bench scope"
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
                  Receive samples, enter results, and flag/reject bench
                  specimens.
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
                  Billing, payments, settlements and the partner ledger are
                  hidden and refused by the API.
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
                  Clinical approval remains with the Pathologist or Owner.
                </span>
              </li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
