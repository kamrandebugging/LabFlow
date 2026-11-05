/**
 * Reports and Exceptions API Service (Screens 26–30).
 * Connects directly to backend /api/v1/reports and /api/v1/exceptions endpoints.
 * Never uses mocks or seed-data fallbacks in production.
 */

import { useAuthStore } from "../auth/authStore";
import type {
  DeliverReportRequest,
  DeliverReportResponse,
  DeliveryChannel,
  DeliveryStatus,
  ExceptionsResponse,
  IssueAccessTokenResponse,
  PublicReportAccessError,
  RegenerateReportResponse,
  ReportDetail,
  ReportGenerationStatus,
  ReportListFilters,
  ReportListResponse,
  ReportStatus,
  ReportSummaryItem,
  RevokeAccessTokenRequest,
  RevokeAccessTokenResponse,
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
      if (data?.detail) {
        errorMsg = data.detail;
      } else if (data?.error?.message) {
        errorMsg = data.error.message;
      } else if (data?.message) {
        errorMsg = data.message;
      }
    } catch {
      // Non-JSON response
    }
    throw new Error(errorMsg);
  }
  return res.json() as Promise<T>;
}

export const reportsService = {
  /**
   * GET /api/v1/reports — Staff reports list with cursor pagination & filters.
   */
  async getReports(filters: ReportListFilters = {}): Promise<ReportListResponse> {
    const params = new URLSearchParams();
    if (filters.status && filters.status !== "all" && filters.status !== "All") {
      params.set("status", filters.status.toLowerCase());
    }
    if (filters.branch && filters.branch !== "all") {
      params.set("branch", filters.branch);
    }
    if (filters.q && filters.q.trim()) {
      params.set("q", filters.q.trim());
    } else if (filters.patient && filters.patient.trim()) {
      params.set("patient", filters.patient.trim());
    }
    if (filters.created_after) {
      params.set("created_after", filters.created_after);
    }
    if (filters.created_before) {
      params.set("created_before", filters.created_before);
    }
    if (filters.cursor) {
      params.set("cursor", filters.cursor);
    }
    if (filters.limit) {
      params.set("limit", String(filters.limit));
    }

    const queryString = params.toString();
    const url = `/api/v1/reports${queryString ? `?${queryString}` : ""}`;
    const res = await fetch(url, {
      method: "GET",
      headers: getAuthHeaders(),
    });

    const rawData = await handleResponse<{
      results: Array<Record<string, unknown>>;
      next_cursor: string | null;
    }>(res);

    const adaptedResults: ReportSummaryItem[] = (rawData.results || []).map(
      (item) => {
        if (
          item.sample &&
          typeof item.sample === "object" &&
          item.sample !== null
        ) {
          return item as unknown as ReportSummaryItem;
        }

        // Defensive mapping for backend flat record format
        return {
          id: String(item.id || ""),
          status: (item.status as ReportStatus) || "draft",
          generation_status:
            (item.generation_status as ReportGenerationStatus) || "idle",
          generation_error: (item.generation_error as string) || null,
          current_version: Number(item.current_version ?? 1),
          published_at: (item.finalised_at as string) || null,
          created_at: String(item.created_at || ""),
          sample: {
            id: String(item.sample_id || ""),
            accession_id: String(item.accession_id || ""),
            collected_at: (item.collected_at as string) || null,
            branch: item.branch_id
              ? {
                  id: String(item.branch_id),
                  name: String(item.branch_name || ""),
                }
              : null,
            patient: {
              id: String(item.patient_id || ""),
              name: String(item.patient_name || ""),
              mrn: String(item.patient_mrn || ""),
              phone: (item.patient_phone as string) || null,
              email: (item.patient_email as string) || null,
            },
            tests: Array.isArray(item.tests)
              ? item.tests.map((t) =>
                  typeof t === "string"
                    ? { id: t, name: t, code: t }
                    : (t as { id: string; name: string; code: string }),
                )
              : [],
          },
          latest_delivery: item.delivery_status
            ? {
                channel:
                  (item.delivery_channel as DeliveryChannel) || "whatsapp",
                status: item.delivery_status as DeliveryStatus,
                sent_at: (item.delivery_sent_at as string) || null,
              }
            : null,
        };
      },
    );

    return {
      results: adaptedResults,
      next_cursor: rawData.next_cursor,
    };
  },

  /**
   * GET /api/v1/reports/:id — Staff report detail.
   */
  async getReport(reportId: string): Promise<ReportDetail> {
    const res = await fetch(`/api/v1/reports/${reportId}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });

    return handleResponse<ReportDetail>(res);
  },

  /**
   * POST /api/v1/reports/:id/regenerate — Enqueue new PDF generation.
   * Permitted roles: Owner, Manager, Pathologist.
   */
  async regenerateReport(reportId: string): Promise<RegenerateReportResponse> {
    const res = await fetch(`/api/v1/reports/${reportId}/regenerate`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({}),
    });

    return handleResponse<RegenerateReportResponse>(res);
  },

  /**
   * POST /api/v1/reports/:id/deliver — Dispatch report delivery via email/whatsapp.
   * Permitted roles: Owner, Manager, Reception.
   */
  async deliverReport(
    reportId: string,
    data: DeliverReportRequest,
  ): Promise<DeliverReportResponse> {
    const res = await fetch(`/api/v1/reports/${reportId}/deliver`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });

    return handleResponse<DeliverReportResponse>(res);
  },

  /**
   * POST /api/v1/reports/:id/access-token — Issue patient access token link.
   * Permitted roles: Owner, Manager, Reception.
   */
  async issueAccessToken(reportId: string): Promise<IssueAccessTokenResponse> {
    const res = await fetch(`/api/v1/reports/${reportId}/access-token`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({}),
    });

    return handleResponse<IssueAccessTokenResponse>(res);
  },

  /**
   * POST /api/v1/reports/:id/revoke-token — Revoke active patient access token(s).
   * Permitted roles: Owner, Manager.
   */
  async revokeAccessToken(
    reportId: string,
    data: RevokeAccessTokenRequest = {},
  ): Promise<RevokeAccessTokenResponse> {
    const payload: Record<string, unknown> = {};
    if (data.token_id) {
      payload.token_id = data.token_id;
    } else {
      payload.all = true;
    }

    const res = await fetch(`/api/v1/reports/${reportId}/revoke-token`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });

    return handleResponse<RevokeAccessTokenResponse>(res);
  },

  /**
   * GET /api/v1/exceptions — Staff triage exceptions queue derived from real data.
   */
  async getExceptions(): Promise<ExceptionsResponse> {
    const res = await fetch("/api/v1/exceptions", {
      method: "GET",
      headers: getAuthHeaders(),
    });

    return handleResponse<ExceptionsResponse>(res);
  },

  /**
   * PUBLIC GET /api/v1/report-access/:token — Patient token redemption.
   * NO auth headers: token is the sole credential (RP-V3).
   */
  async checkPublicReportAccess(
    token: string,
  ): Promise<{
    status: number;
    redirectUrl?: string;
    error?: PublicReportAccessError;
  }> {
    const url = `/api/v1/report-access/${encodeURIComponent(token)}`;
    const res = await fetch(url, {
      method: "GET",
      // No Authorization header!
    });

    if (res.status === 410 || res.status === 404) {
      let errorData: PublicReportAccessError = {
        code: res.status === 410 ? "link_expired" : "token_not_found",
        message:
          res.status === 410
            ? "This report link has expired."
            : "Report link not found.",
      };
      try {
        const json = await res.json();
        if (json?.error) {
          errorData = json.error;
        } else if (json?.detail) {
          errorData.message = json.detail;
        }
      } catch {
        // Plain text or HTML 410
      }
      return { status: res.status, error: errorData };
    }

    if (!res.ok) {
      let msg = "Failed to load report";
      try {
        const json = await res.json();
        if (json?.error?.message) msg = json.error.message;
      } catch {
        // Ignore non-json
      }
      return {
        status: res.status,
        error: { code: "error", message: msg },
      };
    }

    // 200 or 302
    return {
      status: res.status,
      redirectUrl: url,
    };
  },
};
