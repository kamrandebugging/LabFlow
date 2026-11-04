/**
 * Invoicing & Billing API Service (Doc 03 §5.3, §6.4, LAB-20, 21, 22).
 */

import { useAuthStore } from "../auth/authStore";
import type {
  InvoiceCreateInput,
  InvoiceDetail,
  InvoiceListResponse,
  PaymentCreateInput,
  PaymentRecord,
} from "./types";

const API_BASE = "/api/v1/invoices";

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

function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return (
    "idem-" + Date.now() + "-" + Math.random().toString(36).substring(2, 9)
  );
}

export const billingService = {
  async listInvoices(
    params: {
      status?: string;
      patientId?: string;
      cursor?: string;
      limit?: number;
    } = {},
  ): Promise<InvoiceListResponse> {
    const url = new URL(API_BASE, window.location.origin);
    if (params.status && params.status !== "all") {
      url.searchParams.set("status", params.status);
    }
    if (params.patientId) {
      url.searchParams.set("patient_id", params.patientId);
    }
    if (params.cursor) {
      url.searchParams.set("cursor", params.cursor);
    }
    if (params.limit) {
      url.searchParams.set("limit", String(params.limit));
    }

    const res = await fetch(url.toString(), {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Failed to load invoices (${res.status})`);
    }

    const data = await res.json();
    if (Array.isArray(data)) {
      return { results: data };
    }
    return {
      results: data.results || data.items || [],
      next_cursor: data.next_cursor || null,
      total_count: data.total_count,
      daily_total: data.daily_total,
    };
  },

  async getInvoice(id: string): Promise<InvoiceDetail> {
    const res = await fetch(`${API_BASE}/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Invoice not found (${res.status})`);
    }

    return res.json();
  },

  async createInvoice(
    input: InvoiceCreateInput,
    idempotencyKey?: string,
  ): Promise<InvoiceDetail> {
    const key = idempotencyKey || generateIdempotencyKey();
    const userBranch = useAuthStore.getState().user?.branch_ids?.[0];
    const branchId =
      input.branch_id || userBranch || "00000000-0000-0000-0000-000000000001";

    // Strict backend schema: exactly one of test_id or panel_id, and qty >= 1
    const cleanItems = input.items.map((it) => {
      if (it.panel_id) {
        return { panel_id: it.panel_id, qty: it.qty || 1 };
      }
      return { test_id: it.test_id, qty: it.qty || 1 };
    });

    const res = await fetch(API_BASE, {
      method: "POST",
      headers: getAuthHeaders({ "Idempotency-Key": key }),
      credentials: "include",
      body: JSON.stringify({
        patient_id: input.patient_id,
        branch_id: branchId,
        referral_partner_id: input.referral_partner_id || null,
        items: cleanItems,
        discount_amount: input.discount_amount || "0.00",
        discount_reason: input.discount_reason || null,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const message =
        err?.error?.message ||
        err?.items?.[0] ||
        err?.discount_amount?.[0] ||
        `Failed to create invoice (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = err?.error?.code;
      throw error;
    }

    return res.json();
  },

  async recordPayment(
    invoiceId: string,
    input: PaymentCreateInput,
    idempotencyKey?: string,
  ): Promise<PaymentRecord> {
    const key = idempotencyKey || generateIdempotencyKey();
    const res = await fetch(`${API_BASE}/${invoiceId}/payments`, {
      method: "POST",
      headers: getAuthHeaders({ "Idempotency-Key": key }),
      credentials: "include",
      body: JSON.stringify({
        kind: input.kind,
        method: input.method,
        amount: input.amount,
        reference: input.reference || null,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const message =
        err?.error?.message ||
        err?.amount?.[0] ||
        `Failed to record payment (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = err?.error?.code;
      throw error;
    }

    return res.json();
  },

  async cancelInvoice(
    invoiceId: string,
    reason: string,
  ): Promise<InvoiceDetail> {
    const res = await fetch(`${API_BASE}/${invoiceId}/cancel`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify({ reason }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const message =
        err?.error?.message ||
        err?.reason?.[0] ||
        `Failed to cancel invoice (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = err?.error?.code;
      throw error;
    }

    return res.json();
  },
};
