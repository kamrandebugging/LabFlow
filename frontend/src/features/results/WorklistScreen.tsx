/**
 * Screen 21: Technician Worklist (/worklist).
 * Spec: Doc 03 §5.5 RS-1/RS-2/RS-3, 21-worklist.html.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState, useId } from "react";
import { Link } from "react-router-dom";
import {
  Clock,
  ArrowRight,
  RefreshCw,
  AlertCircle,
  Layers,
  ChevronDown,
} from "lucide-react";
import { resultsService } from "./resultsService";
import type { WorklistItem } from "./types";

export function WorklistScreen(): JSX.Element {
  const branchFilterId = useId();
  const statusFilterId = useId();
  const testFilterId = useId();

  const [items, setItems] = useState<WorklistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filters
  const [branchFilter, setBranchFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [testFilter, setTestFilter] = useState("all");

  const loadData = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const data = await resultsService.getWorklist({
        statusFilter,
      });
      setItems(data);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Failed to load clinical worklist.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  // Client-side filtering
  const filteredItems = items.filter((item) => {
    if (branchFilter !== "all" && item.branch_id !== branchFilter) return false;
    if (statusFilter !== "all" && item.status !== statusFilter) return false;
    if (testFilter !== "all") {
      const match = item.tests.some((t) =>
        t.toLowerCase().includes(testFilter.toLowerCase()),
      );
      if (!match) return false;
    }
    return true;
  });

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Worklist
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Oldest first · Times are PKT
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200">
          <span className="w-2 h-2 rounded-full bg-teal-600 animate-pulse" />
          <span>Live Telemetry Synchronized</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-4">
        {/* Branch Filter */}
        <div className="flex items-center gap-2 min-w-[200px] flex-1 sm:flex-initial">
          <label
            htmlFor={branchFilterId}
            className="text-xs font-semibold text-slate-500 uppercase tracking-wider"
          >
            Branch
          </label>
          <div className="relative w-full">
            <select
              id={branchFilterId}
              aria-label="Branch filter"
              value={branchFilter}
              onChange={(e) => setBranchFilter(e.target.value)}
              className="w-full appearance-none bg-slate-50 text-slate-900 text-sm rounded-lg px-3 py-2 pr-8 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-teal-600 cursor-pointer"
            >
              <option value="all">All Branches</option>
              <option value="gulberg">Gulberg Branch</option>
              <option value="dha">DHA Phase 5 Branch</option>
              <option value="johar">Johar Town Branch</option>
            </select>
            <ChevronDown className="w-4 h-4 text-slate-400 pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-2 min-w-[190px] flex-1 sm:flex-initial">
          <label
            htmlFor={statusFilterId}
            className="text-xs font-semibold text-slate-500 uppercase tracking-wider"
          >
            Status
          </label>
          <div className="relative w-full">
            <select
              id={statusFilterId}
              aria-label="Sample status filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full appearance-none bg-slate-50 text-slate-900 text-sm rounded-lg px-3 py-2 pr-8 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-teal-600 cursor-pointer"
            >
              <option value="all">All</option>
              <option value="ready">Ready for entry</option>
              <option value="in_process">In process</option>
              <option value="rejected">Sample rejected</option>
            </select>
            <ChevronDown className="w-4 h-4 text-slate-400 pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        {/* Test Filter */}
        <div className="flex items-center gap-2 min-w-[180px] flex-1 sm:flex-initial">
          <label
            htmlFor={testFilterId}
            className="text-xs font-semibold text-slate-500 uppercase tracking-wider"
          >
            Test
          </label>
          <div className="relative w-full">
            <select
              id={testFilterId}
              aria-label="Test panel filter"
              value={testFilter}
              onChange={(e) => setTestFilter(e.target.value)}
              className="w-full appearance-none bg-slate-50 text-slate-900 text-sm rounded-lg px-3 py-2 pr-8 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-teal-600 cursor-pointer"
            >
              <option value="all">All Tests</option>
              <option value="cbc">CBC</option>
              <option value="lipid">Lipid Profile</option>
              <option value="lft">LFT</option>
              <option value="tsh">TSH</option>
              <option value="hba1c">HbA1c</option>
              <option value="urine">Urine R/E</option>
            </select>
            <ChevronDown className="w-4 h-4 text-slate-400 pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        {/* Ordering info */}
        <div className="ml-auto flex items-center gap-1.5 text-xs text-slate-500 font-mono">
          <Clock className="w-3.5 h-3.5 text-slate-400" />
          <span>Ordered by oldest specimen collection</span>
        </div>
      </div>

      {/* Error state */}
      {errorMessage && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start justify-between gap-3"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
            <span className="font-medium">{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={loadData}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-800 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        {loading ? (
          <div className="py-16 flex flex-col items-center justify-center text-slate-500">
            <RefreshCw className="w-6 h-6 animate-spin text-teal-600 mb-2" />
            <span className="text-xs font-medium">Loading clinical worklist...</span>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-sm">
            <Layers className="w-10 h-10 mx-auto text-slate-300 mb-2" />
            <p className="font-semibold text-slate-700">
              No pending specimens in the worklist
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Specimens collected at reception will appear here chronologically for result entry.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-xs font-semibold uppercase tracking-wider border-b border-slate-200">
                  <th className="py-3.5 px-6" scope="col">
                    Accession ID
                  </th>
                  <th className="py-3.5 px-6" scope="col">
                    Patient
                  </th>
                  <th className="py-3.5 px-6" scope="col">
                    Test
                  </th>
                  <th className="py-3.5 px-6" scope="col">
                    Collected
                  </th>
                  <th className="py-3.5 px-6" scope="col">
                    Waiting
                  </th>
                  <th className="py-3.5 px-6" scope="col">
                    Status
                  </th>
                  <th className="py-3.5 px-6 text-right" scope="col">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-sm text-slate-900">
                {filteredItems.map((item) => {
                  const isLongWaiting =
                    item.waiting_time.includes("h") &&
                    parseInt(item.waiting_time, 10) >= 2;

                  return (
                    <tr
                      key={item.sample_id}
                      className={`hover:bg-slate-50/80 transition-colors ${
                        item.status === "rejected" ? "bg-red-50/20" : ""
                      }`}
                    >
                      <td className="py-4 px-6 font-mono font-semibold text-slate-900">
                        {item.accession_id}
                      </td>
                      <td className="py-4 px-6">
                        <div className="font-medium text-slate-900">
                          {item.patient_name}
                        </div>
                        <div className="text-xs font-mono text-slate-400">
                          {item.patient_mrn}
                        </div>
                      </td>
                      <td className="py-4 px-6 text-slate-600">
                        {item.tests.join(", ") || "General Diagnostics"}
                      </td>
                      <td className="py-4 px-6 font-mono text-xs text-slate-500">
                        {item.collected_at
                          ? new Date(item.collected_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              hour12: false,
                            })
                          : "—"}
                      </td>
                      <td className="py-4 px-6">
                        <span
                          className={`font-mono text-xs font-semibold px-2 py-0.5 rounded ${
                            isLongWaiting
                              ? "text-orange-700 bg-orange-50"
                              : "text-slate-600 bg-slate-100"
                          }`}
                        >
                          {item.waiting_time}
                        </span>
                      </td>
                      <td className="py-4 px-6">
                        {item.status === "ready" && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                            Ready for entry
                          </span>
                        )}
                        {item.status === "in_process" && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-orange-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-orange-600" />
                            In process
                          </span>
                        )}
                        {item.status === "rejected" && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                            Sample rejected
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-6 text-right">
                        {item.status === "rejected" ? (
                          <span className="text-slate-300 font-mono text-xs select-none pr-3">
                            —
                          </span>
                        ) : (
                          <Link
                            to={`/results/entry/${item.sample_id}`}
                            className="text-teal-700 font-semibold hover:text-teal-900 inline-flex items-center gap-1 transition-colors text-xs"
                          >
                            <span>Enter results</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </Link>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer info */}
        <div className="px-6 py-3 bg-slate-50/60 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <span>
            Showing {filteredItems.length} of {items.length} items
          </span>
          <span className="font-mono">Worklist Queue v2.4</span>
        </div>
      </div>
    </div>
  );
}
