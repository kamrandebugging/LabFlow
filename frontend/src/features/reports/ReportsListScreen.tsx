/**
 * Screen 26: Reports List Screen (/reports).
 * Spec: Doc 03 §5.6, §6.1, 26-reports.html.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
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
import type { DeliveryChannel, ReportStatus, ReportSummaryItem } from "./types";

export function ReportsListScreen(): JSX.Element {
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
  const [deliveryContact, setDeliveryContact] = useState("");
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
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load clinical reports.",
      );
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
      setSuccessMessage(
        "PDF generation queued. A new version will be ready momentarily.",
      );
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchReports(true);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to regenerate report PDF.",
      );
    } finally {
      setRegeneratingId(null);
    }
  };

  const openDeliveryModal = (report: ReportSummaryItem) => {
    setDeliveringReport(report);
    setDeliveryChannel("whatsapp");
    setDeliveryContact(report.sample.patient.phone || "");
    setDeliveryError(null);
  };

  const handleDeliverSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deliveringReport) return;

    try {
      setIsDelivering(true);
      setDeliveryError(null);

      // In a real flow, contact_id is resolved or created
      const contactId =
        deliveringReport.sample.patient.id ||
        "00000000-0000-0000-0000-000000000000";

      await reportsService.deliverReport(deliveringReport.id, {
        channel: deliveryChannel,
        contact_id: contactId,
      });

      setSuccessMessage(
        `Report dispatched via ${deliveryChannel.toUpperCase()}.`,
      );
      setDeliveringReport(null);
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchReports(true);
    } catch (err) {
      setDeliveryError(
        err instanceof Error ? err.message : "Failed to deliver report.",
      );
    } finally {
      setIsDelivering(false);
    }
  };

  const getStatusBadge = (status: ReportStatus) => {
    switch (status) {
      case "final":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
            Final
          </span>
        );
      case "amended":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-600"></span>
            Amended
          </span>
        );
      case "void":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-200">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600"></span>
            Void
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            Draft
          </span>
        );
    }
  };

  const getDeliveryBadge = (report: ReportSummaryItem) => {
    if (!report.latest_delivery) {
      return (
        <span className="inline-flex items-center gap-1 text-xs text-slate-400">
          Not sent
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
        <span className="capitalize font-semibold">{status}</span>
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
              Reports
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
              LIS Active
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Clinical reports distribution and delivery records.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/exceptions"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            <AlertCircle className="w-4 h-4 text-amber-600" />
            Exceptions Queue
          </Link>
          <button
            onClick={() => fetchReports(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors"
            title="Refresh reports list"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
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
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              id={searchInputId}
              type="text"
              aria-label="Search patient, MRN, or accession ID"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search patient, MRN, or accession ID…"
              className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:ring-2 focus:ring-teal-600 focus:border-transparent transition-all"
            />
          </div>

          {/* Status Filter */}
          <div className="relative min-w-[150px]">
            <select
              id={statusSelectId}
              aria-label="Filter by report status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full appearance-none pl-3 pr-8 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:bg-white focus:ring-2 focus:ring-teal-600 focus:border-transparent cursor-pointer"
            >
              <option value="all">All statuses</option>
              <option value="draft">Draft</option>
              <option value="final">Final</option>
              <option value="amended">Amended</option>
              <option value="void">Void</option>
            </select>
            <Filter className="w-3.5 h-3.5 text-slate-400 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 self-end md:self-auto">
          <span>Channels: WhatsApp & Email</span>
        </div>
      </div>

      {/* Reports Table / Card Container */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
            <span className="text-sm font-medium">
              Loading clinical reports…
            </span>
          </div>
        ) : reports.length === 0 ? (
          /* Honest Empty State */
          <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-slate-900">
              No reports found
            </h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm">
              {searchQuery || statusFilter !== "all"
                ? "No reports match the selected filters. Try clearing your search query or status filter."
                : "No clinical reports have been generated yet."}
            </p>
            {(searchQuery || statusFilter !== "all") && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setStatusFilter("all");
                }}
                className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors"
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Report / Accession
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Patient
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Tests
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Status
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Delivery
                  </th>
                  <th className="py-3 px-4 font-semibold" scope="col">
                    Created
                  </th>
                  <th
                    className="py-3 px-4 font-semibold text-right"
                    scope="col"
                  >
                    Actions
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
                          "Clinical tests"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      {getStatusBadge(report.status)}
                    </td>
                    <td className="py-3.5 px-4">{getDeliveryBadge(report)}</td>
                    <td className="py-3.5 px-4 text-xs font-mono text-slate-500">
                      {new Date(report.created_at).toLocaleDateString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                      })}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {canRegenerate && (
                          <button
                            onClick={() => handleRegenerate(report.id)}
                            disabled={regeneratingId === report.id}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-50"
                            title="Regenerate PDF"
                          >
                            <RefreshCw
                              className={`w-3.5 h-3.5 ${
                                regeneratingId === report.id
                                  ? "animate-spin"
                                  : ""
                              }`}
                            />
                            <span className="hidden sm:inline">Regenerate</span>
                          </button>
                        )}
                        {canDeliver && (
                          <button
                            onClick={() => openDeliveryModal(report)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded text-teal-700 hover:text-teal-900 hover:bg-teal-50 transition-colors"
                            title="Deliver report"
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Deliver</span>
                          </button>
                        )}
                        <Link
                          to={`/reports/${report.id}`}
                          className="inline-flex items-center gap-1 font-semibold text-xs text-teal-700 hover:text-teal-900 group-hover:translate-x-0.5 transition-all ml-1"
                        >
                          <span>Open</span>
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
                  Loading more reports…
                </>
              ) : (
                "Load more reports"
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
                  Deliver Clinical Report
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Report for {deliveringReport.sample.patient.name} (
                  {deliveringReport.sample.accession_id})
                </p>
              </div>
              <button
                onClick={() => setDeliveringReport(null)}
                aria-label="Close dialog"
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
                  Delivery Channel
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setDeliveryChannel("whatsapp");
                      setDeliveryContact(
                        deliveringReport.sample.patient.phone || "",
                      );
                    }}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-semibold transition-all ${
                      deliveryChannel === "whatsapp"
                        ? "border-teal-600 bg-teal-50 text-teal-800"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <span>WhatsApp</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeliveryChannel("email");
                      setDeliveryContact(
                        deliveringReport.sample.patient.email || "",
                      );
                    }}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-semibold transition-all ${
                      deliveryChannel === "email"
                        ? "border-teal-600 bg-teal-50 text-teal-800"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <span>Email</span>
                  </button>
                </div>
              </div>

              <div>
                <label
                  htmlFor="destination-contact-input"
                  className="block text-xs font-semibold uppercase text-slate-600 mb-1.5"
                >
                  Destination Contact
                </label>
                <input
                  id="destination-contact-input"
                  type="text"
                  required
                  value={deliveryContact}
                  onChange={(e) => setDeliveryContact(e.target.value)}
                  placeholder={
                    deliveryChannel === "whatsapp"
                      ? "+92 300 1234567"
                      : "patient@example.com"
                  }
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:bg-white focus:ring-2 focus:ring-teal-600"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setDeliveringReport(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDelivering}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors disabled:opacity-50"
                >
                  {isDelivering ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Dispatching…
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      Send Report
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
