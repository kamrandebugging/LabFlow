/**
 * Screen 25: Amend Result (/results/:id/amend).
 * Spec: Doc 03 §5.5 RS-9, §6.6, §5.6 RP-4, 25-amend-result.html.
 * Roles: Technician, Pathologist.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
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

export function AmendResultScreen(): JSX.Element {
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
          setErrorMessage("Result record not found.");
        }
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Failed to load result for amendment.",
        );
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;

    if (!correctedValue.trim()) {
      setErrorMessage("Corrected value is required.");
      return;
    }
    if (!amendmentReason.trim()) {
      setErrorMessage("Reason for amendment is strictly required.");
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

      setSuccessMessage(
        "Amendment submitted and registered to the audit chain ledger.",
      );
      setTimeout(() => {
        navigate("/results/approvals");
      }, 1500);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to submit amendment.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600 mb-2" />
        <span className="text-sm font-medium">Loading baseline record...</span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Top Breadcrumb & Header */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <nav aria-label="Breadcrumb" className="flex items-center gap-2">
            <Link
              to="/results/approvals"
              className="hover:text-slate-900 transition-colors"
            >
              Approvals
            </Link>
            <span className="text-slate-400">/</span>
            <span className="text-slate-700">
              {detail?.test_name || "Diagnostic Test"}
            </span>
            <span className="text-slate-400">/</span>
            <span className="text-slate-900 font-semibold">Amend</span>
          </nav>
          <div className="flex items-center gap-2 bg-slate-100 px-3 py-1 rounded-full font-mono text-[11px] text-slate-700 border border-slate-200">
            <span>{detail?.accession_id}</span>
            <span>·</span>
            <span>Patient: {detail?.patient_name}</span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Amend result
            </h1>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
              ISO 15189 §5.9
            </span>
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-teal-700" />
            <span>Clinical Session Active</span>
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
                  Approved value — read-only
                </h2>
              </div>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-200 text-slate-700 px-2 py-0.5 rounded">
                Immutable Baseline
              </span>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                Assayed Analyte: {detail?.test_name}
              </span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-4xl font-extrabold font-mono text-slate-900">
                  {detail?.value}
                </span>
                <span className="text-base font-semibold text-slate-600">
                  {detail?.unit}
                </span>
                <span className="ml-auto inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-bold bg-red-100 text-red-800">
                  HIGH (CRITICAL)
                </span>
              </div>
            </div>

            {/* Telemetry card */}
            <div className="bg-white rounded-lg p-3.5 border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Sign-off Authority:</span>
                <span className="font-semibold text-slate-800">
                  Dr. Ayesha Khan (Pathologist)
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Timestamp:</span>
                <span className="font-mono text-slate-800">
                  20 Oct 2026, 10:12 PKT
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Specimen Matrix:</span>
                <span className="font-medium text-slate-800">
                  {detail?.specimen_type || "Serum (Gold top)"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Instrumentation:</span>
                <span className="font-medium text-slate-800">
                  {detail?.analyzer || "Roche Cobas c501"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 pt-4 border-t border-slate-200 text-xs text-slate-500 mt-6">
            <ShieldCheck className="w-4 h-4 text-teal-700 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              <strong className="text-slate-800">
                The original is never edited.
              </strong>{" "}
              Baseline accession records remain permanently sealed in compliance with ISO 15189 protocol and legal healthcare record audit mandates.
            </p>
          </div>
        </div>

        {/* Right Column: Correction Entry Form */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900">Correction</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Enter recalibrated parameter and verified clinical justification.
              </p>
            </div>

            {/* Corrected Value Input */}
            <div className="space-y-1">
              <label
                htmlFor="corrected-value-input"
                className="text-xs font-semibold text-slate-700 flex items-center justify-between"
              >
                <span>
                  Corrected value <span className="text-red-600">*</span>
                </span>
                <span className="text-[10px] text-slate-400">Required</span>
              </label>
              <div className="relative flex items-center">
                <input
                  id="corrected-value-input"
                  type="text"
                  aria-label="Corrected value"
                  value={correctedValue}
                  onChange={(e) => setCorrectedValue(e.target.value)}
                  placeholder="e.g. 5.9"
                  className="w-full text-base font-bold font-mono px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600 pr-16"
                  required
                />
                <span className="absolute right-3 font-semibold text-xs text-slate-500">
                  {detail?.unit || "mmol/L"}
                </span>
              </div>
              <div className="text-[11px] text-slate-500 pt-0.5 flex items-center gap-1">
                <Info className="w-3.5 h-3.5 text-slate-400" />
                <span>Biological reference range: {detail?.matched_range}</span>
              </div>
            </div>

            {/* Reason Textarea */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                <label htmlFor="amendment-reason-input">
                  Reason for amendment <span className="text-red-600">*</span>
                </label>
                <span className="text-[10px] font-mono text-slate-400">
                  {amendmentReason.length} / 250
                </span>
              </div>
              <textarea
                id="amendment-reason-input"
                aria-label="Reason for amendment"
                value={amendmentReason}
                onChange={(e) => setAmendmentReason(e.target.value)}
                placeholder="e.g. Sample rerun confirmed analyzer drift on electrode cell 3B."
                rows={3}
                maxLength={250}
                className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600"
                required
              />
              <span className="text-[10px] text-slate-400 block">
                Mandatory audit justification: This note is permanently appended to the cumulative clinical ledger.
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
                I certify that this result reflects a calibrated rerun validated under benchtop standard operating protocols.
              </label>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => navigate("/results/approvals")}
                className="px-4 py-2 border border-slate-300 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Submitting amendment...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Submit amendment</span>
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
              Amendment chain
            </h2>
            <p className="text-xs text-slate-500">
              Immutable chronological versioning audit log
            </p>
          </div>
          <span className="font-mono text-xs text-slate-400">
            Ledger Node: LIS-GUL-01
          </span>
        </div>

        <div className="space-y-4 relative pl-6 border-l-2 border-slate-200 ml-3">
          {/* Version 1.0 */}
          <div className="relative">
            <div className="absolute -left-[31px] top-1 w-5 h-5 rounded-full bg-teal-700 text-white flex items-center justify-center text-[10px] ring-4 ring-white">
              <Check className="w-3 h-3" />
            </div>
            <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 space-y-1 text-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-slate-900">
                    v1.0
                  </span>
                  <span>·</span>
                  <span className="font-semibold text-slate-900">
                    {detail?.value} {detail?.unit}
                  </span>
                  <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-[10px] font-semibold">
                    APPROVED
                  </span>
                </div>
                <span className="text-slate-400 text-[11px]">10:12 PKT</span>
              </div>
              <p className="text-slate-600 text-xs">
                Certified by Dr. Ayesha Khan. Initial urgent assay intake flagged for high potassium threshold.
              </p>
            </div>
          </div>

          {/* Version 2.0 (Active Correction) */}
          <div className="relative">
            <div className="absolute -left-[31px] top-1 w-5 h-5 rounded-full bg-amber-500 text-white flex items-center justify-center text-[10px] ring-4 ring-white">
              <Clock className="w-3 h-3" />
            </div>
            <div className="bg-amber-50/50 p-3.5 rounded-lg border border-amber-200 space-y-1 text-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-slate-900">
                    v2.0
                  </span>
                  <span>·</span>
                  <span className="font-semibold text-slate-900">
                    {correctedValue || "5.9"} {detail?.unit}
                  </span>
                  <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-[10px] font-semibold">
                    PENDING APPROVAL
                  </span>
                </div>
                <span className="text-slate-400 text-[11px]">Draft</span>
              </div>
              <p className="text-slate-600 text-xs">
                Reason: {amendmentReason || "Calibration rerun underway."}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
