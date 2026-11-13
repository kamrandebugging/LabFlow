/**
 * Results Management Service (Screens 21–25, Doc 03 §5.5, §6.6, KAN-150..KAN-153).
 * Interacts with backend apps/results/ using real endpoints:
 * - GET    /api/v1/samples/<sample_id>/results  (recorded rows for one sample)
 * - GET    /api/v1/results?status=entered       (approvals queue)
 * - GET    /api/v1/results/<result_id>          (result detail + audit trail)
 * - POST   /api/v1/samples/<sample_id>/results
 * - POST   /api/v1/results/<result_id>/approve
 * - POST   /api/v1/results/<result_id>/amend
 * - POST   /api/v1/results/<result_id>/withdraw
 * - POST   /api/v1/results/<result_id>/critical-notifications
 *
 * The worklist is derived from real GET /api/v1/samples/ rows. No value,
 * identity or timestamp is ever fabricated: fields the backend does not
 * supply stay null and the UI renders an honest empty state.
 */

import { apiRequest } from "../../lib/apiClient";
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
  ResultFlag,
  ResultRowInput,
  ResultStatus,
  WorklistItem,
} from "./types";

interface BackendAuditEntry {
  action: string;
  value?: string | null;
  status?: string | null;
  timestamp: string;
  actor_name?: string | null;
  note?: string | null;
  reason?: string | null;
}

interface BackendResultRow {
  id: string;
  sample_id: string;
  sample_status: string;
  accession_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  patient_sex?: string | null;
  patient_age_years?: number | null;
  branch_id: string;
  branch_name: string;
  test_id: string;
  test_name: string;
  test_code?: string;
  specimen_type?: string | null;
  value: string;
  unit?: string | null;
  flag: string | null;
  is_critical: boolean;
  status: string;
  matched_range: string;
  critical_threshold?: string | null;
  entered_by_id?: string;
  entered_by_name?: string | null;
  entered_at: string;
  amend_reason?: string | null;
  supersedes?: string | null;
  approved_by_name?: string | null;
  approved_at?: string | null;
  audit_history?: BackendAuditEntry[];
  critical_notification?: {
    notified_name: string;
    notified_at: string;
    read_back: boolean;
    recorded_by_name?: string | null;
  } | null;
}

interface ResultListResponse {
  results: BackendResultRow[];
}

const RESULT_FLAGS: ResultFlag[] = [
  "normal",
  "low",
  "high",
  "critical",
  "critical_low",
  "critical_high",
  "abnormal",
];

function normalizeFlag(value: string | null): ResultFlag | null {
  if (value && RESULT_FLAGS.includes(value as ResultFlag)) {
    return value as ResultFlag;
  }
  return null;
}

const RESULT_STATUSES: ResultStatus[] = [
  "entered",
  "approved",
  "rejected",
  "withdrawn",
  "amended",
];

function normalizeStatus(value: string): ResultStatus {
  if (RESULT_STATUSES.includes(value as ResultStatus)) {
    return value as ResultStatus;
  }
  throw new Error(`Unknown result status returned by the server: ${value}`);
}

function calculateWaitingDisplay(isoTimestamp?: string | null): string {
  if (!isoTimestamp) return "—";
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  if (Number.isNaN(diffMs) || diffMs <= 0) return "0m";
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function toApprovalQueueItem(row: BackendResultRow): ApprovalQueueItem {
  return {
    result_id: row.id,
    sample_id: row.sample_id,
    accession_id: row.accession_id,
    patient_id: row.patient_id,
    patient_name: row.patient_name,
    patient_mrn: row.patient_mrn,
    test_id: row.test_id,
    test_name: row.test_name,
    test_code: row.test_code,
    specimen_type: row.specimen_type ?? undefined,
    value: row.value,
    unit: row.unit ?? "",
    flag: normalizeFlag(row.flag),
    is_critical: row.is_critical,
    entered_by_name: row.entered_by_name ?? "",
    entered_at: row.entered_at,
    waiting_time: calculateWaitingDisplay(row.entered_at),
  };
}

function toResultDetail(row: BackendResultRow): ResultDetailRecord {
  return {
    id: row.id,
    sample_id: row.sample_id,
    accession_id: row.accession_id,
    patient_id: row.patient_id,
    patient_name: row.patient_name,
    patient_mrn: row.patient_mrn,
    patient_sex: row.patient_sex ?? undefined,
    patient_age_years: row.patient_age_years ?? undefined,
    test_id: row.test_id,
    test_name: row.test_name,
    test_code: row.test_code,
    specimen_type: row.specimen_type ?? undefined,
    value: row.value,
    unit: row.unit ?? "",
    flag: normalizeFlag(row.flag),
    is_critical: row.is_critical,
    status: normalizeStatus(row.status),
    matched_range: row.matched_range,
    critical_threshold: row.critical_threshold ?? undefined,
    entered_by_name: row.entered_by_name ?? "",
    entered_at: row.entered_at,
    approved_by_name: row.approved_by_name ?? undefined,
    approved_at: row.approved_at ?? undefined,
    amend_reason: row.amend_reason ?? undefined,
    supersedes: row.supersedes ?? undefined,
    audit_history: (row.audit_history ?? []).map((entry, index) => ({
      version: `v${index + 1}`,
      action: entry.action,
      value: entry.value ?? "",
      status: entry.status ?? entry.action,
      timestamp: entry.timestamp,
      actor_name: entry.actor_name ?? "",
      note: entry.note ?? undefined,
      reason: entry.reason ?? undefined,
    })),
    critical_notification: row.critical_notification
      ? {
          notified_name: row.critical_notification.notified_name,
          notified_at: row.critical_notification.notified_at,
          read_back: row.critical_notification.read_back,
        }
      : undefined,
  };
}

export const resultsService = {
  /**
   * Screen 22: Submit batch results for a sample (POST /api/v1/samples/<sample_id>/results).
   * Roles: Technician, Pathologist, Owner.
   */
  async submitResults(
    sampleId: string,
    results: ResultRowInput[],
  ): Promise<BatchResultEntryResponse> {
    return apiRequest<BatchResultEntryResponse>(
      `/samples/${sampleId}/results`,
      {
        method: "POST",
        body: { results },
      },
    );
  },

  /**
   * Recorded real result rows for one sample (GET /api/v1/samples/<sample_id>/results).
   */
  async getSampleResults(sampleId: string): Promise<ResultDetailRecord[]> {
    const data = await apiRequest<ResultListResponse>(
      `/samples/${sampleId}/results`,
    );
    return (data.results ?? []).map(toResultDetail);
  },

  /**
   * Screen 23 / 24: Pathologist/Owner approval/rejection (POST /api/v1/results/<result_id>/approve).
   * Roles: Pathologist, Owner.
   */
  async approveResult(
    resultId: string,
    input: ResultApprovalInput,
  ): Promise<ResultApprovalResponse> {
    return apiRequest<ResultApprovalResponse>(`/results/${resultId}/approve`, {
      method: "POST",
      body: {
        decision: input.decision,
        note: input.note?.trim() || undefined,
        range_override: Boolean(input.range_override),
        attestation: Boolean(input.attestation),
      },
    });
  },

  /**
   * Screen 25: Amend an approved result (POST /api/v1/results/<result_id>/amend).
   * Roles: Technician, Pathologist, Owner.
   */
  async amendResult(
    resultId: string,
    input: ResultAmendInput,
  ): Promise<ResultAmendResponse> {
    return apiRequest<ResultAmendResponse>(`/results/${resultId}/amend`, {
      method: "POST",
      body: {
        value: input.value.trim(),
        unit: input.unit?.trim() || undefined,
        reason: input.reason.trim(),
      },
    });
  },

  /**
   * Screen 24: Author withdrawal of entered result (POST /api/v1/results/<result_id>/withdraw).
   * Roles: Technician, Pathologist, Owner (author only).
   */
  async withdrawResult(
    resultId: string,
    reason?: string,
  ): Promise<{ id: string; status: "withdrawn" }> {
    return apiRequest<{ id: string; status: "withdrawn" }>(
      `/results/${resultId}/withdraw`,
      {
        method: "POST",
        body: reason ? { reason } : {},
      },
    );
  },

  /**
   * Screen 24: Critical notification audit record (POST /api/v1/results/<result_id>/critical-notifications).
   * Roles: Manager, Pathologist, Owner.
   */
  async recordCriticalNotification(
    resultId: string,
    input: CriticalNotificationInput,
  ): Promise<CriticalNotificationResponse> {
    return apiRequest<CriticalNotificationResponse>(
      `/results/${resultId}/critical-notifications`,
      {
        method: "POST",
        body: input,
      },
    );
  },

  /**
   * Screen 21: Technician Worklist.
   * Queries the four pending statuses server-side in oldest-first order, so a
   * busy lab's newest page can never hide an older pending accession. The
   * preview may still be capped per status, but the global oldest pending
   * rows are always included.
   */
  async getWorklist(options?: {
    branchId?: string;
    statusFilter?: string;
    demoMode?: boolean;
    signal?: AbortSignal;
  }): Promise<WorklistItem[]> {
    const statuses = ["collected", "received", "in_process", "rejected"];
    const pages = await Promise.all(
      statuses.map((status) =>
        sampleService.listSamples(
          {
            branch_id: options?.branchId,
            status,
            order: "oldest",
            limit: 100,
          },
          options?.signal,
        ),
      ),
    );

    const byId = new Map<string, SampleSummary>();
    for (const page of pages) {
      for (const sample of page.results) {
        byId.set(sample.id, sample);
      }
    }

    // Oldest collection first
    const sorted = [...byId.values()].sort((a, b) => {
      const timeA = a.collected_at ? new Date(a.collected_at).getTime() : 0;
      const timeB = b.collected_at ? new Date(b.collected_at).getTime() : 0;
      return timeA - timeB;
    });

    return sorted.map((s): WorklistItem => {
      let uiStatus: WorklistItem["status"] = "ready";
      if (s.status === "in_process") {
        uiStatus = "in_process";
      } else if (s.status === "rejected") {
        uiStatus = "rejected";
      }

      return {
        sample_id: s.id,
        sample_status: s.status,
        accession_id: s.accession_id,
        patient_id: s.patient_id,
        patient_name: s.patient_name,
        patient_mrn: s.patient_mrn,
        branch_id: s.branch_id,
        branch_name: s.branch_name,
        tests: s.tests || [],
        collected_at: s.collected_at,
        waiting_time: calculateWaitingDisplay(s.collected_at),
        status: uiStatus,
      };
    });
  },

  /**
   * Real result rows filtered by status (GET /api/v1/results?status=...).
   * Used by role dashboards for approved-result history and critical counts.
   */
  async listResults(
    status?: ResultStatus,
    signal?: AbortSignal,
  ): Promise<ResultDetailRecord[]> {
    const data = await apiRequest<ResultListResponse>("/results", {
      query: status ? { status } : {},
      signal,
    });
    return (data.results ?? []).map(toResultDetail);
  },

  /**
   * Screen 23: Pathologist / Owner Approvals Queue.
   * Reads real Result rows awaiting verification (GET /api/v1/results?status=entered).
   */
  async getApprovalsQueue(signal?: AbortSignal): Promise<ApprovalQueueItem[]> {
    const data = await apiRequest<ResultListResponse>("/results", {
      query: { status: "entered" },
      signal,
    });
    const rows = data.results ?? [];
    const items = rows.map(toApprovalQueueItem);

    // Critical first, then longest waiting
    return items.sort((a, b) => {
      if (a.is_critical && !b.is_critical) return -1;
      if (!a.is_critical && b.is_critical) return 1;
      return (
        new Date(a.entered_at).getTime() - new Date(b.entered_at).getTime()
      );
    });
  },

  /**
   * Screen 24: Result Detail Record from GET /api/v1/results/<result_id>.
   * Returns null only when the API reports the record does not exist.
   */
  async getResultDetail(resultId: string): Promise<ResultDetailRecord | null> {
    try {
      const row = await apiRequest<BackendResultRow>(`/results/${resultId}`);
      if (!row || !row.id) return null;
      return toResultDetail(row);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 404) return null;
      throw err;
    }
  },
};
