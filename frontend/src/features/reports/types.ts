/**
 * Clinical Reports & Exceptions Type Definitions (Screens 26–30).
 * Aligned with backend apps/reports/ (Doc 03 §5.6, §6.1, §6.7, §6.8).
 */

export type ReportStatus = "draft" | "final" | "amended" | "void";

export type ReportGenerationStatus =
  "idle" | "running" | "failed" | "completed";

export type DeliveryChannel = "email" | "whatsapp";

export type DeliveryStatus =
  "pending" | "sent" | "delivered" | "failed" | "bounced" | "opened";

export interface ReportTestSummary {
  id: string;
  name: string;
  code: string;
}

export interface ReportPatientSummary {
  id: string;
  name: string;
  mrn: string;
  age_years?: number | null;
  gender?: string | null;
  phone?: string | null;
  email?: string | null;
}

export interface ReportBranchSummary {
  id: string;
  name: string;
  code?: string;
}

export interface ReportSummaryItem {
  id: string;
  status: ReportStatus;
  generation_status: ReportGenerationStatus;
  generation_error: string | null;
  current_version: number;
  published_at: string | null;
  created_at: string;
  sample: {
    id: string;
    accession_id: string;
    collected_at: string | null;
    branch: ReportBranchSummary | null;
    patient: ReportPatientSummary;
    tests: ReportTestSummary[];
  };
  latest_delivery: {
    channel: DeliveryChannel;
    status: DeliveryStatus;
    sent_at: string | null;
  } | null;
}

export interface ReportListResponse {
  results: ReportSummaryItem[];
  next_cursor: string | null;
}

export interface ReportListFilters {
  status?: string;
  branch?: string;
  q?: string;
  patient?: string;
  created_after?: string;
  created_before?: string;
  cursor?: string;
  limit?: number;
}

export interface ReportResultItem {
  id: string;
  test_name: string;
  test_code: string;
  value: string;
  unit: string;
  flag: string;
  status: string;
  amend_reason: string | null;
}

export interface ReportVersionItem {
  id: string;
  version: number;
  pdf_key: string | null;
  generated_by_id: string | null;
  generated_by_email: string | null;
  created_at: string;
}

export interface ReportDeliveryItem {
  id: string;
  channel: DeliveryChannel;
  status: DeliveryStatus;
  contact_id: string;
  contact_value: string | null;
  contact_type: string | null;
  contact_kind: string | null;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface ReportAccessTokenState {
  id: string;
  expires_at: string;
  revoked_at: string | null;
  is_active: boolean;
}

export interface ReportPatientContact {
  id: string;
  kind: string;
  value: string;
  is_primary: boolean;
}

export interface ReportDetail {
  id: string;
  status: ReportStatus;
  generation_status: ReportGenerationStatus;
  generation_error: string | null;
  current_version: number;
  published_at: string | null;
  finalised_at?: string | null;
  created_at: string;
  updated_at: string;
  sample: {
    id: string;
    accession_id: string;
    status: string;
    collected_at: string | null;
    branch: ReportBranchSummary | null;
  };
  patient: {
    id: string;
    full_name: string;
    name?: string;
    mrn: string;
    age_years: number | null;
    gender: string | null;
    dob?: string | null;
    date_of_birth?: string | null;
    sex?: string | null;
    phone: string | null;
    email: string | null;
    contacts?: ReportPatientContact[];
  };
  results: ReportResultItem[];
  versions: ReportVersionItem[];
  deliveries: ReportDeliveryItem[];
  access_tokens: ReportAccessTokenState[];
}

export type ExceptionKind =
  | "failed_generation"
  | "failed_delivery"
  | "late_transfer"
  | "critical_unacknowledged"
  | "stuck_sample";

export type ExceptionSeverity = "critical" | "error" | "warning";

export interface ExceptionItem {
  id: string;
  kind: ExceptionKind;
  title: string;
  severity: ExceptionSeverity;
  reference_id: string;
  reference_code: string;
  patient_name: string | null;
  branch_name: string | null;
  created_at: string;
  details: Record<string, unknown>;
}

export interface ExceptionCounts {
  total: number;
  failed_generation: number;
  failed_delivery: number;
  late_transfer: number;
  critical_unacknowledged: number;
  stuck_sample: number;
}

export interface ExceptionsResponse {
  results: ExceptionItem[];
  counts: ExceptionCounts;
}

export interface RegenerateReportResponse {
  status: string;
  generation_status?: string;
  message?: string;
}

export interface DeliverReportRequest {
  channel: DeliveryChannel;
  contact_id: string;
}

export interface DeliverReportResponse {
  id: string;
  report_id: string;
  channel: DeliveryChannel;
  contact_id: string;
  status: DeliveryStatus;
  created_at: string;
  token_id?: string;
  link?: string;
}

export interface IssueAccessTokenResponse {
  token_id: string;
  link: string;
  expires_at: string;
}

export interface RevokeAccessTokenRequest {
  token_id?: string;
  reason?: string;
}

export interface RevokeAccessTokenResponse {
  revoked_count: number;
  status: string;
}

export interface PublicReportAccessError {
  code: string;
  message: string;
  details?: {
    phone?: string | null;
    [key: string]: unknown;
  };
}
