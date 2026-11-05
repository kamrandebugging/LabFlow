/**
 * Type definitions for LabFlow Settings suite (Screens 33–35).
 * - Screen 33: Branches (/settings/branches)
 * - Screen 34: Tenant Settings (/settings/tenant)
 * - Screen 35: Data Export (/settings/exports)
 */

export interface Branch {
  id: string;
  code: string;
  name: string;
  address: string | null;
  phone: string | null;
  is_collection_centre: boolean;
  result_entry_enabled: boolean;
  deleted_at: string | null;
}

export interface CreateBranchPayload {
  code: string;
  name: string;
  address?: string | null;
  phone?: string | null;
  is_collection_centre?: boolean;
}

export interface UpdateBranchPayload {
  code?: string;
  name?: string;
  address?: string | null;
  phone?: string | null;
  is_collection_centre?: boolean;
}

export interface BranchOpenWorkDetails {
  open_transfers_in?: number;
  open_transfers_out?: number;
  samples_held?: number;
}

export interface PlanLimitDetails {
  plan_limit?: number;
  current_count?: number;
}

export interface BranchActionError {
  code: string;
  message: string;
  details?:
    BranchOpenWorkDetails | PlanLimitDetails | Record<string, unknown> | null;
}

/**
 * Screen 34: Tenant Settings (exactly 6 registry keys per Doc 04 / settings_registry.py).
 */
export interface TenantSettings {
  billing_hold_enabled: boolean;
  report_default_language: "en" | "ur";
  report_link_validity_days: number;
  transfer_late_after_hours: number;
  brand_display_name: string;
  brand_accent_colour: string;
}

export type TenantSettingsUpdatePayload = Partial<TenantSettings>;

/**
 * Screen 35: Data Export.
 */
export type ExportStatus =
  "pending" | "running" | "processing" | "complete" | "ready" | "failed";

export interface DataExportManifest {
  tables_count?: number;
  reports_count?: number;
  row_counts?: Record<string, number>;
  sha256?: string;
}

export interface DataExport {
  id: string;
  status: ExportStatus;
  requested_at: string;
  completed_at: string | null;
  file_size_bytes?: number | null;
  download_url?: string | null;
  error_message?: string | null;
  manifest?: DataExportManifest | null;
}
