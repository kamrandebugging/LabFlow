/**
 * Sample Management API Service (Doc 02 §5.5, Doc 03 §5.4, SM-1..SM-11, Screens 16–20).
 */

import { apiRequest, ApiError } from "../../lib/apiClient";
import type {
  AwaitingCollectionResponse,
  SampleCancelInput,
  SampleCreatedResponse,
  SampleCreateInput,
  SampleDetail,
  SampleEventItem,
  SampleLabelData,
  SampleListFilter,
  SampleListResponse,
  SampleRejectInput,
  SampleTransfer,
  SampleTransferInput,
  TransferDirection,
  TransferExceptionsResponse,
} from "./types";

export const sampleService = {
  /**
   * List accessions with status, search and branch filters
   */
  async listSamples(
    filters: SampleListFilter = {},
    signal?: AbortSignal,
  ): Promise<SampleListResponse> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (filters.q) query.q = filters.q;
    if (filters.status && filters.status !== "all") {
      query.status = filters.status;
    }
    if (filters.branch_id && filters.branch_id !== "all") {
      query.branch_id = filters.branch_id;
    }
    if (filters.limit) query.limit = filters.limit;
    if (filters.order) query.order = filters.order;

    try {
      const data = await apiRequest<
        | {
            results?: SampleDetail[];
            total?: number;
          }
        | SampleDetail[]
      >("/samples", { query, signal });

      if (Array.isArray(data)) {
        return { results: data, total: data.length };
      }
      if (data && Array.isArray(data.results)) {
        return {
          results: data.results,
          total: data.total ?? data.results.length,
        };
      }
      return { results: [], total: 0 };
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch samples (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * A2: ordered tests with no live sample yet (derived server-side).
   */
  async listAwaitingCollection(
    signal?: AbortSignal,
  ): Promise<AwaitingCollectionResponse> {
    return apiRequest<AwaitingCollectionResponse>("/samples", {
      query: { status: "awaiting_collection" },
      signal,
    });
  },

  /**
   * Get full sample detail by UUID (Doc 03 §5.4, GET /api/v1/samples/{id}).
   */
  async getSample(sampleId: string): Promise<SampleDetail> {
    try {
      return await apiRequest<SampleDetail>(`/samples/${sampleId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Sample not found (${err.status})`);
      }
      throw err;
    }
  },

  /**
   * Accession / collect specimen (SM-1..SM-3, POST /api/v1/samples)
   */
  async collectSample(
    input: SampleCreateInput,
  ): Promise<SampleCreatedResponse> {
    const body: Record<string, unknown> = {
      invoice_id: input.invoice_id,
    };
    if (input.invoice_item_ids && input.invoice_item_ids.length > 0) {
      body.invoice_item_ids = input.invoice_item_ids;
    }
    if (input.notes && input.notes.trim().length > 0) {
      body.notes = input.notes.trim();
    }
    try {
      return await apiRequest<SampleCreatedResponse>("/samples", {
        method: "POST",
        body,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Collection failed (${err.status})`);
      }
      throw err;
    }
  },

  /**
   * Explicit print action creating an audit record (D8, POST /api/v1/samples/{id}/label/print)
   */
  async printLabel(sampleId: string): Promise<SampleLabelData> {
    try {
      return await apiRequest<SampleLabelData>(
        `/samples/${sampleId}/label/print`,
        {
          method: "POST",
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to print sample label (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Fetch stored barcode label payload (SM-4, GET /api/v1/samples/{id}/label)
   */
  async getLabel(sampleId: string): Promise<SampleLabelData> {
    try {
      return await apiRequest<SampleLabelData>(`/samples/${sampleId}/label`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch sample label (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Receive specimen into laboratory (SM-7, POST /api/v1/samples/{id}/receive)
   */
  async receiveSample(sampleId: string): Promise<SampleCreatedResponse> {
    try {
      return await apiRequest<SampleCreatedResponse>(
        `/samples/${sampleId}/receive`,
        {
          method: "POST",
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to receive sample (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Reject specimen for quality non-conformance (SM-8, POST /api/v1/samples/{id}/reject)
   */
  async rejectSample(
    sampleId: string,
    input: SampleRejectInput,
  ): Promise<SampleCreatedResponse> {
    try {
      return await apiRequest<SampleCreatedResponse>(
        `/samples/${sampleId}/reject`,
        {
          method: "POST",
          body: input,
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to reject sample (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Issue fresh accession for rejected sample (SM-9, POST /api/v1/samples/{id}/recollect)
   */
  async recollectSample(sampleId: string): Promise<SampleCreatedResponse> {
    try {
      return await apiRequest<SampleCreatedResponse>(
        `/samples/${sampleId}/recollect`,
        {
          method: "POST",
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to trigger recollection (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Cancel specimen accession (POST /api/v1/samples/{id}/cancel)
   */
  async cancelSample(
    sampleId: string,
    input: SampleCancelInput,
  ): Promise<SampleCreatedResponse> {
    try {
      return await apiRequest<SampleCreatedResponse>(
        `/samples/${sampleId}/cancel`,
        {
          method: "POST",
          body: input,
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to cancel sample (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Transfer specimen to another branch (SM-7, POST /api/v1/samples/{id}/transfer)
   */
  async transferSample(
    sampleId: string,
    input: SampleTransferInput,
  ): Promise<{ id: string; status: string }> {
    try {
      return await apiRequest<{ id: string; status: string }>(
        `/samples/${sampleId}/transfer`,
        {
          method: "POST",
          body: input,
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to transfer sample (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Fetch chain-of-custody audit event timeline (GET /api/v1/samples/{id}/events)
   */
  async getEvents(sampleId: string): Promise<SampleEventItem[]> {
    try {
      const data = await apiRequest<
        SampleEventItem[] | { results: SampleEventItem[] }
      >(`/samples/${sampleId}/events`);
      return Array.isArray(data) ? data : data.results || [];
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch events (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * List transfers with status and direction filters (D12, GET /api/v1/transfers)
   */
  async listTransfers(
    params?: {
      status?: string;
      direction?: TransferDirection;
    },
    signal?: AbortSignal,
  ): Promise<{ results: SampleTransfer[]; total: number }> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (params?.status) query.status = params.status;
    if (params?.direction) query.direction = params.direction;

    try {
      return await apiRequest<{ results: SampleTransfer[]; total: number }>(
        "/transfers",
        { query, signal },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch transfers (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Receive specimen transfer at destination (SM-7, POST /api/v1/transfers/{id}/receive)
   */
  async receiveTransfer(transferId: string): Promise<SampleTransfer> {
    try {
      return await apiRequest<SampleTransfer>(
        `/transfers/${transferId}/receive`,
        {
          method: "POST",
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to receive transfer (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Cancel specimen transfer (POST /api/v1/transfers/{id}/cancel)
   */
  async cancelTransfer(transferId: string): Promise<SampleTransfer> {
    try {
      return await apiRequest<SampleTransfer>(
        `/transfers/${transferId}/cancel`,
        {
          method: "POST",
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to cancel transfer (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Mark specimen transfer as lost (SM-7, POST /api/v1/transfers/{id}/mark-lost)
   */
  async markLostTransfer(
    transferId: string,
    note: string,
  ): Promise<SampleTransfer> {
    try {
      return await apiRequest<SampleTransfer>(
        `/transfers/${transferId}/mark-lost`,
        {
          method: "POST",
          body: { note },
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to mark transfer lost (${err.status})`,
        );
      }
      throw err;
    }
  },

  /**
   * Fetch transfer exceptions (late, lost, route health) (GET /api/v1/transfers/exceptions)
   */
  async getTransferExceptions(
    params?: {
      report?: string;
      from?: string;
      to?: string;
      month?: string;
    },
    signal?: AbortSignal,
  ): Promise<TransferExceptionsResponse> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (params?.report) query.report = params.report;
    if (params?.from) query.from = params.from;
    if (params?.to) query.to = params.to;
    if (params?.month) query.month = params.month;

    try {
      return await apiRequest<TransferExceptionsResponse>(
        "/transfers/exceptions",
        { query, signal },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch transfer exceptions (${err.status})`,
        );
      }
      throw err;
    }
  },
};
