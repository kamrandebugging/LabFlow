/**
 * Sample Management API Service (Doc 02 §5.5, Doc 03 §5.4, SM-1..SM-11, Screens 16–20).
 */

import { useAuthStore } from "../auth/authStore";
import type {
  SampleCancelInput,
  SampleCreatedResponse,
  SampleCreateInput,
  SampleDetail,
  SampleEventItem,
  SampleLabelData,
  SampleListFilter,
  SampleListResponse,
  SampleRejectInput,
  SampleTransferInput,
} from "./types";

const API_BASE = "/api/v1/samples";

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

export const sampleService = {
  /**
   * List accessions with status, search and branch filters
   */
  async listSamples(
    filters: SampleListFilter = {},
  ): Promise<SampleListResponse> {
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      throw new Error("Authentication required: no access token found");
    }

    const url = new URL(API_BASE, window.location.origin);
    if (filters.q) url.searchParams.set("q", filters.q);
    if (filters.status && filters.status !== "all") {
      url.searchParams.set("status", filters.status);
    }
    if (filters.branch_id && filters.branch_id !== "all") {
      url.searchParams.set("branch_id", filters.branch_id);
    }

    const res = await fetch(url.toString(), {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to fetch samples (${res.status})`,
      );
    }

    const data = await res.json();
    if (Array.isArray(data)) {
      return { results: data, total: data.length };
    }
    if (data && Array.isArray(data.results)) {
      return { results: data.results, total: data.total ?? data.results.length };
    }
    return { results: [], total: 0 };
  },

  /**
   * Get full sample detail by ID or accession number
   */
  async getSample(sampleId: string): Promise<SampleDetail> {
    const res = await fetch(`${API_BASE}/${sampleId}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Sample not found (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Accession / collect specimen (SM-1..SM-3, POST /api/v1/samples)
   */
  async collectSample(
    input: SampleCreateInput,
  ): Promise<SampleCreatedResponse> {
    const res = await fetch(API_BASE, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify({
        invoice_id: input.invoice_id,
        ...(input.invoice_item_ids && input.invoice_item_ids.length > 0
          ? { invoice_item_ids: input.invoice_item_ids }
          : {}),
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg =
        err?.error?.message ||
        err?.detail ||
        `Collection failed (${res.status})`;
      throw new Error(msg);
    }

    return await res.json();
  },

  /**
   * Fetch stored barcode label payload (SM-4, GET /api/v1/samples/{id}/label)
   */
  async getLabel(sampleId: string): Promise<SampleLabelData> {
    const res = await fetch(`${API_BASE}/${sampleId}/label`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to fetch sample label (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Receive specimen into laboratory (SM-7, POST /api/v1/samples/{id}/receive)
   */
  async receiveSample(sampleId: string): Promise<SampleCreatedResponse> {
    const res = await fetch(`${API_BASE}/${sampleId}/receive`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to receive sample (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Reject specimen for quality non-conformance (SM-8, POST /api/v1/samples/{id}/reject)
   */
  async rejectSample(
    sampleId: string,
    input: SampleRejectInput,
  ): Promise<SampleCreatedResponse> {
    const res = await fetch(`${API_BASE}/${sampleId}/reject`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to reject sample (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Issue fresh accession for rejected sample (SM-9, POST /api/v1/samples/{id}/recollect)
   */
  async recollectSample(sampleId: string): Promise<SampleCreatedResponse> {
    const res = await fetch(`${API_BASE}/${sampleId}/recollect`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to trigger recollection (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Cancel specimen accession (POST /api/v1/samples/{id}/cancel)
   */
  async cancelSample(
    sampleId: string,
    input: SampleCancelInput,
  ): Promise<SampleCreatedResponse> {
    const res = await fetch(`${API_BASE}/${sampleId}/cancel`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to cancel sample (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Transfer specimen to another branch (SM-7, POST /api/v1/samples/{id}/transfer)
   */
  async transferSample(
    sampleId: string,
    input: SampleTransferInput,
  ): Promise<{ id: string; status: string }> {
    const res = await fetch(`${API_BASE}/${sampleId}/transfer`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to transfer sample (${res.status})`,
      );
    }

    return await res.json();
  },

  /**
   * Fetch chain-of-custody audit event timeline (GET /api/v1/samples/{id}/events)
   */
  async getEvents(sampleId: string): Promise<SampleEventItem[]> {
    const res = await fetch(`${API_BASE}/${sampleId}/events`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.error?.message || `Failed to fetch events (${res.status})`,
      );
    }

    const data = await res.json();
    return Array.isArray(data) ? data : data.results || [];
  },
};
