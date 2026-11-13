/**
 * Sample Management Types (Doc 02 §5.5, Doc 03 §5.4, Screens 16–20).
 */

export type SampleStatus =
  "collected" | "received" | "in_process" | "ready" | "rejected" | "cancelled";

export type RejectionReasonCode =
  | "unlabelled"
  | "mislabelled"
  | "hemolyzed"
  | "insufficient_volume"
  | "wrong_tube"
  | "clotted"
  | "lipemic"
  | "damaged_transport"
  | "barcode_issue"
  | "other";

export type TransferStatus = "open" | "received" | "cancelled" | "lost";

export interface BranchRef {
  id: string;
  code: string;
  name: string;
}

export interface SampleReferenceRange {
  low: string | null;
  high: string | null;
  unit: string | null;
  critical_low?: string | null;
  critical_high?: string | null;
}

export interface SampleTestItem {
  id: string;
  test_id: string;
  test_name: string;
  test_code: string;
  invoice_item_id: string;
  category?: string | null;
  unit?: string | null;
  reference_range?: SampleReferenceRange | null;
  panel_codes?: string[];
  specimen_type?: string;
  tube_type?: string;
  tube_color?: string;
  required_volume_ml?: number;
}

/** A2: an ordered invoice item with no live sample yet. Derived, not stored. */
export interface AwaitingCollectionItem {
  invoice_id: string;
  invoice_item_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  branch_id: string;
  branch_name: string;
  ordered_at: string;
  test_id: string | null;
  test_name: string | null;
  test_code: string | null;
  panel_id: string | null;
  panel_name: string | null;
  description: string;
  status: "awaiting_collection";
}

export interface AwaitingCollectionResponse {
  results: AwaitingCollectionItem[];
  total: number;
}

export interface SampleSummary {
  id: string;
  accession_id: string;
  invoice_id: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  patient_sex?: "M" | "F" | "O" | string;
  patient_age_years?: number;
  branch_id: string;
  branch_name: string;
  status: SampleStatus;
  tests: string[];
  collected_at: string;
  age_display?: string;
  rejection_reason_code?: RejectionReasonCode | null;
  rejection_note?: string | null;
}

export interface SampleEventItem {
  id: string;
  event:
    | "COLLECTED"
    | "RECEIVED"
    | "IN_PROCESS"
    | "REJECTED"
    | "TRANSFERRED_IN"
    | "TRANSFERRED_OUT"
    | "TRANSFER_CANCELLED"
    | "TRANSFER_LOST"
    | "READY"
    | "CANCELLED"
    | string;
  actor: string | null;
  branch: BranchRef | null;
  timestamp: string;
  payload?: {
    rejection_code?: string;
    from_branch?: BranchRef | null;
    to_branch?: BranchRef | null;
    note?: string;
  };
}

export interface SampleDetail extends SampleSummary {
  patient_dob?: string | null;
  collected_by: string | null;
  sample_tests: SampleTestItem[];
  custody_location?: string;
  bench_code?: string;
  open_transfer?: {
    id: string;
    from_branch: BranchRef;
    to_branch: BranchRef;
    dispatched_at: string;
    status: TransferStatus;
  } | null;
  events?: SampleEventItem[];
}

export interface SampleLabelData {
  accession_id: string;
  patient_name: string;
  mrn: string;
  date_of_birth: string | null;
  collected_at: string;
  collected_by: string | null;
  branch_name?: string;
  tests?: string[];
  barcode: {
    symbology: "code128" | string;
    payload: string;
  };
}

export interface SampleCreateInput {
  invoice_id: string;
  invoice_item_ids?: string[];
  notes?: string;
}

export interface SampleCreatedResponse {
  id: string;
  accession_id: string;
  invoice_id: string;
  branch_id: string;
  status: SampleStatus;
  collected_at: string;
  collected_by: string | null;
}

export interface SampleRejectInput {
  reason_code: RejectionReasonCode;
  note?: string;
  reason_text?: string;
}

export interface SampleCancelInput {
  reason: string;
}

export interface SampleTransferInput {
  to_branch_id: string;
  notes?: string;
}

export interface SampleListFilter {
  q?: string;
  status?: string;
  branch_id?: string;
  page?: number;
  limit?: number;
  order?: "newest" | "oldest";
}

export interface SampleListResponse {
  results: SampleSummary[];
  total: number;
}

export interface SampleCollectionDraft {
  invoice_id: string;
  invoice_number?: string;
  patient_id: string;
  patient_name: string;
  patient_mrn: string;
  patient_sex?: string;
  patient_age?: string;
  branch_id?: string;
  branch_name?: string;
  selected_item_ids: string[];
  selected_items?: Array<{
    id: string;
    item_type: string;
    item_id: string;
    name: string;
    unit_price: string;
    quantity: number;
    total_price: string;
  }>;
  test_labels: string[];
  tubes_required: Array<{
    type: string;
    color: string;
    specimen: string;
    count: number;
  }>;
  collected_at: string;
  collected_by?: string;
  notes?: string;
}
