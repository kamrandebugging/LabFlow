/**
 * Platform dashboard data access — all reads/writes for the Phase 1 screens.
 * Every call rides on the shared api client with the platform session.
 */

import { apiRequest } from "../../lib/apiClient";
import type {
  AccessControlData,
  AccessControlPayload,
  AuditListResponse,
  DemoRequestItem,
  DemoRequestListResponse,
  MarkPaidPayload,
  OverviewMetrics,
  PlatformHealthResponse,
  PlatformSettingsResponse,
  ProvisionTenantPayload,
  ProvisionTenantResult,
  SubscriptionDetailResponse,
  SubscriptionListResponse,
  TenantDetail,
  TenantListParams,
  TenantListResponse,
  TenantPlan,
  UsersListResponse,
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

  /* =======================================================================
   * Phase 2 Methods
   * ======================================================================= */

  listSubscriptions(params?: {
    status?: string;
    plan_id?: string;
    q?: string;
  }): Promise<SubscriptionListResponse> {
    return apiRequest<SubscriptionListResponse>("/platform/subscriptions", {
      session: "platform",
      query: params,
    });
  },

  getSubscription(id: string): Promise<SubscriptionDetailResponse> {
    return apiRequest<SubscriptionDetailResponse>(
      `/platform/subscriptions/${id}`,
      {
        session: "platform",
      },
    );
  },

  markSubscriptionPaid(
    id: string,
    payload: MarkPaidPayload,
    totpCode: string,
  ): Promise<{ detail: string; payment_id: string; next_due: string | null }> {
    return apiRequest<{
      detail: string;
      payment_id: string;
      next_due: string | null;
    }>(`/platform/subscriptions/${id}/mark-paid`, {
      method: "POST",
      session: "platform",
      headers: { "X-Platform-TOTP": totpCode },
      body: payload,
    });
  },

  changeSubscriptionPlan(
    id: string,
    planId: string,
    totpCode: string,
  ): Promise<{ detail: string; plan: TenantPlan }> {
    return apiRequest<{ detail: string; plan: TenantPlan }>(
      `/platform/subscriptions/${id}/change-plan`,
      {
        method: "POST",
        session: "platform",
        headers: { "X-Platform-TOTP": totpCode },
        body: { plan_id: planId },
      },
    );
  },

  getAccessControl(tenantId: string): Promise<AccessControlData> {
    return apiRequest<AccessControlData>(`/platform/access/${tenantId}`, {
      session: "platform",
    });
  },

  updateAccessControl(
    tenantId: string,
    payload: AccessControlPayload,
    totpCode: string,
  ): Promise<AccessControlData> {
    return apiRequest<AccessControlData>(`/platform/access/${tenantId}`, {
      method: "PUT",
      session: "platform",
      headers: { "X-Platform-TOTP": totpCode },
      body: payload,
    });
  },

  listUsers(q?: string): Promise<UsersListResponse> {
    return apiRequest<UsersListResponse>("/platform/users", {
      session: "platform",
      query: { q },
    });
  },

  invitePlatformUser(
    email: string,
    role: string,
    totpCode: string,
  ): Promise<{ detail: string; invitation: unknown }> {
    return apiRequest<{ detail: string; invitation: unknown }>(
      "/platform/users/invite",
      {
        method: "POST",
        session: "platform",
        headers: { "X-Platform-TOTP": totpCode },
        body: { email, role },
      },
    );
  },

  disablePlatformUser(
    id: string,
    totpCode: string,
  ): Promise<{ detail: string; is_active: boolean }> {
    return apiRequest<{ detail: string; is_active: boolean }>(
      `/platform/users/${id}/disable`,
      {
        method: "POST",
        session: "platform",
        headers: { "X-Platform-TOTP": totpCode },
        body: {},
      },
    );
  },

  listDemoRequests(
    status?: string,
    q?: string,
  ): Promise<DemoRequestListResponse> {
    return apiRequest<DemoRequestListResponse>("/platform/demo-requests", {
      session: "platform",
      query: { status, q },
    });
  },

  getDemoRequest(id: string): Promise<DemoRequestItem> {
    return apiRequest<DemoRequestItem>(`/platform/demo-requests/${id}`, {
      session: "platform",
    });
  },

  updateDemoRequest(
    id: string,
    payload: { status?: string; notes?: string },
    totpCode?: string,
  ): Promise<DemoRequestItem> {
    return apiRequest<DemoRequestItem>(`/platform/demo-requests/${id}`, {
      method: "PATCH",
      session: "platform",
      headers: totpCode ? { "X-Platform-TOTP": totpCode } : undefined,
      body: payload,
    });
  },

  convertDemoRequest(
    id: string,
    tenantId: string,
    totpCode: string,
  ): Promise<DemoRequestItem> {
    return apiRequest<DemoRequestItem>(
      `/platform/demo-requests/${id}/convert`,
      {
        method: "POST",
        session: "platform",
        headers: { "X-Platform-TOTP": totpCode },
        body: { tenant_id: tenantId },
      },
    );
  },

  getHealth(): Promise<PlatformHealthResponse> {
    return apiRequest<PlatformHealthResponse>("/platform/health", {
      session: "platform",
    });
  },

  retryFailure(
    id: string,
    totpCode?: string,
  ): Promise<{ detail: string; failure_id: string }> {
    return apiRequest<{ detail: string; failure_id: string }>(
      `/platform/health/failures/${id}/retry`,
      {
        method: "POST",
        session: "platform",
        headers: totpCode ? { "X-Platform-TOTP": totpCode } : undefined,
        body: {},
      },
    );
  },

  getAuditLog(params?: {
    action?: string;
    tenant_id?: string;
    entity_type?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
  }): Promise<AuditListResponse> {
    return apiRequest<AuditListResponse>("/platform/audit", {
      session: "platform",
      query: params,
    });
  },

  getSettings(): Promise<PlatformSettingsResponse> {
    return apiRequest<PlatformSettingsResponse>("/platform/settings", {
      session: "platform",
    });
  },

  updateSettings(
    payload: Partial<PlatformSettingsResponse>,
    totpCode: string,
  ): Promise<PlatformSettingsResponse> {
    return apiRequest<PlatformSettingsResponse>("/platform/settings", {
      method: "PUT",
      session: "platform",
      headers: { "X-Platform-TOTP": totpCode },
      body: payload,
    });
  },
};
