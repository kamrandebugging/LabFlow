/**
 * API Service for LabFlow Settings suite (Screens 33–35).
 * - Branches: /api/v1/branches
 * - Tenant Settings: /api/v1/settings
 * - Data Export: /api/v1/exports
 *
 * Direct integration with backend endpoints; zero mock fallbacks.
 */

import { useAuthStore } from "../auth/authStore";
import type {
  Branch,
  CreateBranchPayload,
  DataExport,
  UpdateBranchPayload,
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

export class SettingsApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown> | null;

  constructor(
    message: string,
    code: string = "settings_error",
    status: number = 400,
    details?: Record<string, unknown> | null,
  ) {
    super(message);
    this.name = "SettingsApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "error";
    let message = `Server error (${res.status})`;
    let details: Record<string, unknown> | null = null;

    try {
      const data = await res.json();
      if (data?.error && typeof data.error === "object") {
        code = data.error.code || code;
        message = data.error.message || message;
        details = data.error.details || null;
      } else if (data?.code) {
        code = data.code;
        message = data.detail || data.message || message;
        details = data.details || data.errors || null;
      } else if (data?.detail) {
        message = data.detail;
      } else if (data?.message) {
        message = data.message;
      }
    } catch {
      // Non-JSON response
    }

    throw new SettingsApiError(message, code, res.status, details);
  }

  return res.json() as Promise<T>;
}

export const settingsService = {
  // ============================================================================
  // Screen 33: Branches API (/api/v1/branches)
  // ============================================================================

  /**
   * GET /api/v1/branches
   * Note: include_closed=true is available to Lab Owners only.
   */
  async getBranches(includeClosed = false): Promise<Branch[]> {
    const url = `/api/v1/branches${includeClosed ? "?include_closed=true" : ""}`;
    const res = await fetch(url, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<Branch[]>(res);
  },

  /**
   * POST /api/v1/branches (Owner only)
   */
  async createBranch(payload: CreateBranchPayload): Promise<Branch> {
    const res = await fetch("/api/v1/branches", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse<Branch>(res);
  },

  /**
   * PATCH /api/v1/branches/<id> (Owner only)
   * Supports optimistic locking via If-Match header.
   */
  async updateBranch(
    branchId: string,
    payload: UpdateBranchPayload,
    ifMatch?: string,
  ): Promise<Branch> {
    const extraHeaders: Record<string, string> = {};
    if (ifMatch) {
      extraHeaders["If-Match"] = ifMatch;
    }
    const res = await fetch(`/api/v1/branches/${branchId}`, {
      method: "PATCH",
      headers: getAuthHeaders(extraHeaders),
      body: JSON.stringify(payload),
    });
    return handleResponse<Branch>(res);
  },

  /**
   * POST /api/v1/branches/<id>/close (Owner only)
   * Soft-deletes branch; fails with 409 branch_has_open_work if open work exists.
   */
  async closeBranch(branchId: string): Promise<Branch> {
    const res = await fetch(`/api/v1/branches/${branchId}/close`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
    return handleResponse<Branch>(res);
  },

  /**
   * POST /api/v1/branches/<id>/reopen (Owner only)
   * Clears deleted_at on the branch.
   */
  async reopenBranch(branchId: string): Promise<Branch> {
    const res = await fetch(`/api/v1/branches/${branchId}/reopen`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
    return handleResponse<Branch>(res);
  },

  // ============================================================================
  // Screen 34: Tenant Settings API (/api/v1/settings)
  // ============================================================================

  /**
   * GET /api/v1/settings
   * Returns dictionary of setting specs with values and defaults.
   */
  async getSettings(): Promise<
    Record<
      string,
      {
        value: unknown;
        default: unknown;
        type: string;
        description: string;
      }
    >
  > {
    const res = await fetch("/api/v1/settings", {
      method: "GET",
      headers: getAuthHeaders(),
    });
    const data = await handleResponse<{
      settings: Record<
        string,
        {
          value: unknown;
          default: unknown;
          type: string;
          description: string;
        }
      >;
    }>(res);
    return data.settings;
  },

  /**
   * PATCH /api/v1/settings
   * Backend requires values formatted as strings.
   */
  async updateSettings(
    updates: Record<string, string>,
  ): Promise<Record<string, { value: unknown }>> {
    const res = await fetch("/api/v1/settings", {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify({ settings: updates }),
    });
    const data = await handleResponse<{
      settings: Record<string, { value: unknown }>;
    }>(res);
    return data.settings;
  },

  // ============================================================================
  // Screen 35: Data Export API (/api/v1/exports)
  // ============================================================================

  /**
   * POST /api/v1/exports
   * Requires Idempotency-Key header.
   */
  async requestExport(): Promise<{ export_id: string; status: string }> {
    const idempotencyKey = crypto.randomUUID
      ? crypto.randomUUID()
      : `export-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const res = await fetch("/api/v1/exports", {
      method: "POST",
      headers: getAuthHeaders({
        "Idempotency-Key": idempotencyKey,
      }),
    });
    return handleResponse<{ export_id: string; status: string }>(res);
  },

  /**
   * GET /api/v1/exports/<id>
   * Polls status of data export.
   */
  async getExportStatus(exportId: string): Promise<DataExport> {
    const res = await fetch(`/api/v1/exports/${exportId}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    const data = await handleResponse<{
      export_id: string;
      status: string;
      created_at: string;
      download_url?: string;
      download_expires_at?: string;
      error?: string;
    }>(res);

    return {
      id: data.export_id,
      status: data.status as DataExport["status"],
      requested_at: data.created_at,
      completed_at: data.download_expires_at || null,
      download_url: data.download_url || null,
      error_message: data.error || null,
    };
  },
};
