/**
 * TypeScript types for Results Management Suite (Screens 21–25).
 * Mirrors backend models and serializers in apps/results/.
 */

export type ResultFlag =
  "normal" | "low" | "high" | "critical_low" | "critical_high" | "abnormal";
export type ResultStatus =
  "entered" | "approved" | "rejected" | "withdrawn" | "amended";
export type ApprovalDecision = "approved" | "rejected";

export interface ReferenceRangeSummary {
  low: number | null;
  high: number | null;
  unit: string;
  critical_low?: number | null;
  critical_high?: number | null;
  textual_display?: string;
}

export interface ResultRowInput {
  test_id: string;
  value: string;
  unit?: string;
}

export interface BatchResultEntryInput {
  results: ResultRowInput[];
}

export interface EnteredResultItem {
  id: string;
  test_id: string;
  test_name?: string;
  test_code?: string;
  value: string;
  unit?: string;
  flag: ResultFlag;
  qualifier?: string;
  needs_review?: boolean;
  status: ResultStatus;
  matched_range?: string;
  entered_by?: string;
  entered_at?: string;
}

export interface BatchResultEntryResponse {
  sample_id: string;
  sample_status: string;
  results: EnteredResultItem[];
}

export interface ResultApprovalInput {
  decision: ApprovalDecision;
  note?: string;
  range_override?: boolean;
}

export interface ResultApprovalResponse {
  id: string;
  status: ResultStatus;
  decision: ApprovalDecision;
  note: string | null;
  range_override: boolean;
  approved_by: string;
  sample_ready?: boolean;
  amended_result_id?: string;
  report_version_requested?: boolean;
}

export interface ResultAmendInput {
  value: string;
  unit?: string;
  reason: string;
}

export interface ResultAmendResponse {
  id: string;
  test_id: string;
  value: string;
  unit?: string;
  flag: ResultFlag;
  qualifier?: string;
  needs_review?: boolean;
  status: ResultStatus;
  matched_range?: string;
  entered_by: string;
  supersedes: string;
  amend_reason: string;
}

export interface CriticalNotificationInput {
  notified_name: string;
  notified_at: string;
  read_back: boolean;
}

export interface CriticalNotificationResponse {
  id: string;
  result_id: string;
  notified_name: string;
  notified_at: string;
  read_back: boolean;
  recorded_by: string;
}

// UI Models for Worklist, Approvals, and Details
export interface WorklistItem {
  sample_id: string;
  sample_status?:
    | "collected"
    | "received"
    | "in_process"
    | "ready"
    | "rejected"
    | "cancelled";
  accession_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  branch_id?: string;
  branch_name?: string;
  tests: string[];
  collected_at: string;
  waiting_time: string;
  status: "ready" | "in_process" | "rejected";
  priority?: "routine" | "urgent" | "stat";
}

export interface ApprovalQueueItem {
  result_id: string;
  sample_id: string;
  accession_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  test_id: string;
  test_name: string;
  test_code?: string;
  specimen_type?: string;
  value: string;
  unit: string;
  flag: ResultFlag | null;
  is_critical: boolean;
  entered_by_name: string;
  entered_at: string;
  waiting_time: string;
  delta_alert?: string;
  previous_value?: string;
}

export interface ResultDetailRecord {
  id: string;
  sample_id: string;
  accession_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  patient_sex?: string;
  patient_age_years?: number;
  test_id: string;
  test_name: string;
  test_code?: string;
  method?: string;
  specimen_type?: string;
  analyzer?: string;
  value: string;
  unit: string;
  flag: ResultFlag | null;
  is_critical: boolean;
  status: ResultStatus;
  matched_range: string;
  critical_threshold?: string;
  entered_by_name: string;
  entered_at: string;
  approved_by_name?: string;
  approved_at?: string;
  amend_reason?: string;
  supersedes?: string;
  previous_value?: string;
  previous_date?: string;
  shift_rate?: string;
  delta_note?: string;
  audit_history?: Array<{
    version: string;
    action?: string;
    value: string;
    unit?: string;
    status: string;
    timestamp: string;
    actor_name: string;
    note?: string;
    reason?: string;
  }>;
  critical_notification?: {
    notified_name: string;
    notified_at: string;
    read_back: boolean;
    recipient_role?: string;
  };
}
