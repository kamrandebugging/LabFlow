/**
 * Screen 24: Result Detail (/results/:id).
 * Spec: Doc 03 §5.5 RS-4–RS-10, 24-result-detail.html.
 * Roles: Pathologist, Technician.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
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
import { resultsService } from "./resultsService";
import type { ResultDetailRecord } from "./types";

export function ResultDetailScreen(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<ResultDetailRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Decision Form State
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [decisionNote, setDecisionNote] = useState("");
  const [submittingDecision, setSubmittingDecision] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  useEffect(() => {
    if (!id) return;
    async function loadData() {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await resultsService.getResultDetail(id!);
        if (!data) {
          setErrorMessage("Result record not found or endpoint not available.");
        } else {
          setDetail(data);
        }
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Failed to load result detail record.",
        );
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [id]);

  const handleSubmitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;

    if (decision === "rejected" && !decisionNote.trim()) {
      setErrorMessage("A rejection note is mandatory.");
      return;
    }

    try {
      setSubmittingDecision(true);
      setErrorMessage(null);
      await resultsService.approveResult(id, {
        decision,
        note: decisionNote.trim() || undefined,
        range_override: false,
      });

      setSuccessMessage(`Result ${decision} successfully.`);
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1200);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to submit clinical decision.",
      );
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
      setSuccessMessage("Result successfully withdrawn.");
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1200);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to withdraw result.",
      );
    } finally {
      setWithdrawing(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600 mb-2" />
        <span className="text-sm font-medium">Loading diagnostic review...</span>
      </div>
    );
  }

  if (errorMessage && !detail) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-12">
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-slate-400 mx-auto" />
          <h2 className="text-lg font-bold text-slate-900">
            Result Not Found
          </h2>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            {errorMessage}
          </p>
          <div className="pt-2">
            <Link
              to="/results/approvals"
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-100 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Approvals Queue</span>
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
          aria-label="Breadcrumb"
          className="flex items-center gap-2 text-xs font-medium text-slate-500"
        >
          <Link
            to="/results/approvals"
            className="hover:text-slate-900 transition-colors flex items-center gap-1"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-teal-700" />
            <span>Approvals</span>
          </Link>
          <span className="text-slate-400">/</span>
          <span className="font-mono text-slate-700">
            {detail?.accession_id}
          </span>
          <span className="text-slate-400">/</span>
          <span className="text-slate-900 font-semibold">
            {detail?.test_name}
          </span>
        </nav>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {detail?.test_name}
              </h1>
              {detail?.is_critical && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse" />
                  CRITICAL
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 bg-slate-50 px-3 py-1 rounded-full border border-slate-200 text-xs">
              <span className="text-slate-500">Patient:</span>
              <span className="font-semibold text-slate-900">
                {detail?.patient_name}
              </span>
              <span className="text-slate-300">·</span>
              <span className="font-mono text-slate-500">
                {detail?.patient_mrn}
              </span>
              <span className="text-slate-300">·</span>
              <span className="text-slate-600">
                {detail?.patient_sex === "M" ? "Male" : "Female"},{" "}
                {detail?.patient_age_years || 34}y
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {detail?.status === "entered" && (
              <button
                type="button"
                onClick={handleWithdraw}
                disabled={withdrawing}
                className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                <span>Withdraw result</span>
              </button>
            )}

            <Link
              to={`/results/${id}/amend`}
              className="px-3 py-1.5 rounded-lg border border-teal-200 bg-teal-50 hover:bg-teal-100 text-teal-800 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Amend result</span>
            </Link>
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
                  Result Details
                </h2>
              </div>
              <span className="font-mono text-xs text-slate-600 bg-slate-100 px-2.5 py-0.5 rounded">
                {detail?.method || "Ion-Selective Electrode (ISE)"}
              </span>
            </div>

            {/* Large Primary Readout */}
            <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-3 bg-slate-50 rounded-xl p-5 border border-slate-100">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-5xl font-extrabold font-mono text-red-700 tracking-tight">
                    {detail?.value}
                  </span>
                  <span className="text-lg font-medium text-slate-600">
                    {detail?.unit}
                  </span>
                </div>
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800 mt-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                  <span>high (critical)</span>
                </div>
              </div>

              <div className="text-left sm:text-right">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold block">
                  Reference Interval
                </span>
                <span className="font-mono text-sm font-semibold text-slate-900 block mt-0.5">
                  Matched: {detail?.matched_range || "3.5 – 5.1 mmol/L"}
                </span>
                <span className="text-xs text-red-700 font-semibold block mt-0.5">
                  Critical Panic Threshold: &gt; 6.2 mmol/L
                </span>
              </div>
            </div>

            {/* Specimen & Telemetry Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs border-t border-slate-100">
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  Specimen
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.specimen_type || "Serum (Gold top)"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  Analyzer
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.analyzer || "Roche Cobas c501"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  Run Timestamp
                </span>
                <span className="font-mono text-slate-800 mt-0.5 block">
                  20 Oct 2026, 09:38 PKT
                </span>
              </div>
              <div>
                <span className="text-slate-400 font-medium text-[10px] uppercase block">
                  Entered By
                </span>
                <span className="font-semibold text-slate-800 mt-0.5 block">
                  {detail?.entered_by_name || "Usman Tariq"}
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
                  Delta Check
                </h2>
              </div>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200">
                <AlertTriangle className="w-3 h-3" />
                <span>{detail?.delta_note || "Δ +2.6 — exceeds delta limit"}</span>
              </span>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50 p-4 rounded-lg border border-slate-100">
              <div>
                <span className="font-semibold text-slate-900 text-sm block">
                  Previous approved: {detail?.previous_value || "4.2 mmol/L"}
                </span>
                <span className="text-xs text-slate-500">
                  Validated on {detail?.previous_date || "14 Sep 2026"}
                </span>
              </div>
              <div className="font-mono text-xs">
                <span className="text-slate-500">Shift Rate: </span>
                <span className="font-bold text-amber-700">
                  {detail?.shift_rate || "+61.9% in 36 days"}
                </span>
              </div>
            </div>
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
                  Critical Notification
                </h2>
              </div>
              <span className="text-xs font-mono font-semibold text-teal-800 bg-teal-50 px-2 py-0.5 rounded">
                Read-back: Yes
              </span>
            </div>

            <div className="bg-slate-50 p-4 rounded-lg border border-slate-100 space-y-1">
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">
                Immediate Verbal Dispatch
              </div>
              <p className="text-sm font-semibold text-slate-900">
                Notified: {detail?.critical_notification?.notified_name || "Dr. Tariq Niazi"}
              </p>
              <p className="text-xs text-slate-500">
                Recipient: {detail?.critical_notification?.recipient_role || "Ward Medical Officer"} · Verified
              </p>
            </div>

            <div className="text-xs text-slate-500 flex items-center gap-1.5 pt-1">
              <ShieldCheck className="w-4 h-4 text-teal-700 shrink-0" />
              <span>Compliant with ISO 15189:2022 §7.3.3 verbal panic protocol</span>
            </div>
          </div>

          {/* Card 4: Pathologist Decision Card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-teal-700" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Pathologist Decision
                </h2>
              </div>
              <span className="text-xs font-mono text-slate-500">
                Sign-off Desk
              </span>
            </div>

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
                      Approve
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 pl-5">
                    Release to EHR report
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
                      Reject
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 pl-5">
                    Request Recollect
                  </span>
                </label>
              </div>

              {/* Rationale Input */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                  <span>Decision Note</span>
                  {decision === "rejected" && (
                    <span className="text-red-600 text-[10px] font-bold">
                      Mandatory for rejection
                    </span>
                  )}
                </label>
                <textarea
                  value={decisionNote}
                  onChange={(e) => setDecisionNote(e.target.value)}
                  placeholder="Document clinical review rationale, verbal notifications, and clinical validation reasons..."
                  rows={3}
                  className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600"
                />
              </div>

              {/* Policy note */}
              <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>
                  Decision is locked to permanent audit ledger.
                </span>
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={submittingDecision}
                className="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {submittingDecision ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Transmitting decision...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Submit decision</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
