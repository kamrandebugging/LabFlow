/**
 * Screen 22: Result Entry (/results/entry/:sampleId).
 * Spec: Doc 03 §5.5 RS-1/RS-2/RS-3, 22-result-entry.html.
 * Roles: Technician, Pathologist only.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  User,
  FlaskConical,
  Clock,
  BadgeCheck,
  AlertCircle,
  Save,
  CheckCircle2,
  RefreshCw,
  ShieldAlert,
  ArrowLeft,
  Info,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { sampleService } from "../samples/sampleService";
import type { SampleDetail } from "../samples/types";
import { resultsService } from "./resultsService";
import type { ResultRowInput } from "./types";

interface TestParamEntry {
  id: string;
  name: string;
  category: string;
  unit: string;
  refLow: number | null;
  refHigh: number | null;
  rangeDisplay: string;
  value: string;
}

function parseBound(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  const num = Number(raw);
  return Number.isFinite(num) ? num : null;
}

function formatRangeDisplay(
  low: number | null,
  high: number | null,
  unit: string,
): string {
  if (low !== null && high !== null) {
    return `${low} – ${high} ${unit}`.trim();
  }
  if (low !== null) return `>= ${low} ${unit}`.trim();
  if (high !== null) return `<= ${high} ${unit}`.trim();
  return "No reference range configured";
}

export function ResultEntryScreen(): JSX.Element {
  const { sampleId } = useParams<{ sampleId: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);

  // Authorization check (Roles: Technician, Pathologist, Owner)
  const isAuthorized =
    user?.role === "technician" ||
    user?.role === "pathologist" ||
    user?.role === "owner";

  const [sample, setSample] = useState<SampleDetail | null>(null);
  const [params, setParams] = useState<TestParamEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!sampleId) return;

    async function loadData() {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await sampleService.getSample(sampleId!);
        setSample(data);

        // Build parameters strictly from the sample's real ordered tests.
        const entries: TestParamEntry[] = (data?.sample_tests ?? []).map(
          (st) => {
            const unit = st.unit ?? st.reference_range?.unit ?? "";
            const refLow = parseBound(st.reference_range?.low);
            const refHigh = parseBound(st.reference_range?.high);
            return {
              id: st.test_id,
              name: st.test_name || st.test_code,
              category: st.category || "",
              unit,
              refLow,
              refHigh,
              rangeDisplay: formatRangeDisplay(refLow, refHigh, unit),
              value: "",
            };
          },
        );

        setParams(entries);
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Failed to load specimen for result entry.",
        );
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [sampleId]);

  const handleValueChange = (id: string, val: string) => {
    setParams((prev) =>
      prev.map((p) => (p.id === id ? { ...p, value: val } : p)),
    );
  };

  const calculateFlag = (
    p: TestParamEntry,
  ): "low" | "high" | "normal" | null => {
    if (!p.value.trim()) return null;
    const num = parseFloat(p.value);
    if (isNaN(num)) return null;
    if (p.refLow !== null && num < p.refLow) return "low";
    if (p.refHigh !== null && num > p.refHigh) return "high";
    if (p.refLow === null && p.refHigh === null) return null;
    return "normal";
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Validation: All items must have non-empty values
    const emptyItem = params.find((p) => !p.value.trim());
    if (emptyItem) {
      setErrorMessage(
        "Please enter values for all ordered tests. Saving is all-or-nothing.",
      );
      return;
    }

    try {
      setSubmitting(true);
      const rows: ResultRowInput[] = params.map((p) => ({
        test_id: p.id,
        value: p.value.trim(),
        unit: p.unit,
      }));

      await resultsService.submitResults(sampleId!, rows);
      setSuccessMessage("Results successfully saved to laboratory ledger!");
      setTimeout(() => {
        navigate("/worklist");
      }, 1200);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Failed to submit laboratory results.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  // Role Denied View (403)
  if (!isAuthorized) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center space-y-4">
          <ShieldAlert className="w-12 h-12 text-red-600 mx-auto" />
          <h2 className="text-xl font-bold text-red-950">
            Access Denied · Role Restricted
          </h2>
          <p className="text-sm text-red-800 max-w-md mx-auto">
            Only Technician, Pathologist, or Owner may enter results. Your active role
            does not have authorization for direct laboratory entry.
          </p>
          <div className="pt-2">
            <Link
              to="/worklist"
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-red-300 text-red-800 rounded-lg text-sm font-semibold hover:bg-red-100 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Worklist</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600 mb-2" />
        <span className="text-sm font-medium">Loading specimen data...</span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Breadcrumb & Patient Header */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav
            aria-label="Breadcrumb"
            className="flex items-center gap-2 text-xs font-medium text-slate-500"
          >
            <Link
              to="/worklist"
              className="hover:text-slate-900 transition-colors"
            >
              Worklist
            </Link>
            <span className="text-slate-400">/</span>
            <span className="font-mono text-slate-900 font-semibold bg-slate-100 px-2 py-0.5 rounded">
              {sample?.accession_id || "—"}
            </span>
          </nav>

          <div className="flex items-center gap-2 bg-slate-50 px-3 py-1.5 rounded-full border border-slate-200 shadow-xs text-xs">
            <User className="w-4 h-4 text-teal-700" />
            <span className="font-semibold text-slate-900">
              {sample?.patient_name || "—"}
            </span>
            <span className="text-slate-300">·</span>
            <span className="text-slate-600">
              {sample?.patient_sex === "M"
                ? "Male"
                : sample?.patient_sex === "F"
                  ? "Female"
                  : "—"}
              ,{" "}
              {sample?.patient_age_years !== undefined
                ? `${sample.patient_age_years}y`
                : "—"}
            </span>
            <span className="text-slate-300">·</span>
            <span className="font-mono text-slate-500">
              {sample?.patient_mrn || "—"}
            </span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 pt-1">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Enter results
            </h1>
            <span className="text-xs font-bold uppercase tracking-wider text-teal-800 bg-teal-50 px-2 py-0.5 rounded border border-teal-200">
              Accession Active
            </span>
          </div>
          <div className="text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-xs flex items-center gap-1.5">
            <FlaskConical className="w-3.5 h-3.5 text-teal-700" />
            <span>
              Bench Station:{" "}
              <strong className="text-slate-900">
                {sample?.bench_code || "Not assigned"}
              </strong>
            </span>
          </div>
        </div>

        {/* Specimen Metadata Ribbon */}
        <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
              <FlaskConical className="w-4 h-4" />
            </div>
            <div>
              <div className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                Ordered Tests
              </div>
              <div className="font-medium text-slate-900">
                {sample?.tests?.length ? sample.tests.join(", ") : "—"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <div className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                Collection Timestamp
              </div>
              <div className="font-mono text-slate-900">
                {sample?.collected_at
                  ? new Date(sample.collected_at).toLocaleString([], {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })
                  : "—"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center shrink-0">
              <BadgeCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                Technician on Duty
              </div>
              <div className="font-medium text-slate-900">
                {user?.name || user?.email || "—"} ({user?.role})
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Success Banner */}
      {successMessage && (
        <div
          role="status"
          className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 text-sm flex items-center gap-3"
        >
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <span className="font-medium">{successMessage}</span>
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-900 text-sm flex items-center gap-3"
        >
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
          <span className="font-medium">{errorMessage}</span>
        </div>
      )}

      {/* Main Quantitative Parameter Entry Card */}
      <form onSubmit={handleSave} className="space-y-4">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          {/* Table Header Strip */}
          <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-900 text-sm">
                Ordered Quantitative Parameters
              </span>
              <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-mono font-semibold">
                {params.length} Tests
              </span>
            </div>
            <div className="text-slate-500 font-medium hidden sm:flex items-center gap-1">
              <Info className="w-3.5 h-3.5 text-slate-400" />
              <span>Double-check raw analyzer output prior to save</span>
            </div>
          </div>

          {/* Clinical Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50/50 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-100">
                  <th className="py-3 px-6" scope="col">
                    Test Parameter
                  </th>
                  <th className="py-3 px-4 w-64" scope="col">
                    Observed Value
                  </th>
                  <th className="py-3 px-4 w-32" scope="col">
                    Unit
                  </th>
                  <th className="py-3 px-6" scope="col">
                    Reference / Matched Range
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-sm text-slate-900">
                {params.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="py-10 px-6 text-center text-sm text-slate-500"
                    >
                      No ordered tests were found for this sample. Collect or
                      verify the sample before entering results.
                    </td>
                  </tr>
                )}
                {params.map((p) => {
                  const flag = calculateFlag(p);
                  return (
                    <tr
                      key={p.id}
                      className="hover:bg-slate-50/60 transition-colors"
                    >
                      <td className="py-4 px-6 align-middle">
                        <div className="font-semibold text-slate-900">
                          {p.name}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {p.category || "Uncategorized"}
                        </div>
                      </td>
                      <td className="py-4 px-4 align-middle">
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            aria-label={`${p.name} value`}
                            value={p.value}
                            onChange={(e) =>
                              handleValueChange(p.id, e.target.value)
                            }
                            placeholder={
                              p.refLow !== null && p.refHigh !== null
                                ? `e.g. ${((p.refLow + p.refHigh) / 2).toFixed(1)}`
                                : "Enter value"
                            }
                            className={`w-36 h-9 px-3 rounded-lg border font-mono text-sm focus:outline-none focus:ring-2 transition-all ${
                              flag === "high"
                                ? "border-red-400 bg-red-50/30 text-red-950 focus:ring-red-500"
                                : flag === "low"
                                  ? "border-blue-400 bg-blue-50/30 text-blue-950 focus:ring-blue-500"
                                  : "border-slate-300 bg-white text-slate-900 focus:ring-teal-600"
                            }`}
                          />
                          {/* Visual Live Flag Badge */}
                          {flag === "high" && (
                            <span className="text-[11px] font-bold text-red-700 bg-red-100 px-2 py-0.5 rounded uppercase">
                              High
                            </span>
                          )}
                          {flag === "low" && (
                            <span className="text-[11px] font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded uppercase">
                              Low
                            </span>
                          )}
                          {flag === "normal" && (
                            <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                              Normal
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-4 px-4 align-middle font-medium text-slate-600 text-sm">
                        {p.unit}
                      </td>
                      <td className="py-4 px-6 align-middle">
                        <div className="flex items-center gap-1.5 text-xs text-slate-500">
                          <span>Range:</span>
                          <span className="font-mono font-medium text-slate-800">
                            {p.rangeDisplay}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Subfooter */}
          <div className="px-6 py-2.5 bg-slate-50/50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <span>Direct LIS protocol entry</span>
            <span className="font-mono">PROTOCOL: ISO-15189</span>
          </div>
        </div>

        {/* Informational Policy Note */}
        <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
          <Info className="w-4 h-4 text-slate-400 shrink-0" />
          <span>
            Saving is all-or-nothing — one invalid row saves nothing. Values
            will transition specimen to &quot;in_process&quot;.
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => navigate("/worklist")}
            className="px-5 py-2.5 rounded-lg border border-slate-300 text-slate-700 text-sm font-semibold hover:bg-slate-50 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold shadow-sm transition-colors flex items-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {submitting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Saving results...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save results</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
