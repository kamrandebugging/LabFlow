/**
 * Patient Management Types (Doc 03 §5.1, §6.2, Doc 04 §8.5, Screen 08 & 09).
 */

export type PatientSex = "M" | "F" | "O";

export interface PatientCandidate {
  id: string;
  mrn: string;
  name: string;
  sex: string;
  year_of_birth: number | null;
  branch_id: string;
}

export interface PatientContact {
  id: string;
  kind: "phone" | "email" | "whatsapp" | "address";
  value: string;
  is_primary: boolean;
  created_at: string;
}

export interface PatientConsent {
  id: string;
  channel: "whatsapp" | "sms" | "email";
  granted_at: string;
  granted_by: string;
  revoked_at: string | null;
}

export interface PatientSummary {
  id: string;
  mrn: string;
  name: string;
  sex: PatientSex | string;
  phone?: string | null;
  date_of_birth?: string | null;
  year_of_birth?: number | null;
  branch_id: string;
  branch_name?: string;
  referral_partner_id?: string | null;
  referral_partner_name?: string | null;
  last_visit?: string | null;
  created_at: string;
  updated_at: string;
  is_cross_branch: boolean;
  version?: string;
}

export interface PatientInvoiceSummary {
  id: string;
  invoice_number: string;
  status: string;
  total: string | null;
  branch_id: string;
  branch_name?: string;
  created_at: string;
}

export interface PatientDetail extends PatientSummary {
  contacts: PatientContact[];
  consents: PatientConsent[];
  invoices?: PatientInvoiceSummary[];
}

export interface PatientVisitSample {
  id: string;
  accession_id: string;
  status: string;
  collected_at: string | null;
  created_at: string;
}

export interface PatientVisitReport {
  id: string;
  sample_id: string;
  accession_id: string;
  status: string;
  current_version: number;
  finalised_at: string | null;
}

export interface PatientVisit {
  invoice_id: string;
  invoice_number: string;
  branch_id: string;
  branch_name: string;
  status: string;
  total: string | null;
  created_at: string;
  samples: PatientVisitSample[];
  reports: PatientVisitReport[];
}

export interface PatientHistoryResponse {
  patient_id: string;
  mrn: string;
  visits: PatientVisit[];
}

export interface PatientCreateInput {
  name: string;
  phone: string;
  sex: "M" | "F";
  date_of_birth?: string | null;
  branch_id: string;
  referral_partner_id?: string | null;
  whatsapp_number?: string;
  consent_reports?: boolean;
  confirm_duplicate?: boolean;
}

export interface PatientUpdateInput {
  name?: string;
  phone?: string;
  sex?: "M" | "F";
  date_of_birth?: string | null;
}

export interface DuplicateWarningError {
  code: "possible_duplicate";
  message: string;
  candidates: PatientCandidate[];
}
