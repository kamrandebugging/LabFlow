/**
 * Screen 24: Result Detail (/results/:id).
 * Spec: Doc 03 §5.5 RS-4–RS-10, 24-result-detail.html.
 * Roles: Pathologist, Technician.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import {
  FlaskConical,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Edit3,
  PhoneCall,
  ShieldCheck,
  TrendingUp,
  RefreshCw,
  AlertCircle,
  ArrowLeft,
  Info,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { resultsService } from "./resultsService";
import type { ResultDetailRecord } from "./types";
import { ApiError } from "../../lib/apiClient";
import { messageForError } from "../../lib/errors";

const BDI = { bdi: <bdi dir="ltr" /> };

export function ResultDetailScreen(): JSX.Element {
  const { t } = useTranslation(["results", "common"]);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const canApprove = user?.role === "pathologist" || user?.role === "owner";
  const canAmend =
    user?.role === "technician" ||
    user?.role === "pathologist" ||
    user?.role === "owner";
  const backPath =
    user?.role === "technician"
      ? "/worklist"
      : user?.role === "manager" || user?.role === "reception"
        ? "/exceptions"
        : "/results/approvals";

  const [detail, setDetail] = useState<ResultDetailRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Decision Form State
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [decisionNote, setDecisionNote] = useState("");
  const [attestation, setAttestation] = useState(false);
  const [submittingDecision, setSubmittingDecision] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  /** API errors map through the catalogue; anything else uses screen text. */
  const describeError = (err: unknown, fallbackKey: string): string =>
    err instanceof ApiError
      ? messageForError(err, (key) => t(key))
      : t(fallbackKey);

  useEffect(() => {
    if (!id) return;
    // A reused route must never carry the previous result's attestation.
    setAttestation(false);
    setDecisionNote("");
    async function loadData() {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await resultsService.getResultDetail(id!);
        if (!data) {
          setErrorMessage(t("results:detail.not_found_body"));
        } else {
          setDetail(data);
        }
      } catch (err) {
        setErrorMessage(describeError(err, "results:detail.load_error"));
      } finally {
        setLoading(false);
      }
    }
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleSubmitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;

    if (decision === "rejected" && !decisionNote.trim()) {
      setErrorMessage(t("results:detail.rejection_note_required"));
      return;
    }
    if (decision === "approved" && !attestation) {
      setErrorMessage(t("results:detail.attestation_required"));
      return;
    }

    try {
      setSubmittingDecision(true);
      setErrorMessage(null);
      await resultsService.approveResult(id, {
        decision,
        note: decisionNote.trim() || undefined,
        range_override: false,
        attestation: decision === "approved" ? attestation : false,
      });

      setSuccessMessage(
        decision === "approved"
          ? t("results:detail.decision_approved_success")
          : t("results:detail.decision_rejected_success"),
      );
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1200);
    } catch (err) {
      setErrorMessage(describeError(err, "results:detail.decision_error"));
    } finally {
      setSubmittingDecision(false);
    }
  };

  const handleWithdraw = async () => {
    if (!id) return;
    try {
      setWithdrawing(true);
      setErrorMessage(null);
      await resultsService.withdrawResult(id);
      setSuccessMessage(t("results:detail.withdraw_success"));
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1200);
    } catch (err) {
      setErrorMessage(describeError(err, "results:detail.withdraw_error"));
    } finally {
      setWithdrawing(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600 mb-2" />
        <span className="text-sm font-medium">
          {t("results:detail.loading")}
        </span>
      </div>
    );
  }

  if (errorMessage && !detail) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-12">
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-slate-400 mx-auto" />
          <h2 className="text-lg font-bold text-slate-900">
            {t("results:detail.not_found_title")}
          </h2>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            {errorMessage}
          </p>
          <div className="pt-2">
            <Link
              to={backPath}
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-100 transition-colors"
            >
              <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
              <span>{t("common:actions.back")}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Top Header & Breadcrumbs */}
      <div className="flex flex-col gap-2">
        <nav
          aria-label={t("results:breadcrumb_aria")}
          className="flex items-center gap-2 text-xs font-medium text-slate-500"
        >
          <Link
            to="/results/approvals"
            className="hover:text-slate-900 transition-colors flex items-center gap-1"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-teal-700" />
            <span>{t("common:nav.approvals")}</span>
          </Link>
          <span className="text-slate-400">/</span>
          <span className="font-mono text-slate-700">
            <bdi dir="ltr">{detail?.accession_id}</bdi>
          </span>
          <span className="text-slate-400">/</span>
          <span className="text-slate-900 font-semibold">
            <bdi dir="ltr">{detail?.test_name}</bdi>
          </span>
        </nav>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                <bdi dir="ltr">{detail?.test_name}</bdi>
              </h1>
              {detail?.is_critical && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse" />
                  {t("results:critical_badge")}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 bg-slate-50 px-3 py-1 rounded-full border border-slate-200 text-xs">
              <span className="text-slate-500">
                {t("results:columns.patient")}:
              </span>
              <span className="font-semibold text-slate-900">
                <bdi dir="ltr">{detail?.patient_name}</bdi>
              </span>
              <span className="text-slate-300">·</span>
              <span className="font-mono text-slate-500">
                <bdi dir="ltr">{detail?.patient_mrn}</bdi>
              </span>
              <span className="text-slate-300">·</span>
              <span className="text-slate-600">
                {detail?.patient_sex === "M"
                  ? t("results:sex_male")
                  : detail?.patient_sex === "F"
                    ? t("results:sex_female")
                    : "—"}
                ,{" "}
                {detail?.patient_age_years !== undefined ? (
                  <Trans
                    i18nKey="results:age_short"
                    values={{ age: detail.patient_age_years }}
                    components={BDI}
                  />
                ) : (
                  "—"
                )}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {detail?.status === "entered" &&
            canAmend &&
            detail.entered_by_name === user?.email ? (
              <button
                type="button"
                onClick={handleWithdraw}
                disabled={withdrawing}
                className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                <span>{t("results:detail.withdraw")}</span>
              </button>
            ) : null}

            {canAmend ? (
              <Link
                to={`/results/${id}/amend`}
                className="px-3 py-1.5 rounded-lg border border-teal-200 bg-teal-50 hover:bg-teal-100 text-teal-800 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>{t("results:amend_result")}</span>
              </Link>
            ) : null}
          </div>
        </div>
      </div>

      {/* Success/Error Feedback */}
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

      {/* Main Diagnostic Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left Column: Quantitative Metrics & Delta Check (7 cols) */}
        <div className="md:col-span-7 space-y-6">
          {/* Card 1: Result Analysis Readout */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-teal-700" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {t("results:detail.card_details")}
                </h2>
              </div>
              <span className="font-mono text-xs text-slate-600 bg-slate-100 px-2.5 py-0.5 rounded">
                {detail?.test_code ? (
                  <bdi dir="ltr">{detail.test_code}</bdi>
                ) : (
                  "—"
                )}
              </span>
            </div>

            {/* Large Primary Readout */}
            <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-3 bg-slate-50 rounded-xl p-5 border border-slate-100">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-5xl font-extrabold font-mono text-red-700 tracking-tight">
                    <bdi dir="ltr">{detail?.value}</bdi>
                  </span>
                  <span className="text-lg font-medium text-slate-600">
                    <bdi dir="ltr">{detail?.unit}</bdi>
                  </span>
                </div>
                <div
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold mt-2 ${
                    detail?.is_critical
                      ? "bg-red-100 text-red-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      detail?.is_critical ? "bg-red-600" : "bg-slate-400"
                    }`}
                  />
                  <span>
                    {detail?.is_critical
                      ? t("results:detail.flag_critical")
                      : detail?.flag || t("results:detail.no_flag")}
                  </span>
                </div>
              </div>

              <div className="text-start sm:text-right">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold block">
                  {t("results:columns.reference")}
                </span>
                <span className="font-mono text-sm font-semibold text-slate-900 block mt-0.5">
                  <Trans
                    i18nKey="results:detail.matched"
                    values={{
                      range:
                        detail?.matched_range ||
                        t("results:detail.not_configured"),
                    }}
                    components={BDI}
                  />
                </span>
                <span className="text-xs text-red-700 font-semibold block mt-0.5">
                  <Trans
                    i18nKey="results:detail.panic_threshold"
                    values={{
                      range:
                        detail?.critical_threshold ||
                        t("results:detail.not_configured"),
                    }}
                    components={BDI}
                  />
                </span>
              </div>
            </div>

            {/* Specimen & Telemetry Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs border-t border-slate-100">
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  {t("results:detail.specimen")}
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.specimen_type ? (
                    <bdi dir="ltr">{detail.specimen_type}</bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  {t("results:test_code")}
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.test_code ? (
                    <bdi dir="ltr">{detail.test_code}</bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  {t("results:detail.entered_at")}
                </span>
                <span className="font-mono text-slate-800 mt-0.5 block">
                  {detail?.entered_at ? (
                    <bdi dir="ltr">
                      {new Date(detail.entered_at).toLocaleString([], {
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
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  {t("results:columns.entered_by")}
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.entered_by_name ? (
                    <bdi dir="ltr">{detail.entered_by_name}</bdi>
                  ) : (
                    "—"
                  )}
                </span>
              </div>
            </div>
          </div>

          {/* Card 2: Longitudinal Delta Check */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-amber-600" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {t("results:detail.delta_title")}
                </h2>
              </div>
              {detail?.previous_value ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200">
                  <AlertTriangle className="w-3 h-3" />
                  <span>
                    {detail.delta_note ? (
                      <bdi dir="ltr">{detail.delta_note}</bdi>
                    ) : (
                      t("results:detail.prior_available")
                    )}
                  </span>
                </span>
              ) : (
                <span className="text-xs text-slate-500">—</span>
              )}
            </div>

            {detail?.previous_value ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50 p-4 rounded-lg border border-slate-100">
                <div>
                  <span className="font-semibold text-slate-900 text-sm block">
                    <Trans
                      i18nKey="results:detail.previous_approved"
                      values={{ value: detail.previous_value }}
                      components={BDI}
                    />
                  </span>
                  {detail.previous_date && (
                    <span className="text-xs text-slate-500">
                      <Trans
                        i18nKey="results:detail.validated_on"
                        values={{ date: detail.previous_date }}
                        components={BDI}
                      />
                    </span>
                  )}
                </div>
                {detail.shift_rate && (
                  <div className="font-mono text-xs">
                    <span className="text-slate-500">
                      {t("results:detail.shift_rate_label")}{" "}
                    </span>
                    <span className="font-bold text-amber-700">
                      <bdi dir="ltr">{detail.shift_rate}</bdi>
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500 bg-slate-50 p-4 rounded-lg border border-slate-100">
                {t("results:detail.no_prior")}
              </p>
            )}
          </div>
        </div>

        {/* Right Column: Notification Log & Pathologist Decision (5 cols) */}
        <div className="md:col-span-5 space-y-6">
          {/* Card 3: Critical Telephone Notification Audit */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <PhoneCall className="w-4 h-4 text-teal-700" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {t("results:detail.critical_notification_title")}
                </h2>
              </div>
              <span className="text-xs font-mono font-semibold text-teal-800 bg-teal-50 px-2 py-0.5 rounded">
                <Trans
                  i18nKey="results:detail.read_back"
                  values={{
                    value: detail?.critical_notification
                      ? detail.critical_notification.read_back
                        ? t("common:labels.yes")
                        : t("common:labels.no")
                      : "—",
                  }}
                  components={BDI}
                />
              </span>
            </div>

            {detail?.critical_notification ? (
              <div className="bg-slate-50 p-4 rounded-lg border border-slate-100 space-y-1">
                <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">
                  {t("results:detail.verbal_dispatch")}
                </div>
                <p className="text-sm font-semibold text-slate-900">
                  <Trans
                    i18nKey="results:detail.notified"
                    values={{
                      name: detail.critical_notification.notified_name,
                    }}
                    components={BDI}
                  />
                </p>
                <p className="text-xs text-slate-500">
                  <Trans
                    i18nKey="results:detail.notified_at"
                    values={{
                      date: new Date(
                        detail.critical_notification.notified_at,
                      ).toLocaleString([], {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                      }),
                    }}
                    components={BDI}
                  />
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-500 bg-slate-50 p-4 rounded-lg border border-slate-100">
                {t("results:detail.no_notification")}
              </p>
            )}

            <div className="text-xs text-slate-500 flex items-center gap-1.5 pt-1">
              <ShieldCheck className="w-4 h-4 text-teal-700 shrink-0" />
              <span>
                <Trans
                  i18nKey="results:detail.iso_compliance"
                  components={BDI}
                />
              </span>
            </div>
          </div>

          {/* Card 4: Pathologist Decision Card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-teal-700" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {t("results:detail.decision_title")}
                </h2>
              </div>
              <span className="text-xs font-mono text-slate-500">
                {t("results:detail.signoff_desk")}
              </span>
            </div>

            {canApprove ? (
              <form onSubmit={handleSubmitDecision} className="space-y-4">
                {/* Radio Selector */}
                <div className="grid grid-cols-2 gap-3">
                  <label
                    className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                      decision === "approved"
                        ? "border-teal-600 bg-teal-50/50"
                        : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="decision"
                        value="approved"
                        checked={decision === "approved"}
                        onChange={() => setDecision("approved")}
                        className="accent-teal-700"
                      />
                      <span className="text-xs font-bold text-slate-900">
                        {t("results:detail.approve")}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 mt-1 ps-5">
                      {t("results:detail.release_to_ehr")}
                    </span>
                  </label>

                  <label
                    className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                      decision === "rejected"
                        ? "border-red-600 bg-red-50/50"
                        : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="decision"
                        value="rejected"
                        checked={decision === "rejected"}
                        onChange={() => setDecision("rejected")}
                        className="accent-red-600"
                      />
                      <span className="text-xs font-bold text-slate-900">
                        {t("results:detail.reject")}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 mt-1 ps-5">
                      {t("results:detail.request_recollect")}
                    </span>
                  </label>
                </div>

                {/* Rationale Input */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                    <span>{t("results:detail.decision_note")}</span>
                    {decision === "rejected" && (
                      <span className="text-red-600 text-[10px] font-bold">
                        {t("results:detail.mandatory_for_rejection")}
                      </span>
                    )}
                  </label>
                  <textarea
                    value={decisionNote}
                    onChange={(e) => setDecisionNote(e.target.value)}
                    placeholder={t("results:detail.decision_placeholder")}
                    rows={3}
                    className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600"
                  />
                </div>

                {decision === "approved" && (
                  <label className="flex items-start gap-2 text-xs text-slate-700 bg-teal-50/50 p-3 rounded-lg border border-teal-100 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={attestation}
                      onChange={(e) => setAttestation(e.target.checked)}
                      className="mt-0.5 accent-teal-700"
                    />
                    <span>{t("results:detail.attestation")}</span>
                  </label>
                )}

                {/* Policy note */}
                <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span>{t("results:detail.decision_locked")}</span>
                </div>

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={
                    submittingDecision ||
                    (decision === "approved" && !attestation)
                  }
                  className="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {submittingDecision ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>{t("results:detail.transmitting")}</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>{t("results:detail.submit_decision")}</span>
                    </>
                  )}
                </button>
              </form>
            ) : (
              <p className="text-xs text-slate-500 bg-slate-50 p-4 rounded-lg border border-slate-100">
                {t("results:detail.read_only")}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
