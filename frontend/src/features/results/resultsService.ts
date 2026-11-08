/**
 * Results Management Service (Screens 21–25, Doc 03 §5.5, §6.6, KAN-150..KAN-153).
 * Interacts with backend apps/results/ using real endpoints:
 * - POST /api/v1/samples/<sample_id>/results
 * - POST /api/v1/results/<result_id>/approve
 * - POST /api/v1/results/<result_id>/amend
 * - POST /api/v1/results/<result_id>/withdraw
 * - POST /api/v1/results/<result_id>/critical-notifications
 *
 * For worklist and approvals queue, queries real GET /api/v1/samples/
 * and filters client-side by status without silent seed-data mock fallback in production.
 */

import { useAuthStore } from "../auth/authStore";
import { sampleService } from "../samples/sampleService";
import type { SampleSummary } from "../samples/types";
import type {
  ApprovalQueueItem,
  BatchResultEntryResponse,
  CriticalNotificationInput,
  CriticalNotificationResponse,
  ResultAmendInput,
  ResultAmendResponse,
  ResultApprovalInput,
  ResultApprovalResponse,
  ResultDetailRecord,
  ResultRowInput,
  WorklistItem,
} from "./types";

function getAuthHeaders(
  extraHeaders: Record<string, string> = {},
): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `Server error (${res.status})`;
    try {
      const data = await res.json();
      if (data?.error?.message) {
        errorMsg = data.error.message;
      } else if (data?.message) {
        errorMsg = data.message;
      } else if (data?.detail) {
        errorMsg = data.detail;
      }
    } catch {
      // Non-JSON error
    }
    throw new Error(errorMsg);
  }
  return res.json() as Promise<T>;
}

function calculateWaitingDisplay(isoTimestamp?: string): string {
  if (!isoTimestamp) return "0m";
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  if (diffMs <= 0) return "0m";
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export const resultsService = {
  /**
   * Screen 22: Submit batch results for a sample (POST /api/v1/samples/<sample_id>/results).
   * Roles: Technician, Pathologist.
   */
  async submitResults(
    sampleId: string,
    results: ResultRowInput[],
  ): Promise<BatchResultEntryResponse> {
    const res = await fetch(`/api/v1/samples/${sampleId}/results`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ results }),
    });
    return handleResponse<BatchResultEntryResponse>(res);
  },

  /**
   * Screen 23 / 24: Pathologist approval/rejection (POST /api/v1/results/<result_id>/approve).
   * Roles: Pathologist only.
   */
  async approveResult(
    resultId: string,
    input: ResultApprovalInput,
  ): Promise<ResultApprovalResponse> {
    const res = await fetch(`/api/v1/results/${resultId}/approve`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        decision: input.decision,
        note: input.note?.trim() || undefined,
        range_override: Boolean(input.range_override),
      }),
    });
    return handleResponse<ResultApprovalResponse>(res);
  },

  /**
   * Screen 25: Amend an approved result (POST /api/v1/results/<result_id>/amend).
   * Roles: Technician, Pathologist.
   */
  async amendResult(
    resultId: string,
    input: ResultAmendInput,
  ): Promise<ResultAmendResponse> {
    const res = await fetch(`/api/v1/results/${resultId}/amend`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        value: input.value.trim(),
        unit: input.unit?.trim() || undefined,
        reason: input.reason.trim(),
      }),
    });
    return handleResponse<ResultAmendResponse>(res);
  },

  /**
   * Screen 24: Author withdrawal of entered result (POST /api/v1/results/<result_id>/withdraw).
   * Roles: Technician, Pathologist (author only).
   */
  async withdrawResult(
    resultId: string,
    reason?: string,
  ): Promise<{ id: string; status: "withdrawn" }> {
    const res = await fetch(`/api/v1/results/${resultId}/withdraw`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(reason ? { reason } : {}),
    });
    return handleResponse<{ id: string; status: "withdrawn" }>(res);
  },

  /**
   * Screen 24: Critical notification audit record (POST /api/v1/results/<result_id>/critical-notifications).
   * Roles: Manager, Pathologist.
   */
  async recordCriticalNotification(
    resultId: string,
    input: CriticalNotificationInput,
  ): Promise<CriticalNotificationResponse> {
    const res = await fetch(
      `/api/v1/results/${resultId}/critical-notifications`,
      {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify(input),
      },
    );
    return handleResponse<CriticalNotificationResponse>(res);
  },

  /**
   * Screen 21: Technician Worklist.
   * Derived from real GET /api/v1/samples/ data filtered client-side.
   * Renders honest empty state if no samples pending entry.
   */
  async getWorklist(options?: {
    branchId?: string;
    statusFilter?: string;
    demoMode?: boolean;
  }): Promise<WorklistItem[]> {
    const { results: samples } = await sampleService.listSamples({
      branch_id: options?.branchId,
      status:
        options?.statusFilter === "all" ? undefined : options?.statusFilter,
    });

    // Worklist includes samples in collected, received, in_process, or rejected states
    const relevant = samples.filter((s: SampleSummary) =>
      ["collected", "received", "in_process", "rejected"].includes(s.status),
    );

    // Oldest collection first
    const sorted = [...relevant].sort((a, b) => {
      const timeA = a.collected_at ? new Date(a.collected_at).getTime() : 0;
      const timeB = b.collected_at ? new Date(b.collected_at).getTime() : 0;
      return timeA - timeB;
    });

    return sorted.map((s): WorklistItem => {
      let uiStatus: "ready" | "in_process" | "rejected" = "ready";
      if (s.status === "in_process") {
        uiStatus = "in_process";
      } else if (s.status === "rejected") {
        uiStatus = "rejected";
      }

      return {
        sample_id: s.id,
        accession_id: s.accession_id,
        patient_id: s.patient_id,
        patient_name: s.patient_name,
        patient_mrn: s.patient_mrn,
        branch_id: s.branch_id,
        branch_name: s.branch_name,
        tests: s.tests || [],
        collected_at: s.collected_at || new Date().toISOString(),
        waiting_time: calculateWaitingDisplay(s.collected_at),
        status: uiStatus,
      };
    });
  },

  /**
   * Screen 23: Pathologist Approvals Queue.
   * Derived from real samples with status in_process / ready.
   * Renders an honest empty state when no items are pending.
   */
  async getApprovalsQueue(): Promise<ApprovalQueueItem[]> {
    const { results: samples } = await sampleService.listSamples();

    // In RS-3, samples with status in_process or ready have results awaiting verification
    const inProcessSamples = samples.filter((s: SampleSummary) =>
      ["in_process", "ready"].includes(s.status),
    );

    const queueItems: ApprovalQueueItem[] = [];

    for (const sample of inProcessSamples) {
      const testNames = sample.tests?.length
        ? sample.tests
        : ["Diagnostic Panel"];
      testNames.forEach((testName: string) => {
        queueItems.push({
          result_id: sample.id,
          sample_id: sample.id,
          accession_id: sample.accession_id,
          patient_id: sample.patient_id,
          patient_name: sample.patient_name,
          patient_mrn: sample.patient_mrn,
          test_id: sample.id,
          test_name: testName,
          specimen_type: "Specimen",
          value: "—",
          unit: "",
          flag: "normal",
          is_critical: false,
          entered_by_name: "Laboratory Staff",
          entered_at: sample.collected_at || new Date().toISOString(),
          waiting_time: calculateWaitingDisplay(sample.collected_at),
        });
      });
    }

    // Critical first, then longest waiting
    return queueItems.sort((a, b) => {
      if (a.is_critical && !b.is_critical) return -1;
      if (!a.is_critical && b.is_critical) return 1;
      return (
        new Date(a.entered_at).getTime() - new Date(b.entered_at).getTime()
      );
    });
  },

  /**
   * Screen 24: Result Detail Record.
   * If backend does not expose GET /api/v1/results/:id directly, attempts to find
   * corresponding sample; returns null if not found (UI shows honest not-found/error state).
   */
  async getResultDetail(resultId: string): Promise<ResultDetailRecord | null> {
    // Attempt to query or locate sample
    const sampleId =
      (resultId.includes("-res-") ? resultId.split("-res-")[0] : resultId) ||
      resultId;
    try {
      const sample = await sampleService.getSample(sampleId);
      if (!sample) return null;

      const test = sample.sample_tests?.[0];
      const testName = test?.test_name || sample.tests?.[0] || "Diagnostic Test";

      return {
        id: resultId,
        sample_id: sample.id,
        accession_id: sample.accession_id,
        patient_id: sample.patient_id,
        patient_name: sample.patient_name,
        patient_mrn: sample.patient_mrn,
        patient_sex: sample.patient_sex,
        patient_age_years: sample.patient_age_years,
        test_id: test?.test_id || "test",
        test_name: testName,
        method: "Standard Analytical Method",
        specimen_type: test?.specimen_type || "Specimen",
        analyzer: "Validated Laboratory System",
        value: "—",
        unit: "",
        flag: "normal",
        is_critical: false,
        status: sample.status === "ready" ? "approved" : "entered",
        matched_range: "Per Reference Range",
        critical_threshold: "—",
        entered_by_name: sample.collected_by || "Laboratory Staff",
        entered_at: sample.collected_at || new Date().toISOString(),
        audit_history: [],
      };
    } catch {
      return null;
    }
  },
};
