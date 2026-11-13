import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Plus,
  Receipt,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { billingService } from "./billingService";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { InvoiceStatus, InvoiceSummary } from "./types";

interface InvoicesListScreenProps {
  onNewInvoice?: () => void;
  onSelectInvoice?: (id: string) => void;
  service?: typeof billingService;
}

export function InvoicesListScreen({
  onNewInvoice,
  onSelectInvoice,
  service = billingService,
}: InvoicesListScreenProps): JSX.Element {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const lang: "en" | "ur" = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyTotal, setDailyTotal] = useState<string | null>(null);

  const fetchInvoices = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listInvoices({
        status: selectedStatus === "all" ? undefined : selectedStatus,
      });
      setInvoices(data.results);
      // Never derive a "daily" total from the loaded page: it mixes dates and
      // statuses. Absence is shown as unavailable.
      setDailyTotal(data.daily_total ?? null);
    } catch (err: unknown) {
      setError(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [selectedStatus, service, t]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const filteredInvoices = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return invoices;
    return invoices.filter(
      (inv) =>
        inv.id.toLowerCase().includes(q) ||
        (inv.patient_name && inv.patient_name.toLowerCase().includes(q)) ||
        (inv.patient_mrn && inv.patient_mrn.toLowerCase().includes(q)) ||
        (inv.items_summary && inv.items_summary.toLowerCase().includes(q)),
    );
  }, [invoices, searchQuery]);

  const getStatusBadge = (status: InvoiceStatus) => {
    switch (status) {
      case "paid":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
            {statusLabel("invoice", "paid", t)}
          </span>
        );
      case "unpaid":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
            {statusLabel("invoice", "unpaid", t)}
          </span>
        );
      case "partial":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-600" />
            {statusLabel("invoice", "partial", t)}
          </span>
        );
      case "refunded":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
            {statusLabel("invoice", "refunded", t)}
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 line-through border border-slate-200">
            {statusLabel("invoice", "cancelled", t)}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
            {t("common:labels.unknown")}
          </span>
        );
    }
  };

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return `${d.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })} · ${d.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      })} PKT`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-5">
      {/* 1. Header & Daily Summary */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 bg-teal-50 text-teal-700 rounded-lg">
              <Receipt className="w-6 h-6" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {t("billing:list.title")}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                {t("billing:list.subtitle")} · {t("common:time.pkt")}
              </p>
            </div>
          </div>
        </div>

        {/* Daily Total Summary Badge */}
        <div className="flex items-center gap-3 self-start md:self-auto">
          <div className="bg-white border border-slate-200 rounded-xl px-4 py-2 flex items-center gap-2.5 shadow-xs">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
              {t("billing:list.daily_total")}
            </span>
            <span className="font-mono text-sm font-bold text-slate-900">
              {formatMoney(dailyTotal, lang)}
            </span>
          </div>

          {onNewInvoice ? (
            <button
              type="button"
              onClick={onNewInvoice}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-lg hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-sm transition-all"
            >
              <Plus className="w-4 h-4" />
              {t("billing:list.new_invoice")}
            </button>
          ) : null}
        </div>
      </div>

      {/* 2. Filter Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[300px]">
          {/* Status Dropdown */}
          <div className="relative min-w-[150px]">
            <label htmlFor="invoiceStatusFilter" className="sr-only">
              {t("billing:list.status_filter_aria")}
            </label>
            <select
              id="invoiceStatusFilter"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-600 cursor-pointer"
            >
              <option value="all">{t("billing:list.all_statuses")}</option>
              <option value="paid">{statusLabel("invoice", "paid", t)}</option>
              <option value="unpaid">
                {statusLabel("invoice", "unpaid", t)}
              </option>
              <option value="partial">
                {statusLabel("invoice", "partial", t)}
              </option>
              <option value="refunded">
                {statusLabel("invoice", "refunded", t)}
              </option>
              <option value="cancelled">
                {statusLabel("invoice", "cancelled", t)}
              </option>
            </select>
          </div>

          {/* Search Input */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute start-3 top-2.5 text-slate-400 w-4 h-4" />
            <label htmlFor="invoiceSearchInput" className="sr-only">
              {t("billing:list.search_aria")}
            </label>
            <input
              id="invoiceSearchInput"
              type="text"
              placeholder={t("billing:list.search_placeholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full ps-9 pe-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-600"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={fetchInvoices}
          disabled={isLoading}
          className="p-2 border border-slate-200 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition"
          title={t("billing:list.refresh_title")}
        >
          <RefreshCw
            className={`w-4 h-4 ${isLoading ? "animate-spin text-teal-600" : ""}`}
          />
        </button>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label={t("billing:shared.dismiss_error_aria")}
            className="text-rose-500 hover:text-rose-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 3. Invoices Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-start border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4" scope="col">
                  {t("billing:list.col_invoice")}
                </th>
                <th className="py-3 px-4" scope="col">
                  {t("billing:list.col_patient")}
                </th>
                <th className="py-3 px-4" scope="col">
                  {t("common:labels.date")}
                </th>
                <th className="py-3 px-4" scope="col">
                  {t("billing:list.col_tests")}
                </th>
                <th className="py-3 px-4" scope="col">
                  {t("billing:list.col_total")}
                </th>
                <th className="py-3 px-4" scope="col">
                  {t("common:labels.status")}
                </th>
                <th className="py-3 px-4 text-end" scope="col">
                  {t("billing:list.col_action")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-teal-600 mb-2" />
                    {t("billing:list.loading")}
                  </td>
                </tr>
              ) : filteredInvoices.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    {t("billing:list.empty")}
                  </td>
                </tr>
              ) : (
                filteredInvoices.map((inv) => (
                  <tr
                    key={inv.id}
                    className="hover:bg-slate-50/75 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-mono font-bold text-teal-700">
                      {inv.id.startsWith("INV-")
                        ? inv.id
                        : `INV-${inv.id.slice(0, 8).toUpperCase()}`}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="font-medium text-slate-900">
                        {inv.patient_name || t("billing:list.patient_fallback")}
                      </div>
                      <div className="font-mono text-xs text-slate-400">
                        {inv.patient_mrn ||
                          `${t("billing:list.mrn_label")} ${inv.patient_id.slice(0, 8)}`}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 text-xs">
                      <bdi dir="ltr">{formatDate(inv.created_at)}</bdi>
                    </td>
                    <td
                      className="py-3.5 px-4 text-slate-700 max-w-xs truncate"
                      title={
                        inv.items_summary || t("billing:list.tests_fallback")
                      }
                    >
                      {inv.items_summary || t("billing:list.tests_fallback")}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="bg-slate-50 border border-slate-200 rounded px-2.5 py-1 font-mono text-xs font-semibold text-slate-900 inline-block">
                        {formatMoney(inv.total, lang)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      {getStatusBadge(inv.status)}
                    </td>
                    <td className="py-3.5 px-4 text-end">
                      <button
                        type="button"
                        onClick={() => onSelectInvoice?.(inv.id)}
                        className="text-teal-600 font-semibold hover:text-teal-800 text-xs transition-colors"
                      >
                        {t("billing:list.view")}{" "}
                        <span
                          aria-hidden="true"
                          className="inline-block rtl:-scale-x-100"
                        >
                          →
                        </span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="border-t border-slate-200 px-4 py-3 flex items-center justify-between bg-white text-xs text-slate-500">
          <div>
            {t("billing:list.showing", { total: filteredInvoices.length })}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="p-1.5 border border-slate-200 rounded-lg text-slate-300 cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4 rtl:rotate-180" />
            </button>
            <button
              type="button"
              disabled
              className="p-1.5 border border-slate-200 rounded-lg text-slate-300 cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4 rtl:rotate-180" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
export default InvoicesListScreen;
