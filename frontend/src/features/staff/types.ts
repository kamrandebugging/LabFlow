/**
 * Staff CRUD types — mirror the Owner-only `/api/v1/staff` contract exactly.
 * No credential material is ever part of these shapes (S11).
 */

export type StaffRole = "manager" | "reception" | "technician" | "pathologist";

export interface StaffBranchRef {
  id: string;
  code: string;
  name: string;
}

export interface StaffRow {
  id: string;
  display_name: string;
  email: string;
  role: StaffRole | "owner";
  role_label: string;
  is_owner: boolean;
  branch: StaffBranchRef | null;
  status: "active" | "deactivated";
  is_active: boolean;
  totp_status: "enabled" | "disabled";
  totp_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface StaffAuditRow {
  id: string;
  action: string;
  actor_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string | null;
}

export interface StaffDetail extends StaffRow {
  created_by: string | null;
  audit_history: StaffAuditRow[];
}

export interface StaffEnabledRole {
  role: StaffRole;
  label: string;
}

export interface StaffListResponse {
  owner: StaffRow | null;
  results: StaffRow[];
  next_cursor: string | null;
  staff_count: number;
  plan_staff_limit: number | null;
  enabled_roles: StaffEnabledRole[];
  branches: StaffBranchRef[];
}

export interface CreateStaffInput {
  display_name: string;
  email: string;
  role: StaffRole;
  branch_id: string | null;
}

export interface UpdateStaffInput {
  display_name?: string;
  role?: StaffRole;
  branch_id?: string | null;
}

export interface StaffTempPasswordResponse {
  staff: StaffRow;
  temp_password: string;
  password_is_temporary: boolean;
}
