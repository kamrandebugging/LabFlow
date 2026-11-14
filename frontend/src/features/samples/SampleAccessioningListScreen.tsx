import { useCallback, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Filter,
  Plus,
  Printer,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { sampleService } from "./sampleService";
import { useAuthStore } from "../auth/authStore";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import type { SampleStatus, SampleSummary } from "./types";

export interface SampleAccessioningListScreenProps {
  onSelectSample?: (id: string) => void;
  onCollectNew?: () => void;
  onPrintLabels?: (accessionIds: string[]) => void;
  service?: typeof sampleService;
}

type Translator = (key: string) => string;

function getStatusBadge(status: SampleStatus, t: Translator): JSX.Element {
  switch (status) {
    case "collected":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
          {t("common:status.sample.collected")}
        </span>
      );
    case "received":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-600" />
          {t("common:status.sample.received")}
        </span>
      );
    case "in_process":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-orange-700 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-600" />
          {t("common:status.sample.in_process")}
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
          {t("samples:status.ready_reported")}
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-700 bg-red-50 px-2 py-0.5 rounded-full border border-red-200">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
          {t("common:status.sample.rejected")}
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
          {t("common:status.sample.cancelled")}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
          {t("common:labels.unknown")}
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
  const { t } = useTranslation(["samples", "common"]);
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedBranch, setSelectedBranch] = useState<string>("all");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const accessToken = useAuthStore((s) => s.accessToken);

  const searchInputId = useId();
  const statusSelectId = useId();
  const branchSelectId = useId();

  const loadSamples = useCallback(async () => {
    // When using default sampleService, never fire without authentication
    if (service === sampleService && !useAuthStore.getState().accessToken) {
      setIsLoading(false);
      return;
    }
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
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, selectedStatus, selectedBranch, service, t]);

  useEffect(() => {
    if (service === sampleService && !accessToken) {
      return;
    }
    loadSamples();
  }, [loadSamples, service, accessToken]);

  useEffect(() => {
    let active = true;
    void settingsService
      .getBranches()
      .then((list) => {
        if (active && Array.isArray(list)) {
          setBranches(list);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

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
            {t("common:nav.samples")}
          </h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            {t("samples:list.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-slate-500">
            {t("samples:time.pkt_utc")}
          </span>
          {onCollectNew && (
            <button
              type="button"
              onClick={onCollectNew}
              className="inline-flex items-center gap-1.5 bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t("samples:actions.collect_sample")}
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
            aria-label={t("samples:list.dismiss_error")}
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
            <Search className="w-4 h-4 absolute start-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              id={searchInputId}
              type="text"
              placeholder={t("samples:list.search_placeholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full ps-9 pe-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-teal-600 focus:bg-white font-mono transition-colors"
            />
          </div>

          {/* Status Select */}
          <div className="relative w-40">
            <select
              id={statusSelectId}
              aria-label={t("samples:list.filter_status_aria")}
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full appearance-none ps-3 pe-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium focus:outline-none focus:border-teal-600 focus:bg-white transition-colors cursor-pointer"
            >
              <option value="all">{t("samples:list.all_statuses")}</option>
              <option value="collected">
                {t("common:status.sample.collected")}
              </option>
              <option value="received">
                {t("common:status.sample.received")}
              </option>
              <option value="in_process">
                {t("common:status.sample.in_process")}
              </option>
              <option value="ready">
                {t("samples:status.ready_reported")}
              </option>
              <option value="rejected">
                {t("common:status.sample.rejected")}
              </option>
              <option value="cancelled">
                {t("common:status.sample.cancelled")}
              </option>
            </select>
            <Filter className="w-3.5 h-3.5 absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>

          {/* Branch Select */}
          <div className="relative w-44">
            <select
              id={branchSelectId}
              aria-label={t("samples:list.filter_branch_aria")}
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              className="w-full appearance-none ps-3 pe-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium focus:outline-none focus:border-teal-600 focus:bg-white transition-colors cursor-pointer"
            >
              <option value="all">{t("common:topbar.all_branches")}</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={loadSamples}
            aria-label={t("samples:list.refresh_aria")}
            className="p-1.5 text-slate-400 hover:text-slate-600 border border-slate-200 rounded-lg bg-slate-50 hover:bg-slate-100"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`}
            />
          </button>
        </div>

        {/* Batch Action Header Controls */}
        <div className="flex items-center gap-3 justify-end shrink-0">
          <span className="text-xs text-slate-500 font-medium">
            {t("samples:list.selected_count", { n: selectedIds.size })}
          </span>
          <button
            type="button"
            onClick={handleBatchPrint}
            disabled={selectedIds.size === 0}
            className="inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-3.5 py-2 rounded-lg transition-colors shadow-sm"
          >
            <Printer className="w-4 h-4" />
            <span>
              {t("samples:actions.print_labels", { n: selectedIds.size })}
            </span>
          </button>
        </div>
      </div>

      {/* Samples Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-start border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                <th className="py-3 px-4 w-10 text-center">
                  <input
                    type="checkbox"
                    aria-label={t("samples:list.select_all_aria")}
                    checked={
                      samples.length > 0 && selectedIds.size === samples.length
                    }
                    onChange={toggleSelectAll}
                    className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-600 cursor-pointer"
                  />
                </th>
                <th className="py-3 px-4">
                  {t("samples:list.table.accession")}
                </th>
                <th className="py-3 px-4">{t("samples:list.table.patient")}</th>
                <th className="py-3 px-4">{t("samples:list.table.tests")}</th>
                <th className="py-3 px-4">{t("common:labels.status")}</th>
                <th className="py-3 px-4">{t("samples:list.table.branch")}</th>
                <th className="py-3 px-4">{t("common:labels.age")}</th>
                <th className="py-3 px-4 text-end">
                  {t("common:labels.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
              {isLoading && samples.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {t("samples:list.loading")}
                  </td>
                </tr>
              ) : samples.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {t("samples:list.empty")}
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
                          aria-label={t("samples:list.select_one_aria", {
                            accession: sample.accession_id,
                          })}
                          checked={isChecked}
                          onChange={() => toggleSelectOne(sample.id)}
                          className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-600 cursor-pointer"
                        />
                      </td>
                      <td className="py-3 px-4">
                        <button
                          type="button"
                          onClick={() => onSelectSample?.(sample.id)}
                          className="font-mono font-medium text-teal-700 hover:text-teal-900 tracking-tight underline text-start"
                          dir="ltr"
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
                      <td className="py-3 px-4">
                        {getStatusBadge(sample.status, t)}
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {sample.branch_name}
                      </td>
                      <td
                        className={`py-3 px-4 font-medium ${
                          sample.age_display &&
                          sample.age_display.startsWith("6")
                            ? "font-semibold text-orange-600"
                            : "text-slate-600"
                        }`}
                      >
                        {sample.age_display || t("samples:list.recent")}
                      </td>
                      <td className="py-3 px-4 text-end">
                        <button
                          type="button"
                          onClick={() => onSelectSample?.(sample.id)}
                          className="inline-flex items-center text-xs font-semibold text-teal-600 hover:text-teal-800"
                        >
                          {t("common:actions.view")}
                          <ChevronRight className="w-3.5 h-3.5 ms-0.5 rtl:rotate-180" />
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
            {t("samples:list.showing", { n: samples.length })}
          </span>
          <span className="text-slate-400 text-[11px]">
            {t("samples:list.iso_compliant")}
          </span>
        </div>
      </div>
    </div>
  );
}
