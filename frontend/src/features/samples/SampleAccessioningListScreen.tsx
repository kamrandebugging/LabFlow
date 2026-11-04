import { useCallback, useEffect, useId, useState } from "react";
import {
  ChevronRight,
  Filter,
  Plus,
  Printer,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { sampleService } from "./sampleService";
import type { SampleStatus, SampleSummary } from "./types";

export interface SampleAccessioningListScreenProps {
  onSelectSample?: (id: string) => void;
  onCollectNew?: () => void;
  onPrintLabels?: (accessionIds: string[]) => void;
  service?: typeof sampleService;
}

function getStatusBadge(status: SampleStatus): JSX.Element {
  switch (status) {
    case "collected":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
          Collected
        </span>
      );
    case "received":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-600" />
          Received
        </span>
      );
    case "in_process":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-orange-700 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-600" />
          In process
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
          Ready / Reported
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-700 bg-red-50 px-2 py-0.5 rounded-full border border-red-200">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
          Rejected
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
          Cancelled
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
          {status}
        </span>
      );
  }
}

export function SampleAccessioningListScreen({
  onSelectSample,
  onCollectNew,
  onPrintLabels,
  service = sampleService,
}: SampleAccessioningListScreenProps): JSX.Element {
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedBranch, setSelectedBranch] = useState<string>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const searchInputId = useId();
  const statusSelectId = useId();
  const branchSelectId = useId();

  const loadSamples = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await service.listSamples({
        q: searchQuery.trim() || undefined,
        status: selectedStatus !== "all" ? selectedStatus : undefined,
        branch_id: selectedBranch !== "all" ? selectedBranch : undefined,
      });
      setSamples(res.results);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load samples list.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, selectedStatus, selectedBranch, service]);

  useEffect(() => {
    loadSamples();
  }, [loadSamples]);

  const toggleSelectAll = () => {
    if (selectedIds.size === samples.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(samples.map((s) => s.id)));
    }
  };

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleBatchPrint = () => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    if (onPrintLabels) {
      onPrintLabels(ids);
    } else if (onSelectSample && ids.length === 1 && ids[0]) {
      onSelectSample(ids[0]);
    }
  };

  return (
    <div className="w-full max-w-[1160px] mx-auto space-y-6 px-4 py-8">
      {/* Title & Audit Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Samples
          </h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Central specimen accessioning and chain of custody tracking
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-slate-500">
            times are PKT (UTC+5)
          </span>
          {onCollectNew && (
            <button
              type="button"
              onClick={onCollectNew}
              className="inline-flex items-center gap-1.5 bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
              Collect sample
            </button>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center justify-between"
        >
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            aria-label="Dismiss error"
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Filter Bar (16-samples.html) */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 flex-1">
          {/* Search by Accession ID */}
          <div className="relative flex-1 min-w-[240px] max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              id={searchInputId}
              type="text"
              placeholder="Search by Accession ID (e.g. CDL2026...)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-teal-600 focus:bg-white font-mono transition-colors"
            />
          </div>

          {/* Status Select */}
          <div className="relative w-40">
            <select
              id={statusSelectId}
              aria-label="Filter by sample status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full appearance-none pl-3 pr-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium focus:outline-none focus:border-teal-600 focus:bg-white transition-colors cursor-pointer"
            >
              <option value="all">All statuses</option>
              <option value="collected">Collected</option>
              <option value="received">Received</option>
              <option value="in_process">In process</option>
              <option value="ready">Ready / Reported</option>
              <option value="rejected">Rejected</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <Filter className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>

          {/* Branch Select */}
          <div className="relative w-44">
            <select
              id={branchSelectId}
              aria-label="Filter by branch"
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              className="w-full appearance-none pl-3 pr-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium focus:outline-none focus:border-teal-600 focus:bg-white transition-colors cursor-pointer"
            >
              <option value="all">All branches</option>
              <option value="00000000-0000-0000-0000-000000000001">Central Diagnostic Lab</option>
              <option value="00000000-0000-0000-0000-000000000002">Gulberg Branch</option>
            </select>
          </div>

          <button
            type="button"
            onClick={loadSamples}
            aria-label="Refresh sample list"
            className="p-1.5 text-slate-400 hover:text-slate-600 border border-slate-200 rounded-lg bg-slate-50 hover:bg-slate-100"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Batch Action Header Controls */}
        <div className="flex items-center gap-3 justify-end shrink-0">
          <span className="text-xs text-slate-500 font-medium">
            {selectedIds.size} samples selected
          </span>
          <button
            type="button"
            onClick={handleBatchPrint}
            disabled={selectedIds.size === 0}
            className="inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-3.5 py-2 rounded-lg transition-colors shadow-sm"
          >
            <Printer className="w-4 h-4" />
            <span>Print labels ({selectedIds.size})</span>
          </button>
        </div>
      </div>

      {/* Samples Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                <th className="py-3 px-4 w-10 text-center">
                  <input
                    type="checkbox"
                    aria-label="Select all samples"
                    checked={
                      samples.length > 0 && selectedIds.size === samples.length
                    }
                    onChange={toggleSelectAll}
                    className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-600 cursor-pointer"
                  />
                </th>
                <th className="py-3 px-4">Accession ID</th>
                <th className="py-3 px-4">Patient</th>
                <th className="py-3 px-4">Tests</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Branch</th>
                <th className="py-3 px-4">Age</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
              {isLoading && samples.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    Loading accession records...
                  </td>
                </tr>
              ) : samples.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    No samples match the selected filters.
                  </td>
                </tr>
              ) : (
                samples.map((sample) => {
                  const isChecked = selectedIds.has(sample.id);
                  return (
                    <tr
                      key={sample.id}
                      className={`hover:bg-slate-50 transition-colors ${
                        isChecked ? "bg-teal-50/40" : ""
                      }`}
                    >
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          aria-label={`Select sample ${sample.accession_id}`}
                          checked={isChecked}
                          onChange={() => toggleSelectOne(sample.id)}
                          className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-600 cursor-pointer"
                        />
                      </td>
                      <td className="py-3 px-4">
                        <button
                          type="button"
                          onClick={() => onSelectSample?.(sample.id)}
                          className="font-mono font-medium text-teal-700 hover:text-teal-900 tracking-tight underline text-left"
                        >
                          {sample.accession_id}
                        </button>
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-900">
                        {sample.patient_name}
                        <span className="block text-[11px] text-slate-500 font-mono">
                          {sample.patient_mrn}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {sample.tests.map((testName, idx) => (
                            <span
                              key={idx}
                              className="inline-block bg-slate-100 border border-slate-200 text-slate-700 px-2 py-0.5 rounded text-[11px] font-medium"
                            >
                              {testName}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4">{getStatusBadge(sample.status)}</td>
                      <td className="py-3 px-4 text-slate-600">{sample.branch_name}</td>
                      <td
                        className={`py-3 px-4 font-medium ${
                          sample.age_display && sample.age_display.startsWith("6")
                            ? "font-semibold text-orange-600"
                            : "text-slate-600"
                        }`}
                      >
                        {sample.age_display || "Recent"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => onSelectSample?.(sample.id)}
                          className="inline-flex items-center text-xs font-semibold text-teal-600 hover:text-teal-800"
                        >
                          View
                          <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="border-t border-slate-200 px-4 py-3 bg-white flex items-center justify-between text-xs">
          <span className="text-slate-500 font-medium">
            Showing {samples.length} accession records
          </span>
          <span className="text-slate-400 text-[11px]">ISO 15189 Compliant</span>
        </div>
      </div>
    </div>
  );
}
