/**
 * Invoicing & Billing API Service (Doc 03 §5.3, §6.4, LAB-20, 21, 22).
 */

import { apiRequest, ApiError } from "../../lib/apiClient";
import { useAuthStore } from "../auth/authStore";
import type {
  InvoiceCreateInput,
  InvoiceDetail,
  InvoiceListResponse,
  PaymentCreateInput,
  PaymentRecord,
} from "./types";

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
      signal?: AbortSignal;
    } = {},
  ): Promise<InvoiceListResponse> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (params.status && params.status !== "all") {
      query.status = params.status;
    }
    if (params.patientId) {
      query.patient_id = params.patientId;
    }
    if (params.cursor) {
      query.cursor = params.cursor;
    }
    if (params.limit) {
      query.limit = params.limit;
    }

    try {
      const data = await apiRequest<
        | {
            results?: InvoiceDetail[];
            items?: InvoiceDetail[];
            next_cursor?: string | null;
            total_count?: number;
            daily_total?: string;
          }
        | InvoiceDetail[]
      >("/invoices", { query, signal: params.signal });

      if (Array.isArray(data)) {
        return {
          results: data,
          total_count: data.length,
        };
      }
      return {
        results: data.results || data.items || [],
        next_cursor: data.next_cursor || null,
        total_count:
          data.total_count ?? (data.results || data.items || []).length,
        // Preserve absence: a missing server aggregate must render as
        // unavailable, never as a fabricated PKR 0.00.
        daily_total: data.daily_total,
      };
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch invoices (${err.status})`,
        );
      }
      throw err;
    }
  },

  async getInvoice(id: string): Promise<InvoiceDetail> {
    try {
      return await apiRequest<InvoiceDetail>(`/invoices/${id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch invoice ${id} (${err.status})`,
        );
      }
      throw err;
    }
  },

  async createInvoice(
    input: InvoiceCreateInput,
    idempotencyKey?: string,
  ): Promise<InvoiceDetail> {
    const key = idempotencyKey || generateIdempotencyKey();
    const userBranch = useAuthStore.getState().user?.branch_ids?.[0];
    const branchId = input.branch_id || userBranch;
    if (!branchId) {
      throw new Error(
        "No branch is available for this invoice. Select a patient assigned to one of your branches.",
      );
    }

    const cleanItems = input.items.map((it) => {
      if (it.panel_id) {
        return { panel_id: it.panel_id, qty: it.qty || 1 };
      }
      return { test_id: it.test_id, qty: it.qty || 1 };
    });

    try {
      return await apiRequest<InvoiceDetail>("/invoices", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: {
          patient_id: input.patient_id,
          branch_id: branchId,
          referral_partner_id: input.referral_partner_id || null,
          items: cleanItems,
          discount_amount: input.discount_amount || "0.00",
          discount_reason: input.discount_reason || null,
        },
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to create invoice (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async recordPayment(
    invoiceId: string,
    input: PaymentCreateInput,
    idempotencyKey?: string,
  ): Promise<PaymentRecord> {
    const key = idempotencyKey || generateIdempotencyKey();
    try {
      return await apiRequest<PaymentRecord>(
        `/invoices/${invoiceId}/payments`,
        {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: {
            kind: input.kind,
            method: input.method,
            amount: input.amount,
            reference: input.reference || null,
          },
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to record payment (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async cancelInvoice(
    invoiceId: string,
    reason: string,
  ): Promise<InvoiceDetail> {
    try {
      return await apiRequest<InvoiceDetail>(`/invoices/${invoiceId}/cancel`, {
        method: "POST",
        body: { reason },
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to cancel invoice (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },
};
