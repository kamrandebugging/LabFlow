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

function toServiceError(err: unknown, defaultMessage: string): Error {
  if (err instanceof ApiError) {
    const error = new Error(err.message || defaultMessage);
    (error as Error & { code?: string; status?: number }).code =
      err.code ?? undefined;
    (error as Error & { code?: string; status?: number }).status = err.status;
    return error;
  }
  return err instanceof Error ? err : new Error(defaultMessage);
}

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
      throw toServiceError(err, "Failed to fetch samples");
    }
  },

  /**
   * A2: ordered tests with no live sample yet (derived server-side).
   */
  async listAwaitingCollection(
    signal?: AbortSignal,
  ): Promise<AwaitingCollectionResponse> {
    try {
      return await apiRequest<AwaitingCollectionResponse>("/samples", {
        query: { status: "awaiting_collection" },
        signal,
      });
    } catch (err) {
      throw toServiceError(err, "Failed to fetch awaiting collection");
    }
  },

  /**
   * Get full sample detail by UUID (Doc 03 §5.4, GET /api/v1/samples/{id}).
   */
  async getSample(sampleId: string): Promise<SampleDetail> {
    try {
      return await apiRequest<SampleDetail>(`/samples/${sampleId}`);
    } catch (err) {
      throw toServiceError(err, "Sample not found");
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
      throw toServiceError(err, "Collection failed");
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
      throw toServiceError(err, "Failed to print sample label");
    }
  },

  /**
   * Fetch stored barcode label payload (SM-4, GET /api/v1/samples/{id}/label)
   */
  async getLabel(sampleId: string): Promise<SampleLabelData> {
    try {
      return await apiRequest<SampleLabelData>(`/samples/${sampleId}/label`);
    } catch (err) {
      throw toServiceError(err, "Failed to fetch sample label");
    }
  },

  /**
   * Fetch stored barcode label payloads for multiple samples without auditing
   */
  async getLabelsBulk(sampleIds: string[]): Promise<SampleLabelData[]> {
    try {
      const qs = encodeURIComponent(sampleIds.join(","));
      const data = await apiRequest<{ labels: SampleLabelData[] }>(
        `/samples/labels?ids=${qs}`,
      );
      return data.labels;
    } catch (err) {
      throw toServiceError(err, "Failed to fetch sample labels");
    }
  },

  /**
   * Explicit bulk print creating 1 sample.label_printed audit row per sample
   */
  async printLabelsBulk(sampleIds: string[]): Promise<SampleLabelData[]> {
    try {
      const data = await apiRequest<{ labels: SampleLabelData[] }>(
        "/samples/labels/print",
        {
          method: "POST",
          body: { sample_ids: sampleIds },
        },
      );
      return data.labels;
    } catch (err) {
      throw toServiceError(err, "Failed to print sample labels");
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
      throw toServiceError(err, "Failed to receive sample");
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
      throw toServiceError(err, "Failed to reject sample");
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
      throw toServiceError(err, "Failed to trigger recollection");
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
      throw toServiceError(err, "Failed to cancel sample");
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
      throw toServiceError(err, "Failed to transfer sample");
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
      throw toServiceError(err, "Failed to fetch events");
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
      throw toServiceError(err, "Failed to fetch transfers");
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
      throw toServiceError(err, "Failed to receive transfer");
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
      throw toServiceError(err, "Failed to cancel transfer");
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
      throw toServiceError(err, "Failed to mark transfer lost");
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
      throw toServiceError(err, "Failed to fetch transfer exceptions");
    }
  },
};
