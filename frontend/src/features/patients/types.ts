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
  last_visit?: string | null;
  created_at: string;
  updated_at: string;
  is_cross_branch: boolean;
  version?: number;
}

export interface PatientDetail extends PatientSummary {
  contacts: PatientContact[];
  consents: PatientConsent[];
}

export interface PatientCreateInput {
  name: string;
  phone: string;
  sex: "M" | "F";
  date_of_birth?: string | null;
  branch_id: string;
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
