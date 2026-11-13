/**
 * Screen 26: Reports List Screen (/reports).
 * Spec: Doc 03 §5.6, §6.1, 26-reports.html.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  FileText,
  Search,
  RefreshCw,
  Send,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Filter,
  X,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { reportsService } from "./reportsService";
import { formatDate, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type {
  DeliveryChannel,
  ReportPatientContact,
  ReportStatus,
  ReportSummaryItem,
} from "./types";

export function ReportsListScreen(): JSX.Element {
  const { t } = useTranslation(["reports", "common"]);
  const searchInputId = useId();
  const statusSelectId = useId();

  const user = useAuthStore((state) => state.user);
  const userRole = user?.role?.toLowerCase() || "";

  // Role permissions based on backend specification Doc 03 §6.6, §6.7
  const canRegenerate = ["owner", "manager", "pathologist"].includes(userRole);
  const canDeliver = ["owner", "manager", "reception"].includes(userRole);

  const [reports, setReports] = useState<ReportSummaryItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Delivery Modal State
  const [deliveringReport, setDeliveringReport] =
    useState<ReportSummaryItem | null>(null);
  const [deliveryChannel, setDeliveryChannel] =
    useState<DeliveryChannel>("whatsapp");
  const [deliveryContacts, setDeliveryContacts] = useState<
    ReportPatientContact[] | null
  >(null);
  const [isDelivering, setIsDelivering] = useState(false);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  // Regenerating State
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  const fetchReports = async (reset: boolean = true, cursor?: string) => {
    try {
      if (reset) {
        setLoading(true);
        setErrorMessage(null);
      } else {
        setLoadingMore(true);
      }

      const res = await reportsService.getReports({
        q: searchQuery.trim() || undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
        cursor: cursor || undefined,
        limit: 50,
      });

      if (reset) {
        setReports(res.results);
      } else {
        setReports((prev) => [...prev, ...res.results]);
      }
      setNextCursor(res.next_cursor);
    } catch (err) {
      setErrorMessage(messageForError(err, (key) => t(`common:${key}`)));
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchReports(true);
    }, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, statusFilter]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && deliveringReport) {
        setDeliveringReport(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deliveringReport]);

  const handleRegenerate = async (reportId: string) => {
    if (!canRegenerate) return;
    try {
      setRegeneratingId(reportId);
      setErrorMessage(null);
      await reportsService.regenerateReport(reportId);
      setSuccessMessage(t("reports:list.regenerated"));
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchReports(true);
    } catch (err) {
      setErrorMessage(messageForError(err, (key) => t(`common:${key}`)));
    } finally {
      setRegeneratingId(null);
    }
  };

  const openDeliveryModal = (report: ReportSummaryItem) => {
    setDeliveringReport(report);
    setDeliveryChannel("whatsapp");
    setDeliveryContacts(null);
    setDeliveryError(null);
    // The list payload has no contacts; delivery is addressed to a stored
    // PatientContact row, so fetch the detail to resolve a real contact id.
    void reportsService
      .getReport(report.id)
      .then((detail) => setDeliveryContacts(detail.patient.contacts ?? []))
      .catch(() => setDeliveryContacts([]));
  };

  const handleDeliverSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deliveringReport) return;

    const contact = deliveryContacts?.find((c) => c.kind === deliveryChannel);
    if (!contact) {
      setDeliveryError(
        t("reports:list.no_contact_channel", {
          channel:
            deliveryChannel === "whatsapp"
              ? t("reports:list.whatsapp")
              : t("reports:list.email"),
        }),
      );
      return;
    }

    try {
      setIsDelivering(true);
      setDeliveryError(null);

      await reportsService.deliverReport(deliveringReport.id, {
        channel: deliveryChannel,
        contact_id: contact.id,
      });

      setSuccessMessage(
        t("reports:list.dispatched", {
          channel: deliveryChannel.toUpperCase(),
        }),
      );
      setDeliveringReport(null);
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchReports(true);
    } catch (err) {
      setDeliveryError(messageForError(err, (key) => t(`common:${key}`)));
    } finally {
      setIsDelivering(false);
    }
  };

  const activeContact =
    deliveryContacts?.find((c) => c.kind === deliveryChannel) ?? null;
  const emailContactAvailable =
    deliveryContacts?.some((c) => c.kind === "email") ?? false;

  const getStatusBadge = (status: ReportStatus) => {
    const label = statusLabel("report", status, (key) => t(`common:${key}`));
    switch (status) {
      case "final":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
            {label}
          </span>
        );
      case "amended":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-600"></span>
            {label}
          </span>
        );
      case "void":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-200">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600"></span>
            {label}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            {label}
          </span>
        );
    }
  };

  const getDeliveryBadge = (report: ReportSummaryItem) => {
    if (!report.latest_delivery) {
      return (
        <span className="inline-flex items-center gap-1 text-xs text-slate-400">
          {t("reports:list.not_sent")}
        </span>
      );
    }
    const { status, channel } = report.latest_delivery;
    const isSuccess = status === "delivered" || status === "opened";
    const isPending = status === "pending" || status === "sent";

    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
          isSuccess
            ? "bg-sky-50 text-sky-800 border border-sky-200"
            : isPending
              ? "bg-amber-50 text-amber-800 border border-amber-200"
              : "bg-rose-50 text-rose-800 border border-rose-200"
        }`}
      >
        <span className="capitalize">{channel}:</span>
        <span className="capitalize font-semibold">
          {t(`reports:list.delivery.${status}`, { defaultValue: status })}
        </span>
      </span>
    );
  };

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 gap-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-2 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("reports:list.title")}
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
              {t("reports:list.active")}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {t("reports:list.subtitle")}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/exceptions"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            <AlertCircle className="w-4 h-4 text-amber-600" />
            {t("reports:list.exceptions_queue")}
          </Link>
          <button
            onClick={() => fetchReports(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors"
            title={t("reports:list.refresh_title")}
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
            />
            {t("reports:list.refresh")}
          </button>
        </div>
      </div>

      {/* Messages */}
      {errorMessage && (
        <div className="flex items-center gap-2 p-4 text-sm text-rose-800 bg-rose-50 border border-rose-200 rounded-xl">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span className="flex-1">{errorMessage}</span>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-rose-500 hover:text-rose-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center gap-2 p-4 text-sm text-teal-800 bg-teal-50 border border-teal-200 rounded-xl">
          <CheckCircle2 className="w-5 h-5 shrink-0" />
          <span className="flex-1">{successMessage}</span>
          <button
            onClick={() => setSuccessMessage(null)}
            className="text-teal-500 hover:text-teal-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-wrap items-center gap-3 flex-1">
          {/* Search Box */}
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute start-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              id={searchInputId}
              type="text"
              aria-label={t("reports:list.search_aria")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("reports:list.search_placeholder")}
              className="w-full ps-9 pe-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-teal-600 focus:border-transparent transition-all"
            />
          </div>

          {/* Status Filter */}
          <div className="relative min-w-[150px]">
            <select
              id={statusSelectId}
              aria-label={t("reports:list.filter_aria")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full appearance-none ps-3 pe-8 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:bg-white focus:ring-2 focus:ring-teal-600 focus:border-transparent cursor-pointer"
            >
              <option value="all">{t("reports:list.all_statuses")}</option>
              <option value="draft">{t("common:status.report.draft")}</option>
              <option value="final">{t("common:status.report.final")}</option>
              <option value="amended">
                {t("common:status.report.amended")}
              </option>
              <option value="void">{t("common:status.report.void")}</option>
            </select>
            <Filter className="w-3.5 h-3.5 text-slate-400 absolute end-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 self-end md:self-auto">
          <span>{t("reports:list.channels")}</span>
        </div>
      </div>

      {/* Reports Table / Card Container */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
            <span className="text-sm font-medium">
              {t("reports:list.loading")}
            </span>
          </div>
        ) : reports.length === 0 ? (
          /* Honest Empty State */
          <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-slate-900">
              {t("reports:list.empty_title")}
            </h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm">
              {searchQuery || statusFilter !== "all"
                ? t("reports:list.empty_filtered")
                : t("reports:list.empty_none")}
            </p>
            {(searchQuery || statusFilter !== "all") && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setStatusFilter("all");
                }}
                className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors"
              >
                {t("reports:list.clear_filters")}
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-start border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_report")}
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_patient")}
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_tests")}
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_status")}
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_delivery")}
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    {t("reports:list.th_created")}
                  </th>
                  <th className="py-3 px-4 font-semibold text-end" scope="col">
                    {t("reports:list.th_actions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-sm">
                {reports.map((report) => (
                  <tr
                    key={report.id}
                    className="hover:bg-slate-50/80 transition-colors group"
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex flex-col">
                        <span className="font-mono text-xs font-semibold text-slate-900">
                          {report.sample.accession_id}
                        </span>
                        <span className="text-[11px] text-slate-400">
                          v{report.current_version}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-col">
                        <span className="font-medium text-slate-900">
                          {report.sample.patient.name}
                        </span>
                        <span className="font-mono text-xs text-slate-500">
                          {report.sample.patient.mrn}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-600">
                      <span className="truncate max-w-[200px] block">
                        {report.sample.tests.map((t) => t.code).join(", ") ||
                          t("reports:list.clinical_tests")}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      {getStatusBadge(report.status)}
                    </td>
                    <td className="py-3.5 px-4">{getDeliveryBadge(report)}</td>
                    <td className="py-3.5 px-4 text-xs font-mono text-slate-500">
                      {formatDate(report.created_at)}
                    </td>
                    <td className="py-3.5 px-4 text-end">
                      <div className="flex items-center justify-end gap-2">
                        {canRegenerate && (
                          <button
                            onClick={() => handleRegenerate(report.id)}
                            disabled={regeneratingId === report.id}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-50"
                            title={t("reports:list.regenerate_title")}
                          >
                            <RefreshCw
                              className={`w-3.5 h-3.5 ${
                                regeneratingId === report.id
                                  ? "animate-spin"
                                  : ""
                              }`}
                            />
                            <span className="hidden sm:inline">
                              {t("reports:list.regenerate")}
                            </span>
                          </button>
                        )}
                        {canDeliver && (
                          <button
                            onClick={() => openDeliveryModal(report)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded text-teal-700 hover:text-teal-900 hover:bg-teal-50 transition-colors"
                            title={t("reports:list.deliver_title")}
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">
                              {t("reports:list.deliver")}
                            </span>
                          </button>
                        )}
                        <Link
                          to={`/reports/${report.id}`}
                          className="inline-flex items-center gap-1 font-semibold text-xs text-teal-700 hover:text-teal-900 group-hover:translate-x-0.5 transition-all ms-1"
                        >
                          <span>{t("reports:list.open")}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Cursor Pagination Button */}
        {nextCursor && !loading && (
          <div className="p-4 border-t border-slate-200 flex justify-center bg-slate-50">
            <button
              onClick={() => fetchReports(false, nextCursor)}
              disabled={loadingMore}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-sm disabled:opacity-50"
            >
              {loadingMore ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  {t("reports:list.loading_more")}
                </>
              ) : (
                t("reports:list.load_more")
              )}
            </button>
          </div>
        )}
      </div>

      {/* Deliver Modal */}
      {deliveringReport && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="deliver-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3
                  id="deliver-modal-title"
                  className="text-lg font-bold text-slate-900"
                >
                  {t("reports:list.deliver_modal_title")}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("reports:list.deliver_for", {
                    name: deliveringReport.sample.patient.name,
                    accession: deliveringReport.sample.accession_id,
                  })}
                </p>
              </div>
              <button
                onClick={() => setDeliveringReport(null)}
                aria-label={t("reports:list.close_dialog")}
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form
              onSubmit={handleDeliverSubmit}
              className="p-6 flex flex-col gap-4"
            >
              {deliveryError && (
                <div className="p-3 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg">
                  {deliveryError}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold uppercase text-slate-600 mb-1.5">
                  {t("reports:list.delivery_channel")}
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setDeliveryChannel("whatsapp");
                      setDeliveryError(null);
                    }}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-semibold transition-all ${
                      deliveryChannel === "whatsapp"
                        ? "border-teal-600 bg-teal-50 text-teal-800"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <span>{t("reports:list.whatsapp")}</span>
                  </button>
                  <button
                    type="button"
                    disabled={!emailContactAvailable}
                    title={
                      emailContactAvailable
                        ? undefined
                        : t("reports:list.no_email_title")
                    }
                    onClick={() => {
                      setDeliveryChannel("email");
                      setDeliveryError(null);
                    }}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                      deliveryChannel === "email"
                        ? "border-teal-600 bg-teal-50 text-teal-800"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <span>{t("reports:list.email")}</span>
                  </button>
                </div>
              </div>

              <div>
                <label
                  htmlFor="destination-contact-input"
                  className="block text-xs font-semibold uppercase text-slate-600 mb-1.5"
                >
                  {t("reports:list.destination_contact")}
                </label>
                {activeContact ? (
                  <>
                    <input
                      id="destination-contact-input"
                      type="text"
                      readOnly
                      value={activeContact.value}
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono"
                    />
                    <p className="mt-1 text-[11px] text-slate-400">
                      {t("reports:list.stored_contact", {
                        channel: deliveryChannel,
                      })}
                    </p>
                  </>
                ) : (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900">
                    {deliveryContacts === null
                      ? t("reports:list.loading_contacts")
                      : t("reports:list.no_stored_contact", {
                          channel: deliveryChannel,
                        })}
                  </div>
                )}
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setDeliveringReport(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 transition-colors"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isDelivering || !activeContact}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isDelivering ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      {t("reports:list.dispatching")}
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      {t("reports:list.send_report")}
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
