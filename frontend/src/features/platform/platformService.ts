/**
 * Platform dashboard data access — all reads/writes for the Phase 1 screens.
 * Every call rides on the shared api client with the platform session.
 */

import { apiRequest } from "../../lib/apiClient";
import type {
  AuditListResponse,
  OverviewMetrics,
  ProvisionTenantPayload,
  ProvisionTenantResult,
  TenantDetail,
  TenantListParams,
  TenantListResponse,
  TenantPlan,
} from "./types";

export const platformService = {
  getOverview(): Promise<OverviewMetrics> {
    return apiRequest<OverviewMetrics>("/platform/metrics/overview", {
      session: "platform",
    });
  },

  listTenants(params: TenantListParams): Promise<TenantListResponse> {
    return apiRequest<TenantListResponse>("/platform/tenants", {
      session: "platform",
      query: {
        q: params.q,
        status: params.status,
        cursor: params.cursor,
        limit: params.limit,
      },
    });
  },

  getTenant(id: string): Promise<TenantDetail> {
    return apiRequest<TenantDetail>(`/platform/tenants/${id}`, {
      session: "platform",
    });
  },

  getTenantAudit(id: string): Promise<AuditListResponse> {
    return apiRequest<AuditListResponse>("/platform/audit", {
      session: "platform",
      query: { entity_type: "tenant", entity_id: id, limit: 20 },
    });
  },

  listPlans(): Promise<{ plans: TenantPlan[] }> {
    return apiRequest<{ plans: TenantPlan[] }>("/platform/plans", {
      session: "platform",
    });
  },

  provisionTenant(
    payload: ProvisionTenantPayload,
  ): Promise<ProvisionTenantResult> {
    return apiRequest<ProvisionTenantResult>("/platform/tenants", {
      method: "POST",
      session: "platform",
      body: payload,
    });
  },

  suspendTenant(id: string, reason: string): Promise<TenantDetail> {
    return apiRequest<TenantDetail>(`/platform/tenants/${id}/suspend`, {
      method: "POST",
      session: "platform",
      body: { reason },
    });
  },

  reactivateTenant(id: string): Promise<TenantDetail> {
    return apiRequest<TenantDetail>(`/platform/tenants/${id}/reactivate`, {
      method: "POST",
      session: "platform",
      body: {},
    });
  },

  offboardTenant(id: string): Promise<TenantDetail> {
    return apiRequest<TenantDetail>(`/platform/tenants/${id}/offboard`, {
      method: "POST",
      session: "platform",
      body: {},
    });
  },

  retryProvisioning(id: string): Promise<TenantDetail> {
    return apiRequest<TenantDetail>(
      `/platform/tenants/${id}/retry-provisioning`,
      {
        method: "POST",
        session: "platform",
        body: {},
      },
    );
  },

  resendActivation(id: string): Promise<{ detail?: string }> {
    return apiRequest<{ detail?: string }>(
      `/platform/tenants/${id}/resend-activation`,
      { method: "POST", session: "platform", body: {} },
    );
  },
};
