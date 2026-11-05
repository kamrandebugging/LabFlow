/**
 * Screen 30: Exceptions Triage Screen (/exceptions).
 * Spec: Doc 03 §5.6, §6.7, 30-exceptions.html.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Clock,
  ArrowRight,
  RefreshCw,
  CheckCircle2,
  Send,
  FileText,
  Truck,
  Activity,
  X,
} from "lucide-react";
import { reportsService } from "./reportsService";
import type { ExceptionsResponse } from "./types";

function getDetail(
  details: Record<string, unknown>,
  key: string,
  fallback = "—",
): string {
  const val = details[key];
  if (val === null || val === undefined || val === "") return fallback;
  return String(val);
}

export function ExceptionsScreen(): JSX.Element {
  const [data, setData] = useState<ExceptionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchExceptions = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const res = await reportsService.getExceptions();
      setData(res);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Failed to load clinical exceptions.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExceptions();
  }, []);

  const totalCount = data?.counts.total || 0;

  const lateTransfers =
    data?.results.filter((item) => item.kind === "late_transfer") || [];
  const failedGenerations =
    data?.results.filter((item) => item.kind === "failed_generation") || [];
  const failedDeliveries =
    data?.results.filter((item) => item.kind === "failed_delivery") || [];
  const criticalUnacknowledged =
    data?.results.filter((item) => item.kind === "critical_unacknowledged") ||
    [];
  const stuckSamples =
    data?.results.filter((item) => item.kind === "stuck_sample") || [];

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 gap-6">
      {/* Top Header & Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Exceptions
            </h1>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                totalCount > 0
                  ? "bg-rose-50 text-rose-800 border border-rose-200"
                  : "bg-emerald-50 text-emerald-800 border border-emerald-200"
              }`}
            >
              {totalCount} Actionable
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Clinical workflows requiring manual staff attention or triage.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchExceptions}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Banner */}
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

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
          <span className="text-sm font-medium">Scanning for exceptions…</span>
        </div>
      ) : totalCount === 0 ? (
        /* Honest Empty State */
        <div className="flex flex-col items-center justify-center py-20 px-4 text-center bg-white rounded-2xl border border-slate-200 shadow-sm">
          <div className="w-14 h-14 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100">
            <CheckCircle2 className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">
            No active exceptions
          </h2>
          <p className="text-sm text-slate-500 mt-1 max-w-md">
            All clinical transfers, report generations, deliveries, and critical
            notifications are operating within target SLAs.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* 1. Critical Results Unacknowledged */}
          {criticalUnacknowledged.length > 0 && (
            <div className="bg-white rounded-xl border border-rose-200 shadow-sm overflow-hidden">
              <div className="p-4 sm:p-5 flex items-center justify-between gap-3 bg-rose-50/60 border-b border-rose-100">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center">
                    <Activity className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-slate-900">
                        Critical Results Unacknowledged
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-200 text-rose-900">
                        {criticalUnacknowledged.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Approved critical results pending physician notification
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-slate-100 text-xs">
                {criticalUnacknowledged.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-rose-700">
                          {item.title}
                        </span>
                        <span className="font-mono text-slate-500">
                          ({item.reference_code})
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        Patient:{" "}
                        <span className="font-medium text-slate-800">
                          {item.patient_name || "Unknown"}
                        </span>{" "}
                        · MRN: {getDetail(item.details, "patient_mrn")}
                      </div>
                    </div>
                    <Link
                      to={`/results/${getDetail(item.details, "result_id", item.reference_id)}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>Review result</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. Failed Generations */}
          {failedGenerations.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 sm:p-5 flex items-center justify-between gap-3 bg-slate-50 border-b border-slate-200">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-slate-900">
                        Failed PDF Generations
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-100 text-rose-800">
                        {failedGenerations.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      WeasyPrint or rendering task errors requiring regeneration
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-slate-100 text-xs">
                {failedGenerations.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-slate-900">
                          {item.reference_code}
                        </span>
                        <span className="text-rose-600 font-medium">
                          {getDetail(
                            item.details,
                            "generation_error",
                            "Generation error",
                          )}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        Patient: {item.patient_name || "—"} · Branch:{" "}
                        {item.branch_name || "Main Lab"}
                      </div>
                    </div>
                    <Link
                      to={`/reports/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>Open report</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 3. Failed Deliveries */}
          {failedDeliveries.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 sm:p-5 flex items-center justify-between gap-3 bg-slate-50 border-b border-slate-200">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center">
                    <Send className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-slate-900">
                        Failed Deliveries
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800">
                        {failedDeliveries.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      WhatsApp or Email dispatches bounced or unroutable
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-slate-100 text-xs">
                {failedDeliveries.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900">
                          {item.title}
                        </span>
                        <span className="font-mono text-slate-500">
                          (
                          {getDetail(item.details, "contact", "No destination")}
                          )
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        Patient: {item.patient_name || "—"} · Error:{" "}
                        <span className="text-rose-600 font-medium">
                          {getDetail(
                            item.details,
                            "last_error",
                            "Dispatch failed",
                          )}
                        </span>
                      </div>
                    </div>
                    <Link
                      to={`/reports/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>Retry delivery</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 4. Late Transfers */}
          {lateTransfers.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 sm:p-5 flex items-center justify-between gap-3 bg-slate-50 border-b border-slate-200">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center">
                    <Truck className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-slate-900">
                        Late Specimen Transfers
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800">
                        {lateTransfers.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Inter-branch transit exceeding 2 hour SLA threshold
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-slate-100 text-xs">
                {lateTransfers.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-slate-900">
                          {item.reference_code}
                        </span>
                        <span className="text-amber-700 font-medium">
                          {item.title}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        Delay:{" "}
                        <span className="text-rose-600 font-semibold">
                          {getDetail(item.details, "hours_late", "0")}h overdue
                        </span>{" "}
                        · Patient: {item.patient_name || "—"}
                      </div>
                    </div>
                    <Link
                      to={`/samples/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>Track sample</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 5. Stuck Samples */}
          {stuckSamples.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 sm:p-5 flex items-center justify-between gap-3 bg-slate-50 border-b border-slate-200">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center">
                    <Clock className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-slate-900">
                        Stuck Samples
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-200 text-slate-800">
                        {stuckSamples.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Samples without movement or results for &gt; 4 hours
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-slate-100 text-xs">
                {stuckSamples.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-slate-900">
                          {item.reference_code}
                        </span>
                        <span className="text-slate-600 capitalize">
                          Status:{" "}
                          {getDetail(item.details, "sample_status", "pending")}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        Patient: {item.patient_name || "—"} · Branch:{" "}
                        {item.branch_name || "Main Lab"}
                      </div>
                    </div>
                    <Link
                      to={`/samples/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>Open sample</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
