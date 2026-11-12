/**
 * API Service for Referral Partners suite (Screens 36–37).
 * - Collection: GET, POST /api/v1/referral-partners
 * - Detail: GET, PATCH, DELETE /api/v1/referral-partners/:id
 * - Dashboard: GET /api/v1/referral-partners/:id/dashboard
 * - Rules: GET /api/v1/referral-partners/:id/rules
 *
 * Direct integration with backend endpoints; zero mock fallbacks.
 */

import { useAuthStore } from "../auth/authStore";
import type {
  CreatePartnerPayload,
  CreateRulePayload,
  PartnerDashboardData,
  ReferralPartner,
  RevenueShareRule,
  Settlement,
  SettlementExceptionsData,
  SettlementListResponse,
  SettlementStatus,
  ShareLedgerResponse,
  UpdatePartnerPayload,
  UpdateRulePayload,
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

export class PartnerApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown> | null;

  constructor(
    message: string,
    code: string = "partner_error",
    status: number = 400,
    details?: Record<string, unknown> | null,
  ) {
    super(message);
    this.name = "PartnerApiError";
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

    throw new PartnerApiError(message, code, res.status, details);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json() as Promise<T>;
}

export const partnersService = {
  /**
   * GET /api/v1/referral-partners
   * Lists all referral partners for tenant.
   */
  async getPartners(): Promise<ReferralPartner[]> {
    const res = await fetch("/api/v1/referral-partners", {
      method: "GET",
      headers: getAuthHeaders(),
    });
    const data = await handleResponse<{ results: ReferralPartner[] }>(res);
    return data.results || [];
  },

  /**
   * GET /api/v1/referral-partners/:id
   * Single partner details.
   */
  async getPartner(id: string): Promise<ReferralPartner> {
    const res = await fetch(`/api/v1/referral-partners/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<ReferralPartner>(res);
  },

  /**
   * POST /api/v1/referral-partners
   * Creates a new referral partner. Requires Idempotency-Key header.
   */
  async createPartner(payload: CreatePartnerPayload): Promise<ReferralPartner> {
    const idempotencyKey = `partner-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const res = await fetch("/api/v1/referral-partners", {
      method: "POST",
      headers: getAuthHeaders({
        "Idempotency-Key": idempotencyKey,
      }),
      body: JSON.stringify(payload),
    });
    return handleResponse<ReferralPartner>(res);
  },

  /**
   * PATCH /api/v1/referral-partners/:id
   * Updates partner identity or active status.
   */
  async updatePartner(
    id: string,
    payload: UpdatePartnerPayload,
  ): Promise<ReferralPartner> {
    const res = await fetch(`/api/v1/referral-partners/${id}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse<ReferralPartner>(res);
  },

  /**
   * DELETE /api/v1/referral-partners/:id
   * Soft deletes a partner. Returns 409 partner_has_ledger_entries if ledger entries exist.
   */
  async deletePartner(id: string): Promise<void> {
    const res = await fetch(`/api/v1/referral-partners/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    await handleResponse<void>(res);
  },

  /**
   * GET /api/v1/referral-partners/:id/dashboard
   * Live financial and operational metrics for partner.
   */
  async getPartnerDashboard(id: string): Promise<PartnerDashboardData> {
    const res = await fetch(`/api/v1/referral-partners/${id}/dashboard`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<PartnerDashboardData>(res);
  },

  /**
   * GET /api/v1/referral-partners/:id/rules
   * Revenue share rules configured for partner.
   */
  async getPartnerRules(id: string): Promise<RevenueShareRule[]> {
    const res = await fetch(`/api/v1/referral-partners/${id}/rules`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    const data = await handleResponse<{ results: RevenueShareRule[] }>(res);
    return data.results || [];
  },

  /**
   * POST /api/v1/referral-partners/:id/rules
   * Creates a new revenue share rule for partner.
   */
  async createPartnerRule(
    partnerId: string,
    payload: CreateRulePayload,
  ): Promise<RevenueShareRule> {
    const res = await fetch(`/api/v1/referral-partners/${partnerId}/rules`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse<RevenueShareRule>(res);
  },

  /**
   * PATCH /api/v1/revenue-share-rules/:ruleId
   * Updates a rule via RR-3: closes old rule and inserts new rule row.
   */
  async updatePartnerRule(
    ruleId: string,
    payload: UpdateRulePayload,
  ): Promise<RevenueShareRule> {
    const res = await fetch(`/api/v1/revenue-share-rules/${ruleId}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse<RevenueShareRule>(res);
  },

  /**
   * GET /api/v1/referral-partners/ledger
   * Immutable revenue share fact table with cursor pagination and totals.
   */
  async getShareLedger(params?: {
    partner_id?: string;
    period?: string;
    rule_id?: string;
    limit?: number;
    cursor?: string;
  }): Promise<ShareLedgerResponse> {
    const query = new URLSearchParams();
    if (params?.partner_id) query.set("partner_id", params.partner_id);
    if (params?.period) query.set("period", params.period);
    if (params?.rule_id) query.set("rule_id", params.rule_id);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);

    const queryString = query.toString();
    const endpoint = `/api/v1/referral-partners/ledger${queryString ? `?${queryString}` : ""}`;
    const res = await fetch(endpoint, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<ShareLedgerResponse>(res);
  },

  /**
   * GET /api/v1/settlements
   * List settlements with status, partner, period filters.
   */
  async getSettlements(params?: {
    partner_id?: string;
    period?: string;
    status?: SettlementStatus | string;
    limit?: number;
    cursor?: string;
    signal?: AbortSignal;
  }): Promise<SettlementListResponse> {
    const query = new URLSearchParams();
    if (params?.partner_id) query.set("partner_id", params.partner_id);
    if (params?.period) query.set("period", params.period);
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);

    const queryString = query.toString();
    const endpoint = `/api/v1/settlements${queryString ? `?${queryString}` : ""}`;
    const res = await fetch(endpoint, {
      method: "GET",
      headers: getAuthHeaders(),
      signal: params?.signal,
    });
    return handleResponse<SettlementListResponse>(res);
  },

  /**
   * GET /api/v1/settlements/:id
   * Single settlement detail including line items and version.
   */
  async getSettlement(id: string): Promise<Settlement> {
    const res = await fetch(`/api/v1/settlements/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<Settlement>(res);
  },

  /**
   * GET /api/v1/settlements/exceptions
   * Settlement exception counters.
   */
  async getSettlementExceptions(): Promise<SettlementExceptionsData> {
    const res = await fetch("/api/v1/settlements/exceptions", {
      method: "GET",
      headers: getAuthHeaders(),
    });
    return handleResponse<SettlementExceptionsData>(res);
  },

  /**
   * POST /api/v1/settlements/:id/approve
   * Approves a settlement (Owner only; requires If-Match version header).
   */
  async approveSettlement(id: string, version: string): Promise<Settlement> {
    const res = await fetch(`/api/v1/settlements/${id}/approve`, {
      method: "POST",
      headers: getAuthHeaders({
        "If-Match": version,
      }),
    });
    return handleResponse<Settlement>(res);
  },

  /**
   * POST /api/v1/settlements/:id/cancel
   * Cancels a settlement (Owner only; requires If-Match version header).
   */
  async cancelSettlement(id: string, version: string): Promise<Settlement> {
    const res = await fetch(`/api/v1/settlements/${id}/cancel`, {
      method: "POST",
      headers: getAuthHeaders({
        "If-Match": version,
      }),
    });
    return handleResponse<Settlement>(res);
  },

  /**
   * POST /api/v1/settlements/:id/mark-paid
   * Marks a settlement paid (Owner only; requires If-Match version header).
   */
  async markPaidSettlement(
    id: string,
    version: string,
    reference?: string,
  ): Promise<Settlement> {
    const res = await fetch(`/api/v1/settlements/${id}/mark-paid`, {
      method: "POST",
      headers: getAuthHeaders({
        "If-Match": version,
      }),
      body: JSON.stringify(reference ? { reference } : {}),
    });
    return handleResponse<Settlement>(res);
  },

  /**
   * POST /api/v1/settlements/:id/send
   * Sends statement notification to partner (Owner only).
   */
  async sendSettlement(id: string): Promise<unknown> {
    const res = await fetch(`/api/v1/settlements/${id}/send`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
    return handleResponse<unknown>(res);
  },

  /**
   * URL for statement PDF download.
   */
  getStatementPdfUrl(id: string): string {
    return `/api/v1/settlements/${id}/statement.pdf`;
  },
};
