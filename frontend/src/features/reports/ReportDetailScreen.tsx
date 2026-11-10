/**
 * Screen 27: Report Detail Screen (/reports/:id).
 * Spec: Doc 03 §5.6, §6.7, 27-report-detail.html.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  FileText,
  Download,
  RefreshCw,
  Send,
  Link as LinkIcon,
  Copy,
  Check,
  AlertCircle,
  CheckCircle2,
  ArrowLeft,
  X,
  Ban,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { reportsService } from "./reportsService";
import type { DeliveryChannel, ReportDetail } from "./types";

export function ReportDetailScreen(): JSX.Element | null {
  const { id } = useParams<{ id: string }>();

  const user = useAuthStore((state) => state.user);
  const userRole = user?.role?.toLowerCase() || "";

  // Role permissions per Doc 03 §6.6, §6.7
  const canRegenerate = ["owner", "manager", "pathologist"].includes(userRole);
  const canDeliver = ["owner", "manager", "reception"].includes(userRole);
  const canIssueToken = ["owner", "manager", "reception"].includes(userRole);
  const canRevokeToken = ["owner", "manager"].includes(userRole);

  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Issued token link state
  const [activeLink, setActiveLink] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [issuingToken, setIssuingToken] = useState(false);
  const [revokingToken, setRevokingToken] = useState(false);

  // Delivery Modal State
  const [showDeliveryModal, setShowDeliveryModal] = useState(false);
  const [deliveryChannel, setDeliveryChannel] =
    useState<DeliveryChannel>("whatsapp");
  const [isDelivering, setIsDelivering] = useState(false);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  // Regenerating
  const [isRegenerating, setIsRegenerating] = useState(false);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      setLoading(true);
      setErrorMessage(null);
      const data = await reportsService.getReport(id);
      setReport(data);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load report detail.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showDeliveryModal) {
        setShowDeliveryModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showDeliveryModal]);

  const handleCopyLink = () => {
    if (!activeLink) return;
    const fullUrl = activeLink.startsWith("http")
      ? activeLink
      : `${window.location.origin}${activeLink}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  };

  const handleIssueToken = async () => {
    if (!id || !canIssueToken) return;
    try {
      setIssuingToken(true);
      setErrorMessage(null);
      const res = await reportsService.issueAccessToken(id);
      setActiveLink(res.link);
      setSuccessMessage(
        "New patient access link generated. It is valid for 7 days.",
      );
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchDetail();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to issue access token.",
      );
    } finally {
      setIssuingToken(false);
    }
  };

  const handleRevokeTokens = async () => {
    if (!id || !canRevokeToken) return;
    if (
      !window.confirm(
        "Are you sure you want to revoke all patient access links for this report?",
      )
    ) {
      return;
    }
    try {
      setRevokingToken(true);
      setErrorMessage(null);
      await reportsService.revokeAccessToken(id);
      setActiveLink(null);
      setSuccessMessage("All patient access links have been revoked.");
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchDetail();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to revoke tokens.",
      );
    } finally {
      setRevokingToken(false);
    }
  };

  const handleRegenerate = async () => {
    if (!id || !canRegenerate) return;
    try {
      setIsRegenerating(true);
      setErrorMessage(null);
      await reportsService.regenerateReport(id);
      setSuccessMessage("New PDF rendering enqueued. Refreshing in a moment…");
      setTimeout(() => {
        setSuccessMessage(null);
        fetchDetail();
      }, 3000);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to regenerate report PDF.",
      );
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleDeliverSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !report) return;

    // Delivery is addressed to a stored PatientContact row. Without one the
    // backend rejects the request (ContactNotFoundError), so resolve it here
    // and fail loudly instead of sending a patient id as a contact id.
    const contact = report.patient.contacts?.find(
      (c) => c.kind === deliveryChannel,
    );
    if (!contact) {
      setDeliveryError(
        `No ${deliveryChannel === "whatsapp" ? "WhatsApp" : "email"} contact is recorded for this patient. Add one on the patient record before delivering.`,
      );
      return;
    }

    try {
      setIsDelivering(true);
      setDeliveryError(null);

      const res = await reportsService.deliverReport(id, {
        channel: deliveryChannel,
        contact_id: contact.id,
      });

      if (res.link) {
        setActiveLink(res.link);
      }

      setSuccessMessage(
        `Report dispatched successfully via ${deliveryChannel}.`,
      );
      setShowDeliveryModal(false);
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchDetail();
    } catch (err) {
      setDeliveryError(
        err instanceof Error ? err.message : "Failed to dispatch delivery.",
      );
    } finally {
      setIsDelivering(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
        <span className="text-sm font-medium">Loading report…</span>
      </div>
    );
  }

  if (errorMessage && !report) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-4">
        <div className="w-12 h-12 rounded-full bg-rose-50 flex items-center justify-center text-rose-600">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">Report Not Found</h2>
        <p className="text-sm text-slate-500 max-w-sm">{errorMessage}</p>
        <Link
          to="/reports"
          className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Reports
        </Link>
      </div>
    );
  }

  if (!report) return null;

  const hasActiveToken = report.access_tokens.some((t) => t.is_active);
  const deliveryContactRecord =
    report.patient.contacts?.find((c) => c.kind === deliveryChannel) ?? null;
  const hasEmailContact =
    report.patient.contacts?.some((c) => c.kind === "email") ?? false;

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 gap-6">
      {/* Breadcrumb & Action Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex flex-col gap-1">
          <nav className="flex items-center gap-2 text-xs text-slate-500">
            <Link
              to="/reports"
              className="hover:text-teal-700 transition-colors flex items-center gap-1"
            >
              <FileText className="w-3.5 h-3.5" />
              Reports
            </Link>
            <span>/</span>
            <span className="font-mono text-slate-700 font-medium">
              {report.sample.accession_id}
            </span>
          </nav>
          <div className="flex flex-wrap items-center gap-3 mt-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
              {report.sample.accession_id}
            </h1>
            <span className="text-slate-300">•</span>
            <Link
              to={`/patients/${report.patient.id}`}
              className="text-base font-semibold text-teal-700 hover:underline"
            >
              {report.patient.full_name}
            </Link>
            <span className="text-xs font-mono text-slate-500">
              ({report.patient.mrn})
            </span>
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider ${
                report.status === "final"
                  ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                  : report.status === "amended"
                    ? "bg-amber-50 text-amber-800 border border-amber-200"
                    : report.status === "void"
                      ? "bg-rose-50 text-rose-800 border border-rose-200"
                      : "bg-slate-100 text-slate-700 border border-slate-200"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  report.status === "final"
                    ? "bg-emerald-600"
                    : report.status === "amended"
                      ? "bg-amber-600"
                      : "bg-slate-400"
                }`}
              ></span>
              {report.status}
            </span>
          </div>
        </div>

        {/* Toolbar Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {canRegenerate && (
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors shadow-xs disabled:opacity-50"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isRegenerating ? "animate-spin" : ""}`}
              />
              <span>Regenerate</span>
            </button>
          )}

          {canDeliver && (
            <button
              onClick={() => {
                setDeliveryError(null);
                setShowDeliveryModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-xs"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Deliver</span>
            </button>
          )}

          {/* Direct Print / Preview trigger */}
          <button
            onClick={() => window.print()}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors shadow-xs"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Print PDF</span>
          </button>
        </div>
      </div>

      {/* Alert Messages */}
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

      {report.generation_status === "failed" && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 text-sm text-rose-800 bg-rose-50 border border-rose-200 rounded-xl">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <div className="flex-1">
            <span className="font-semibold">PDF generation failed.</span>{" "}
            <span className="text-rose-700">
              {report.generation_error ||
                "The renderer could not produce this report version."}
            </span>
          </div>
          {canRegenerate && (
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-600 text-white hover:bg-rose-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isRegenerating ? "animate-spin" : ""}`}
              />
              <span>Regenerate PDF</span>
            </button>
          )}
        </div>
      )}

      {report.generation_status === "running" && (
        <div className="flex items-center gap-2 p-4 text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-xl">
          <RefreshCw className="w-5 h-5 shrink-0 animate-spin text-teal-600" />
          <span className="flex-1">
            Rendering the report PDF. This page will update when the version is
            finalised.
          </span>
          <button
            onClick={fetchDetail}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
          >
            Refresh
          </button>
        </div>
      )}

      {/* Main Grid: Left PDF Paper Specimen, Right Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Rendered Specimen Preview Canvas */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm flex flex-col gap-6">
            {/* Specimen Header */}
            <div className="flex justify-between items-start pb-5 border-b-2 border-slate-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 font-bold">
                  LF
                </div>
                <div>
                  <h2 className="text-lg font-bold uppercase tracking-tight text-slate-900 leading-tight">
                    {report.branding?.display_name || "Diagnostic Laboratory"}
                  </h2>
                  <p className="text-xs text-slate-500">
                    {report.sample.branch?.name || "Clinical Laboratory Report"}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <span className="inline-block px-2.5 py-0.5 bg-slate-100 text-slate-700 font-mono text-[11px] font-semibold rounded uppercase">
                  Confidential Medical Record
                </span>
                <p className="text-[11px] font-mono text-slate-400 mt-1">
                  {report.sample.accession_id}
                </p>
              </div>
            </div>

            {/* Demographics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-lg text-xs">
              <div>
                <span className="text-slate-400 font-medium uppercase block text-[10px]">
                  Patient
                </span>
                <span className="font-semibold text-slate-900 block truncate text-sm">
                  {report.patient.full_name}
                </span>
                <span className="text-slate-500 font-mono">
                  {report.patient.gender || "U"} ·{" "}
                  {report.patient.age_years != null
                    ? `${report.patient.age_years}Y`
                    : "Age not recorded"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium uppercase block text-[10px]">
                  MRN
                </span>
                <span className="font-mono font-semibold text-slate-900 block text-sm">
                  {report.patient.mrn}
                </span>
                <span className="text-slate-500">
                  {report.patient.phone || "No phone"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium uppercase block text-[10px]">
                  Accession ID
                </span>
                <span className="font-mono font-semibold text-teal-800 block text-sm">
                  {report.sample.accession_id}
                </span>
                <span className="text-slate-500">
                  Branch: {report.sample.branch?.name || "Main Reference"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium uppercase block text-[10px]">
                  Reported Date
                </span>
                <span className="font-mono text-slate-800 block text-sm">
                  {new Date(report.created_at).toLocaleDateString("en-GB", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
                <span className="text-slate-500">
                  {report.current_version > 0
                    ? `Version ${report.current_version}`
                    : "PDF not generated yet"}
                </span>
              </div>
            </div>

            {/* Results Table */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                Laboratory Test Results
              </h3>
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3" scope="col">
                        Investigation
                      </th>
                      <th className="py-2.5 px-3" scope="col">
                        Result
                      </th>
                      <th className="py-2.5 px-3" scope="col">
                        Unit
                      </th>
                      <th className="py-2.5 px-3" scope="col">
                        Flag
                      </th>
                      <th className="py-2.5 px-3" scope="col">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.results.length === 0 ? (
                      <tr>
                        <td
                          colSpan={5}
                          className="py-6 text-center text-slate-400"
                        >
                          No results recorded for this report.
                        </td>
                      </tr>
                    ) : (
                      report.results.map((res) => (
                        <tr key={res.id} className="hover:bg-slate-50/50">
                          <td className="py-3 px-3 font-medium text-slate-900">
                            <div>{res.test_name}</div>
                            <div className="font-mono text-[10px] text-slate-400">
                              {res.test_code}
                            </div>
                          </td>
                          <td className="py-3 px-3 font-mono font-semibold text-slate-900">
                            {res.value}
                          </td>
                          <td className="py-3 px-3 text-slate-500 font-mono">
                            {res.unit || "—"}
                          </td>
                          <td className="py-3 px-3">
                            {res.flag === "critical" ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
                                CRITICAL
                              </span>
                            ) : res.flag === "abnormal" ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">
                                ABNORMAL
                              </span>
                            ) : (
                              <span className="text-slate-400">Normal</span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-slate-600 capitalize">
                            {res.status}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Specimen Footer */}
            <div className="pt-4 border-t border-slate-200 flex flex-col sm:flex-row justify-between items-center text-xs text-slate-400 gap-2">
              <span>Electronic report verified.</span>
              <span className="font-mono">End of Report</span>
            </div>
          </div>
        </div>

        {/* Right Sidebar: Access Link & Delivery History */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          {/* Patient Access Link Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Patient Access Link
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Public redemption link for the patient — no password needed.
              </p>
            </div>

            {activeLink ? (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <LinkIcon className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="font-mono text-xs text-slate-700 truncate">
                    {activeLink}
                  </span>
                </div>
                <button
                  onClick={handleCopyLink}
                  className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors shadow-xs"
                >
                  {copiedLink ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-600" />
                      <span className="text-emerald-600">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            ) : hasActiveToken ? (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800">
                An active token exists for this report. Generate a new link or
                revoke existing tokens below.
              </div>
            ) : (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
                No active patient access links issued yet.
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              {canIssueToken && (
                <button
                  onClick={handleIssueToken}
                  disabled={issuingToken}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors disabled:opacity-50"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${issuingToken ? "animate-spin" : ""}`}
                  />
                  <span>
                    {hasActiveToken || activeLink
                      ? "Reissue link"
                      : "Issue link"}
                  </span>
                </button>
              )}

              {canRevokeToken && (hasActiveToken || activeLink) && (
                <button
                  onClick={handleRevokeTokens}
                  disabled={revokingToken}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-50 text-rose-700 hover:bg-rose-100 transition-colors disabled:opacity-50"
                >
                  <Ban className="w-3 h-3" />
                  <span>Revoke links</span>
                </button>
              )}
            </div>
          </div>

          {/* Delivery History Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col gap-3">
            <h3 className="text-sm font-bold text-slate-900">
              Delivery Records
            </h3>

            {report.deliveries.length === 0 ? (
              <div className="py-4 text-center text-xs text-slate-400">
                No deliveries attempted yet.
              </div>
            ) : (
              <div className="space-y-2.5">
                {report.deliveries.map((d) => (
                  <div
                    key={d.id}
                    className="p-3 rounded-lg bg-slate-50 border border-slate-100 flex items-start justify-between gap-3 text-xs"
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="w-7 h-7 rounded-md bg-teal-100 text-teal-800 flex items-center justify-center shrink-0 mt-0.5 font-bold uppercase">
                        {d.channel === "whatsapp" ? "WA" : "EM"}
                      </div>
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-900 capitalize">
                            {d.channel}
                          </span>
                          <span
                            className={`px-1.5 py-0.2 rounded text-[10px] font-semibold uppercase ${
                              d.status === "delivered" || d.status === "opened"
                                ? "bg-sky-100 text-sky-800"
                                : d.status === "sent"
                                  ? "bg-teal-100 text-teal-800"
                                  : "bg-rose-100 text-rose-800"
                            }`}
                          >
                            {d.status}
                          </span>
                        </div>
                        <span className="text-slate-500 font-mono text-[11px] block mt-0.5 truncate max-w-[140px]">
                          {d.contact_value || "—"}
                        </span>
                      </div>
                    </div>
                    <div className="text-right text-[11px] font-mono text-slate-400">
                      {new Date(d.created_at).toLocaleTimeString("en-GB", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Audit & Compliance Metadata */}
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 text-xs flex flex-col gap-2 text-slate-600">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Audit & Compliance
            </div>
            <div className="flex justify-between items-center py-0.5">
              <span>Accession ID</span>
              <span className="font-mono text-slate-900 font-medium">
                {report.sample.accession_id}
              </span>
            </div>
            <div className="flex justify-between items-center py-0.5">
              <span>Report Versions</span>
              <span className="font-mono text-slate-900 font-medium">
                {report.versions.length > 0
                  ? `${report.versions.length} generated`
                  : "Not generated yet"}
              </span>
            </div>
            <div className="flex justify-between items-center py-0.5">
              <span>Encryption</span>
              <span className="font-mono text-teal-700 font-semibold">
                TLS 1.3 · AES-256
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Deliver Modal */}
      {showDeliveryModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="detail-deliver-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3
                  id="detail-deliver-modal-title"
                  className="text-lg font-bold text-slate-900"
                >
                  Deliver Report
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Send to {report.patient.full_name}
                </p>
              </div>
              <button
                onClick={() => setShowDeliveryModal(false)}
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
                  Channel
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
                    <span>WhatsApp</span>
                  </button>
                  <button
                    type="button"
                    disabled={!hasEmailContact}
                    title={
                      hasEmailContact
                        ? undefined
                        : "No email contact is stored for this patient"
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
                    <span>Email</span>
                  </button>
                </div>
              </div>

              <div>
                <label
                  htmlFor="detail-delivery-contact-input"
                  className="block text-xs font-semibold uppercase text-slate-600 mb-1.5"
                >
                  Recipient Contact
                </label>
                {deliveryContactRecord ? (
                  <>
                    <input
                      id="detail-delivery-contact-input"
                      type="text"
                      readOnly
                      value={deliveryContactRecord.value}
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono"
                    />
                    <p className="mt-1 text-[11px] text-slate-400">
                      Stored {deliveryChannel} contact on this patient record.
                    </p>
                  </>
                ) : (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900">
                    No stored {deliveryChannel} contact for this patient. Update
                    the patient record with a{" "}
                    {deliveryChannel === "whatsapp"
                      ? "WhatsApp number"
                      : "email address"}{" "}
                    before delivering this report.
                  </div>
                )}
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowDeliveryModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDelivering || !deliveryContactRecord}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isDelivering ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Sending…
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      Send
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
