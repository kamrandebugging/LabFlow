/**
 * Staff CRUD API service (Owner-only).
 * Every mutation is audited server-side; the client never sends a tenant id.
 */

import { apiRequest } from "../../lib/apiClient";
import type {
  CreateStaffInput,
  StaffDetail,
  StaffListResponse,
  StaffRow,
  StaffTempPasswordResponse,
  UpdateStaffInput,
} from "./types";

export const staffService = {
  list(
    params: {
      cursor?: string | null;
      limit?: number;
      q?: string;
      status?: "" | "active" | "deactivated";
      role?: string;
    } = {},
  ): Promise<StaffListResponse> {
    return apiRequest<StaffListResponse>("/staff", {
      query: {
        cursor: params.cursor,
        limit: params.limit ?? 50,
        q: params.q,
        status: params.status || undefined,
        role: params.role || undefined,
      },
    });
  },

  get(id: string): Promise<StaffDetail> {
    return apiRequest<StaffDetail>(`/staff/${id}`);
  },

  create(payload: CreateStaffInput): Promise<StaffTempPasswordResponse> {
    return apiRequest<StaffTempPasswordResponse>("/staff", {
      method: "POST",
      body: payload,
    });
  },

  update(id: string, payload: UpdateStaffInput): Promise<StaffRow> {
    return apiRequest<StaffRow>(`/staff/${id}`, {
      method: "PATCH",
      body: payload,
    });
  },

  deactivate(id: string): Promise<StaffRow> {
    return apiRequest<StaffRow>(`/staff/${id}/deactivate`, {
      method: "POST",
      body: {},
    });
  },

  reactivate(id: string): Promise<StaffRow> {
    return apiRequest<StaffRow>(`/staff/${id}/reactivate`, {
      method: "POST",
      body: {},
    });
  },

  resetPassword(id: string): Promise<StaffTempPasswordResponse> {
    return apiRequest<StaffTempPasswordResponse>(
      `/staff/${id}/reset-password`,
      { method: "POST", body: {} },
    );
  },

  resetTotp(id: string): Promise<{ staff: StaffRow; totp_enabled: boolean }> {
    return apiRequest<{ staff: StaffRow; totp_enabled: boolean }>(
      `/staff/${id}/reset-totp`,
      { method: "POST", body: {} },
    );
  },

  listPasswordRequests(): Promise<{
    requests: Array<{
      id: string;
      email: string;
      display_name: string;
      status: string;
      created_at: string;
    }>;
  }> {
    return apiRequest("/staff/password-requests");
  },

  resolvePasswordRequest(id: string): Promise<{ id: string; status: string }> {
    return apiRequest(`/staff/password-requests/${id}/resolve`, {
      method: "POST",
      body: {},
    });
  },
};
