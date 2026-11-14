/**
 * Screen 30: Exceptions Triage Screen (/exceptions).
 * Spec: Doc 03 §5.6, §6.7, 30-exceptions.html.
 * Icons: lucide-react exclusively. No emojis.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { statusLabel } from "../../lib/format";
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
import { messageForError } from "../../lib/errors";
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
  const { t } = useTranslation(["reports", "common"]);
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
      setErrorMessage(messageForError(err, (key) => t(`common:${key}`)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExceptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
              {t("reports:exceptions.title")}
            </h1>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                totalCount > 0
                  ? "bg-rose-50 text-rose-800 border border-rose-200"
                  : "bg-emerald-50 text-emerald-800 border border-emerald-200"
              }`}
            >
              {t("reports:exceptions.actionable", { count: totalCount })}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {t("reports:exceptions.subtitle")}
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
            {t("common:actions.refresh")}
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
          <span className="text-sm font-medium">
            {t("reports:exceptions.scanning")}
          </span>
        </div>
      ) : totalCount === 0 ? (
        /* Honest Empty State */
        <div className="flex flex-col items-center justify-center py-20 px-4 text-center bg-white rounded-2xl border border-slate-200 shadow-sm">
          <div className="w-14 h-14 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100">
            <CheckCircle2 className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">
            {t("reports:exceptions.empty_title")}
          </h2>
          <p className="text-sm text-slate-500 mt-1 max-w-md">
            {t("reports:exceptions.empty_body")}
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
                        {t("reports:exceptions.critical_title")}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-200 text-rose-900">
                        {criticalUnacknowledged.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {t("reports:exceptions.critical_subtitle")}
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
                        {t("reports:exceptions.patient")}:{" "}
                        <span className="font-medium text-slate-800">
                          {item.patient_name || t("common:labels.unknown")}
                        </span>{" "}
                        · MRN:{" "}
                        <bdi dir="ltr">
                          {getDetail(item.details, "patient_mrn")}
                        </bdi>
                      </div>
                    </div>
                    <Link
                      to={`/results/${getDetail(item.details, "result_id", item.reference_id)}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>{t("reports:exceptions.review_result")}</span>
                      <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
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
                        {t("reports:exceptions.failed_gen_title")}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-100 text-rose-800">
                        {failedGenerations.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {t("reports:exceptions.failed_gen_subtitle")}
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
                            t("reports:exceptions.generation_error"),
                          )}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        {t("reports:exceptions.patient")}:{" "}
                        {item.patient_name || "—"} ·{" "}
                        {t("reports:exceptions.branch")}:{" "}
                        {item.branch_name || t("reports:exceptions.main_lab")}
                      </div>
                    </div>
                    <Link
                      to={`/reports/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>{t("reports:exceptions.open_report")}</span>
                      <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
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
                        {t("reports:exceptions.failed_del_title")}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800">
                        {failedDeliveries.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {t("reports:exceptions.failed_del_subtitle")}
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
                          {getDetail(
                            item.details,
                            "contact",
                            t("reports:exceptions.no_destination"),
                          )}
                          )
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        {t("reports:exceptions.patient")}:{" "}
                        {item.patient_name || "—"} ·{" "}
                        {t("reports:exceptions.error_label")}:{" "}
                        <span className="text-rose-600 font-medium">
                          {getDetail(
                            item.details,
                            "last_error",
                            t("reports:exceptions.dispatch_failed"),
                          )}
                        </span>
                      </div>
                    </div>
                    <Link
                      to={`/reports/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>{t("reports:exceptions.retry_delivery")}</span>
                      <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
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
                        {t("reports:exceptions.late_title")}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800">
                        {lateTransfers.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {t("reports:exceptions.late_subtitle")}
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
                        {t("reports:exceptions.delay")}:{" "}
                        <span className="text-rose-600 font-semibold">
                          {t("reports:exceptions.hours_overdue", {
                            hours: getDetail(item.details, "hours_late", "0"),
                          })}
                        </span>{" "}
                        · {t("reports:exceptions.patient")}:{" "}
                        {item.patient_name || "—"}
                      </div>
                    </div>
                    <Link
                      to={`/samples/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>{t("reports:exceptions.track_sample")}</span>
                      <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
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
                        {t("reports:exceptions.stuck_title")}
                      </h2>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-200 text-slate-800">
                        {stuckSamples.length}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {t("reports:exceptions.stuck_subtitle")}
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
                          {t("common:labels.status")}:{" "}
                          {statusLabel(
                            "sample",
                            getDetail(
                              item.details,
                              "sample_status",
                              "pending",
                            ).toLowerCase(),
                            (key) => t(`common:${key}`),
                          )}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        {t("reports:exceptions.patient")}:{" "}
                        {item.patient_name || "—"} ·{" "}
                        {t("reports:exceptions.branch")}:{" "}
                        {item.branch_name || t("reports:exceptions.main_lab")}
                      </div>
                    </div>
                    <Link
                      to={`/samples/${item.reference_id}`}
                      className="inline-flex items-center gap-1 font-semibold text-teal-700 hover:text-teal-900 shrink-0"
                    >
                      <span>{t("reports:exceptions.open_sample")}</span>
                      <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
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
