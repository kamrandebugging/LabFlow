/**
 * Screen 23: Approvals Queue (/results/approvals).
 * Spec: Doc 03 §5.5 RS-4–RS-10, §6.6, 23-approvals-queue.html.
 * Roles: Pathologist only.
 * Icons: lucide-react exclusively.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  RefreshCw,
  AlertCircle,
  X,
  FileCheck,
  ShieldAlert,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { resultsService } from "./resultsService";
import type { ApprovalQueueItem } from "./types";

export function ApprovalsQueueScreen(): JSX.Element {
  const user = useAuthStore((state) => state.user);
  const isPathologist = user?.role === "pathologist";

  const [queue, setQueue] = useState<ApprovalQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<
    string | null
  >(null);

  // Reject Modal State
  const [rejectingItem, setRejectingItem] = useState<ApprovalQueueItem | null>(
    null,
  );
  const [rejectionNote, setRejectionNote] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [processingAction, setProcessingAction] = useState(false);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (successTimerRef.current) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const data = await resultsService.getApprovalsQueue();
      setQueue(data);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load approvals queue.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleQuickApprove = async (item: ApprovalQueueItem) => {
    try {
      setProcessingAction(true);
      setErrorMessage(null);
      await resultsService.approveResult(item.result_id, {
        decision: "approved",
      });

      // Update UI state only after 2xx response
      setQueue((prev) => prev.filter((q) => q.result_id !== item.result_id));
      setActionSuccessMessage(
        `Result for ${item.patient_name} (${item.test_name}) approved.`,
      );
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      successTimerRef.current = setTimeout(
        () => setActionSuccessMessage(null),
        4000,
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to approve result.",
      );
    } finally {
      setProcessingAction(false);
    }
  };

  const handleConfirmReject = async () => {
    if (!rejectingItem) return;
    if (!rejectionNote.trim()) {
      setRejectError(
        "A clinical reason note is strictly required for rejection.",
      );
      return;
    }

    try {
      setProcessingAction(true);
      setRejectError(null);
      await resultsService.approveResult(rejectingItem.result_id, {
        decision: "rejected",
        note: rejectionNote.trim(),
      });

      // Update UI state only after 2xx response
      setQueue((prev) =>
        prev.filter((q) => q.result_id !== rejectingItem.result_id),
      );
      setActionSuccessMessage(
        `Result for ${rejectingItem.patient_name} (${rejectingItem.test_name}) rejected. Sample recollect requested.`,
      );
      setRejectingItem(null);
      setRejectionNote("");
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      successTimerRef.current = setTimeout(
        () => setActionSuccessMessage(null),
        4000,
      );
    } catch (err) {
      setRejectError(
        err instanceof Error ? err.message : "Failed to reject result.",
      );
    } finally {
      setProcessingAction(false);
    }
  };

  // Role restriction view: Pathologist only
  if (!isPathologist) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center space-y-4">
          <ShieldAlert className="w-12 h-12 text-red-600 mx-auto" />
          <h2 className="text-xl font-bold text-red-950">
            Access Denied · Pathologist Desk Restricted
          </h2>
          <p className="text-sm text-red-800 max-w-md mx-auto">
            Only a registered Pathologist may access the clinical verification
            and approvals queue (Doc 03 §6.6).
          </p>
          <div className="pt-2">
            <Link
              to="/worklist"
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-red-300 text-red-800 rounded-lg text-sm font-semibold hover:bg-red-100 transition-colors"
            >
              <span>Go to Worklist</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const criticalCount = queue.filter((q) => q.is_critical).length;
  const standardCount = queue.length - criticalCount;

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Top Context Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-slate-500 text-xs uppercase tracking-wider font-semibold mb-1">
            <span className="w-2 h-2 rounded-full bg-red-600 animate-pulse" />
            <span>Clinical Verification · Pathologist Desk</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Approvals queue
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Entered results awaiting your decision · Critical first · Times are
            PKT
          </p>
        </div>

        {/* Quick Stats Bar */}
        <div className="flex items-center gap-3 bg-white p-2 rounded-xl border border-slate-200 shadow-xs">
          <div className="px-3 py-1.5 rounded-lg bg-red-50 border border-red-100 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            <div>
              <div className="text-xs font-bold text-red-800 uppercase">
                {criticalCount} Critical
              </div>
              <div className="text-[10px] text-red-600 font-mono">
                TAT &gt; 2h
              </div>
            </div>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center gap-2">
            <FileCheck className="w-4 h-4 text-teal-700" />
            <div>
              <div className="text-xs font-bold text-slate-800 uppercase">
                {standardCount} Standard
              </div>
              <div className="text-[10px] text-slate-500 font-mono">
                In batch
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Critical Banner */}
      {criticalCount > 0 && (
        <div className="bg-red-50/70 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-4 shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-red-100 text-red-600 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-red-900">
                {criticalCount} critical results need immediate clinical
                sign-off.
              </p>
              <p className="text-xs text-red-700 mt-0.5">
                Per CAP/ISO 15189 protocol, critical alerts require verified
                telephonic/portal notification within 30 minutes of entry.
              </p>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-bold text-red-700 uppercase tracking-wider bg-white px-2.5 py-1 rounded border border-red-200">
            Priority Escalated
          </span>
        </div>
      )}

      {/* Action Feedback Banners */}
      {actionSuccessMessage && (
        <div
          role="status"
          className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 text-xs flex items-center gap-2"
        >
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span className="font-semibold">{actionSuccessMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-900 text-xs flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span className="font-semibold">{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={loadData}
            className="px-2.5 py-1 bg-red-100 text-red-900 rounded font-semibold text-xs hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Approvals Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        {/* Card Header Strip */}
        <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-900 text-sm">
              Specimens for Sign-off
            </span>
            <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-mono font-semibold">
              {queue.length} items pending
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadData}
              className="px-3 py-1 bg-white border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Table Body */}
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-slate-500">
            <RefreshCw className="w-6 h-6 animate-spin text-teal-600 mb-2" />
            <span className="text-xs font-medium">
              Loading pending sign-offs...
            </span>
          </div>
        ) : queue.length === 0 ? (
          <div className="py-20 text-center text-slate-500 text-sm">
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500 mb-2" />
            <p className="font-semibold text-slate-800">
              Approvals queue is clear!
            </p>
            <p className="text-xs text-slate-400 mt-1">
              No results currently pending pathologist verification.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50/50 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-100">
                  <th className="py-3 px-6" scope="col">
                    Priority
                  </th>
                  <th className="py-3 px-4" scope="col">
                    Patient
                  </th>
                  <th className="py-3 px-4" scope="col">
                    Test
                  </th>
                  <th className="py-3 px-4" scope="col">
                    Value &amp; Flag
                  </th>
                  <th className="py-3 px-4" scope="col">
                    Entered By
                  </th>
                  <th className="py-3 px-4" scope="col">
                    Waiting
                  </th>
                  <th className="py-3 px-6 text-right" scope="col">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-sm text-slate-900">
                {queue.map((item) => (
                  <tr
                    key={item.result_id}
                    className="hover:bg-slate-50/70 transition-colors"
                  >
                    <td className="py-4 px-6 whitespace-nowrap">
                      {item.is_critical ? (
                        <span className="bg-red-100 text-red-800 font-bold text-[11px] px-2.5 py-0.5 rounded-full inline-flex items-center gap-1.5 shadow-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-ping" />
                          CRITICAL
                        </span>
                      ) : (
                        <span className="bg-slate-100 text-slate-600 font-semibold text-[11px] px-2.5 py-0.5 rounded-full inline-flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                          entered
                        </span>
                      )}
                    </td>
                    <td className="py-4 px-4">
                      <div className="font-semibold text-slate-900">
                        {item.patient_name}
                      </div>
                      <div className="text-xs font-mono text-slate-400">
                        {item.patient_mrn}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div className="font-medium text-slate-900">
                        {item.test_name}
                      </div>
                      <div className="text-xs text-slate-400">
                        {item.specimen_type || "Specimen"}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div className="flex flex-col gap-1">
                        <div
                          className={`inline-flex items-center gap-1 font-mono text-xs font-bold px-2 py-0.5 rounded w-fit ${
                            item.is_critical
                              ? "bg-red-50 text-red-700 border border-red-200"
                              : "bg-slate-100 text-slate-800"
                          }`}
                        >
                          <span>
                            {item.value} {item.unit}
                          </span>
                          {item.flag === "critical_high" && <span>— high</span>}
                          {item.flag === "critical_low" && <span>— low</span>}
                        </div>
                        {item.delta_alert && (
                          <span className="text-[10px] font-semibold text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded w-fit border border-amber-200">
                            {item.delta_alert}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-4 px-4 text-xs text-slate-600 whitespace-nowrap">
                      {item.entered_by_name}
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap">
                      <span
                        className={`font-mono text-xs font-semibold flex items-center gap-1 ${
                          item.is_critical ? "text-red-700" : "text-slate-600"
                        }`}
                      >
                        <Clock className="w-3.5 h-3.5" />
                        <span>{item.waiting_time}</span>
                      </span>
                    </td>
                    <td className="py-4 px-6 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => handleQuickApprove(item)}
                          disabled={processingAction}
                          className="px-2.5 py-1.5 bg-teal-50 hover:bg-teal-100 text-teal-800 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                        >
                          Quick Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRejectingItem(item);
                            setRejectionNote("");
                            setRejectError(null);
                          }}
                          disabled={processingAction}
                          className="px-2.5 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                        >
                          Reject
                        </button>
                        <Link
                          to={`/results/${item.result_id}`}
                          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                          title="Full diagnostic review"
                        >
                          <ArrowRight className="w-4 h-4" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Reject Modal */}
      {rejectingItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-red-600" />
                <span>Rejection Note Required</span>
              </h2>
              <button
                type="button"
                onClick={() => setRejectingItem(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-600">
              Rejecting result for <strong>{rejectingItem.patient_name}</strong>{" "}
              ({rejectingItem.test_name}). Please document the explicit clinical
              justification:
            </p>

            {rejectError && (
              <div className="p-2.5 bg-red-50 text-red-800 text-xs rounded-lg border border-red-200">
                {rejectError}
              </div>
            )}

            <div>
              <textarea
                value={rejectionNote}
                onChange={(e) => setRejectionNote(e.target.value)}
                placeholder="Enter clinical reason for rejection (e.g. Specimen clotted, hemolysis index exceeded, delta mismatch)..."
                rows={3}
                maxLength={2000}
                className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setRejectingItem(null)}
                className="px-4 py-2 border border-slate-300 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmReject}
                disabled={processingAction}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 cursor-pointer"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
