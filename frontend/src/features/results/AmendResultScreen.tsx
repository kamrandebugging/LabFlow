/**
 * Screen 25: Amend Result (/results/:id/amend).
 * Spec: Doc 03 §5.5 RS-9, §6.6, §5.6 RP-4, 25-amend-result.html.
 * Roles: Technician, Pathologist.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { statusLabel } from "../../lib/format";
import {
  Lock,
  CheckCircle2,
  Clock,
  AlertCircle,
  RefreshCw,
  ShieldCheck,
  Info,
  Check,
} from "lucide-react";
import { resultsService } from "./resultsService";
import type { ResultDetailRecord } from "./types";
import { ApiError } from "../../lib/apiClient";
import { messageForError } from "../../lib/errors";

const BDI = { bdi: <bdi dir="ltr" /> };

export function AmendResultScreen(): JSX.Element {
  const { t } = useTranslation(["results", "common"]);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<ResultDetailRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form inputs
  const [correctedValue, setCorrectedValue] = useState("");
  const [amendmentReason, setAmendmentReason] = useState("");
  const [confirmedProtocol, setConfirmedProtocol] = useState(true);

  /** API errors map through the catalogue; anything else uses screen text. */
  const describeError = (err: unknown, fallbackKey: string): string =>
    err instanceof ApiError
      ? messageForError(err, (key) => t(key))
      : t(fallbackKey);

  useEffect(() => {
    if (!id) return;
    async function loadData() {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await resultsService.getResultDetail(id!);
        if (data) {
          setDetail(data);
          setCorrectedValue(data.value);
        } else {
          setErrorMessage(t("results:amend.not_found"));
        }
      } catch (err) {
        setErrorMessage(describeError(err, "results:amend.load_error"));
      } finally {
        setLoading(false);
      }
    }
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;

    if (!correctedValue.trim()) {
      setErrorMessage(t("results:amend.correction_required"));
      return;
    }
    if (!amendmentReason.trim()) {
      setErrorMessage(t("results:amend.reason_required"));
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      await resultsService.amendResult(id, {
        value: correctedValue.trim(),
        unit: detail?.unit,
        reason: amendmentReason.trim(),
      });

      setSuccessMessage(t("results:amend.success"));
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1500);
    } catch (err) {
      setErrorMessage(describeError(err, "results:amend.submit_error"));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600 mb-2" />
        <span className="text-sm font-medium">
          {t("results:amend.loading")}
        </span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Top Breadcrumb & Header */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <nav
            aria-label={t("results:breadcrumb_aria")}
            className="flex items-center gap-2"
          >
            <Link
              to="/results/approvals"
              className="hover:text-slate-900 transition-colors"
            >
              {t("common:nav.approvals")}
            </Link>
            <span className="text-slate-400">/</span>
            <span className="text-slate-700">
              {detail?.test_name ? (
                <bdi dir="ltr">{detail.test_name}</bdi>
              ) : (
                t("results:amend.test_fallback")
              )}
            </span>
            <span className="text-slate-400">/</span>
            <span className="text-slate-900 font-semibold">
              {t("results:amend.crumb")}
            </span>
          </nav>
          <div className="flex items-center gap-2 bg-slate-100 px-3 py-1 rounded-full font-mono text-[11px] text-slate-700 border border-slate-200">
            <span>
              <bdi dir="ltr">{detail?.accession_id}</bdi>
            </span>
            <span>·</span>
            <span>
              {t("results:columns.patient")}:{" "}
              <bdi dir="ltr">{detail?.patient_name}</bdi>
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              {t("results:amend_result")}
            </h1>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
              {t("results:amend.iso_badge")}
            </span>
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-teal-700" />
            <span>{t("results:amend.session_active")}</span>
          </div>
        </div>
      </div>

      {/* Success/Error Notifications */}
      {successMessage && (
        <div
          role="status"
          className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 text-xs flex items-center gap-2"
        >
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span className="font-semibold">{successMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-900 text-xs flex items-center gap-2"
        >
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span className="font-semibold">{errorMessage}</span>
        </div>
      )}

      {/* Dual Workstation Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Immutable Baseline (Read-Only) */}
        <div className="lg:col-span-6 bg-slate-50 border border-slate-200 rounded-xl p-6 flex flex-col justify-between shadow-xs">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <div className="flex items-center gap-2">
                <Lock className="w-4 h-4 text-slate-500" />
                <h2 className="text-sm font-bold text-slate-900">
                  {t("results:amend.baseline_title")}
                </h2>
              </div>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-200 text-slate-700 px-2 py-0.5 rounded">
                {t("results:amend.immutable_badge")}
              </span>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                <Trans
                  i18nKey="results:amend.assayed_analyte"
                  values={{ test: detail?.test_name || "—" }}
                  components={BDI}
                />
              </span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-4xl font-extrabold font-mono text-slate-900">
                  <bdi dir="ltr">{detail?.value || "—"}</bdi>
                </span>
                <span className="text-base font-semibold text-slate-600">
                  <bdi dir="ltr">{detail?.unit}</bdi>
                </span>
                <span
                  className={`ms-auto inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-bold ${
                    detail?.is_critical
                      ? "bg-red-100 text-red-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {detail?.is_critical
                    ? t("results:critical_badge")
                    : (
                        detail?.flag || t("results:amend.no_flag")
                      ).toUpperCase()}
                </span>
              </div>
            </div>

            {/* Telemetry card */}
            <div className="bg-white rounded-lg p-3.5 border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">
                  {t("results:amend.signoff_authority")}
                </span>
                <span className="font-semibold text-slate-800">
                  {detail?.approved_by_name ? (
                    <bdi dir="ltr">{detail.approved_by_name}</bdi>
                  ) : (
                    t("results:amend.not_approved")
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">
                  {t("results:amend.approved_at")}
                </span>
                <span className="font-mono text-slate-800">
                  {detail?.approved_at ? (
                    <bdi dir="ltr">
                      {new Date(detail.approved_at).toLocaleString([], {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                      })}
                    </bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">
                  {t("results:amend.specimen_matrix")}
                </span>
                <span className="font-medium text-slate-800">
                  {detail?.specimen_type ? (
                    <bdi dir="ltr">{detail.specimen_type}</bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">
                  {t("results:test_code")}:
                </span>
                <span className="font-medium text-slate-800">
                  {detail?.test_code ? (
                    <bdi dir="ltr">{detail.test_code}</bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 pt-4 border-t border-slate-200 text-xs text-slate-500 mt-6">
            <ShieldCheck className="w-4 h-4 text-teal-700 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              <strong className="text-slate-800">
                {t("results:amend.original_never_edited")}
              </strong>{" "}
              <Trans i18nKey="results:amend.baseline_sealed" components={BDI} />
            </p>
          </div>
        </div>

        {/* Right Column: Correction Entry Form */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900">
                {t("results:amend.correction")}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {t("results:amend.correction_help")}
              </p>
            </div>

            {/* Corrected Value Input */}
            <div className="space-y-1">
              <label
                htmlFor="corrected-value-input"
                className="text-xs font-semibold text-slate-700 flex items-center justify-between"
              >
                <span>
                  {t("results:amend.corrected_value")}{" "}
                  <span className="text-red-600">*</span>
                </span>
                <span className="text-[10px] text-slate-400">
                  {t("common:labels.required")}
                </span>
              </label>
              <div className="relative flex items-center">
                <input
                  id="corrected-value-input"
                  type="text"
                  aria-label={t("results:amend.corrected_value_aria")}
                  value={correctedValue}
                  onChange={(e) => setCorrectedValue(e.target.value)}
                  placeholder={t("results:amend.corrected_placeholder")}
                  className="w-full text-base font-bold font-mono px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600 pe-16"
                  required
                />
                <span className="absolute end-3 font-semibold text-xs text-slate-500">
                  <bdi dir="ltr">{detail?.unit || "mmol/L"}</bdi>
                </span>
              </div>
              <div className="text-[11px] text-slate-500 pt-0.5 flex items-center gap-1">
                <Info className="w-3.5 h-3.5 text-slate-400" />
                <span>
                  <Trans
                    i18nKey="results:amend.range_label"
                    values={{
                      range:
                        detail?.matched_range ||
                        t("results:detail.not_configured"),
                    }}
                    components={BDI}
                  />
                </span>
              </div>
            </div>

            {/* Reason Textarea */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                <label htmlFor="amendment-reason-input">
                  {t("results:amend.reason")}{" "}
                  <span className="text-red-600">*</span>
                </label>
                <span className="text-[10px] font-mono text-slate-400">
                  {amendmentReason.length} / 250
                </span>
              </div>
              <textarea
                id="amendment-reason-input"
                aria-label={t("results:amend.reason_aria")}
                value={amendmentReason}
                onChange={(e) => setAmendmentReason(e.target.value)}
                placeholder={t("results:amend.reason_placeholder")}
                rows={3}
                maxLength={250}
                className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600"
                required
              />
              <span className="text-[10px] text-slate-400 block">
                {t("results:amend.reason_help")}
              </span>
            </div>

            {/* Protocol Certification Checkbox */}
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex items-start gap-2.5">
              <input
                id="certify-checkbox"
                type="checkbox"
                checked={confirmedProtocol}
                onChange={(e) => setConfirmedProtocol(e.target.checked)}
                className="mt-0.5 accent-teal-700"
                required
              />
              <label
                htmlFor="certify-checkbox"
                className="text-xs text-slate-700 cursor-pointer select-none leading-relaxed"
              >
                {t("results:amend.certify")}
              </label>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => navigate("/results/approvals")}
                className="px-4 py-2 border border-slate-300 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition-colors cursor-pointer"
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>{t("results:amend.submitting")}</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>{t("results:amend.submit")}</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Amendment Chain Timeline Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-slate-900">
              {t("results:amend.chain_title")}
            </h2>
            <p className="text-xs text-slate-500">
              {t("results:amend.chain_help")}
            </p>
          </div>
          <span className="font-mono text-xs text-slate-400">
            <bdi dir="ltr">{detail?.accession_id || "—"}</bdi>
          </span>
        </div>

        {detail?.audit_history && detail.audit_history.length > 0 ? (
          <div className="space-y-4 relative ps-6 border-l-2 border-slate-200 ms-3">
            {detail.audit_history.map((entry) => (
              <div
                className="relative"
                key={`${entry.version}-${entry.timestamp}`}
              >
                <div className="absolute --start-[31px] top-1 w-5 h-5 rounded-full bg-teal-700 text-white flex items-center justify-center text-[10px] ring-4 ring-white">
                  <Check className="w-3 h-3" />
                </div>
                <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 space-y-1 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-slate-900">
                        <bdi dir="ltr">{entry.version}</bdi>
                      </span>
                      <span>·</span>
                      <span className="font-semibold text-slate-900">
                        <bdi dir="ltr">
                          {entry.value || "—"} {entry.unit || ""}
                        </bdi>
                      </span>
                      <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-[10px] font-semibold uppercase">
                        {statusLabel("result", entry.status.toLowerCase(), t)}
                      </span>
                    </div>
                    <span className="text-slate-400 text-[11px]">
                      <bdi dir="ltr">
                        {new Date(entry.timestamp).toLocaleString([], {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                          hour12: false,
                        })}
                      </bdi>
                    </span>
                  </div>
                  <p className="text-slate-600 text-xs">
                    {entry.actor_name ? (
                      <bdi dir="ltr">{entry.actor_name}</bdi>
                    ) : (
                      t("results:amend.unknown_actor")
                    )}
                    {entry.note ? (
                      <>
                        {" · "}
                        <bdi dir="ltr">{entry.note}</bdi>
                      </>
                    ) : (
                      ""
                    )}
                    {entry.reason ? (
                      <>
                        {" · "}
                        <bdi dir="ltr">{entry.reason}</bdi>
                      </>
                    ) : (
                      ""
                    )}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500 bg-slate-50 p-4 rounded-lg border border-slate-100">
            {t("results:amend.empty")}
          </p>
        )}
      </div>
    </div>
  );
}
