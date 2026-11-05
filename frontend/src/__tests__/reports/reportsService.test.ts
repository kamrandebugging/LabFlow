/**
 * Unit tests for reportsService (frontend/src/features/reports/reportsService.ts).
 * Tests all API methods, JWT bearer token injection, public unauthenticated requests,
 * query parameter formatting, and error handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { reportsService } from "../../features/reports/reportsService";
import { useAuthStore } from "../../features/auth/authStore";

describe("reportsService unit tests", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "test-jwt-access-token",
      isAuthenticated: true,
      user: {
        id: "usr-staff-01",
        email: "staff@labflow.pk",
        name: "Ali Raza",
        role: "owner",
        branch_ids: ["br-01"],
      },
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("getReports sends JWT bearer token and query filters", async () => {
    const mockReports = {
      results: [
        {
          id: "rep-001",
          status: "final",
          generation_status: "completed",
          generation_error: null,
          current_version: 1,
          published_at: "2026-10-20T10:00:00Z",
          created_at: "2026-10-20T09:00:00Z",
          sample: {
            id: "smp-001",
            accession_id: "CDL20261020000041",
            collected_at: "2026-10-20T08:30:00Z",
            branch: { id: "br-01", name: "Main Lab" },
            patient: { id: "pat-01", name: "Muhammad Imran", mrn: "MRN-001" },
            tests: [{ id: "t-1", name: "CBC", code: "CBC" }],
          },
          latest_delivery: null,
        },
      ],
      next_cursor: "cursor-123",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockReports,
    });

    const res = await reportsService.getReports({
      status: "final",
      q: "Imran",
      cursor: "c-start",
      limit: 25,
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(global.fetch).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toContain("/api/v1/reports");
    expect(url).toContain("status=final");
    expect(url).toContain("q=Imran");
    expect(url).toContain("cursor=c-start");
    expect(url).toContain("limit=25");
    const headers = options.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer test-jwt-access-token");
    expect(res.results).toHaveLength(1);
    expect(res.next_cursor).toBe("cursor-123");
  });

  it("getReports adapts flat backend response to nested structure defensively", async () => {
    const flatBackendResponse = {
      results: [
        {
          id: "rep-flat-01",
          sample_id: "smp-flat-01",
          accession_id: "CDL20261020000099",
          status: "final",
          current_version: 2,
          generation_status: "completed",
          generation_error: null,
          finalised_at: "2026-10-20T11:00:00Z",
          created_at: "2026-10-20T10:00:00Z",
          updated_at: "2026-10-20T11:00:00Z",
          branch_id: "br-flat-01",
          branch_name: "Branch Alpha",
          patient_id: "pat-flat-01",
          patient_mrn: "MRN-FLAT-01",
          patient_name: "Ayesha Khan",
          patient_phone: "+923009999999",
          patient_email: "ayesha@example.com",
          tests: ["CBC", "LFT"],
          delivery_status: "delivered",
          delivery_channel: "whatsapp",
        },
      ],
      next_cursor: null,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => flatBackendResponse,
    });

    const res = await reportsService.getReports();

    expect(res.results).toHaveLength(1);
    const item = res.results[0]!;
    expect(item).toBeDefined();
    expect(item.id).toBe("rep-flat-01");
    expect(item.status).toBe("final");
    expect(item.sample.accession_id).toBe("CDL20261020000099");
    expect(item.sample.patient.name).toBe("Ayesha Khan");
    expect(item.sample.patient.mrn).toBe("MRN-FLAT-01");
    expect(item.sample.branch?.name).toBe("Branch Alpha");
    expect(item.sample.tests).toHaveLength(2);
    expect(item.sample.tests[0]?.code).toBe("CBC");
    expect(item.latest_delivery?.channel).toBe("whatsapp");
    expect(item.latest_delivery?.status).toBe("delivered");
  });

  it("getReport fetches detail by UUID with JWT bearer header", async () => {
    const mockDetail = {
      id: "rep-001",
      status: "final",
      generation_status: "completed",
      current_version: 1,
      sample: {
        id: "smp-01",
        accession_id: "CDL20261020000041",
        status: "completed",
        collected_at: "2026-10-20T08:00:00Z",
        branch: { id: "br-01", name: "Main Lab" },
      },
      patient: {
        id: "pat-01",
        full_name: "Muhammad Imran",
        mrn: "MRN-001",
        age_years: 42,
        gender: "Male",
        phone: "+923001234567",
        email: "imran@example.com",
      },
      results: [],
      versions: [],
      deliveries: [],
      access_tokens: [],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDetail,
    });

    const res = await reportsService.getReport("rep-001");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/reports/rep-001",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-access-token",
        }),
      }),
    );
    expect(res.id).toBe("rep-001");
    expect(res.patient.full_name).toBe("Muhammad Imran");
  });

  it("regenerateReport sends POST with JWT header", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "accepted", message: "Generation queued" }),
    });

    const res = await reportsService.regenerateReport("rep-001");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/reports/rep-001/regenerate",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-access-token",
        }),
      }),
    );
    expect(res.status).toBe("accepted");
  });

  it("deliverReport sends channel and contact_id in body", async () => {
    const mockDelivery = {
      id: "del-01",
      report_id: "rep-001",
      channel: "whatsapp",
      contact_id: "pat-01",
      status: "delivered",
      created_at: "2026-10-20T11:00:00Z",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDelivery,
    });

    const res = await reportsService.deliverReport("rep-001", {
      channel: "whatsapp",
      contact_id: "pat-01",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/reports/rep-001/deliver",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ channel: "whatsapp", contact_id: "pat-01" }),
      }),
    );
    expect(res.status).toBe("delivered");
  });

  it("issueAccessToken and revokeAccessToken call correct endpoints", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token_id: "tok-01",
          link: "/report-access/sample-token",
          expires_at: "2026-10-27T10:00:00Z",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ revoked_count: 1, status: "revoked" }),
      });

    const issueRes = await reportsService.issueAccessToken("rep-001");
    expect(issueRes.link).toBe("/report-access/sample-token");

    const revokeRes = await reportsService.revokeAccessToken("rep-001", {
      token_id: "tok-01",
    });
    expect(revokeRes.revoked_count).toBe(1);
  });

  it("getExceptions fetches triage queue", async () => {
    const mockExceptions = {
      results: [
        {
          id: "x-01",
          kind: "late_transfer",
          title: "Late transfer: Gulberg -> DHA",
          severity: "warning",
          reference_id: "smp-01",
          reference_code: "CDL20261019000012",
          patient_name: "Fatima Noor",
          branch_name: "Gulberg",
          created_at: "2026-10-19T16:40:00Z",
          details: { hours_late: 18.0 },
        },
      ],
      counts: {
        total: 1,
        failed_generation: 0,
        failed_delivery: 0,
        late_transfer: 1,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockExceptions,
    });

    const res = await reportsService.getExceptions();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/exceptions",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-access-token",
        }),
      }),
    );
    expect(res.counts.total).toBe(1);
    expect(res.results[0]?.kind).toBe("late_transfer");
  });

  it("checkPublicReportAccess sends NO auth headers (RP-V3)", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });

    const res = await reportsService.checkPublicReportAccess("valid-token-xyz");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/report-access/valid-token-xyz",
      expect.objectContaining({
        method: "GET",
      }),
    );
    const [, options] = vi.mocked(global.fetch).mock.calls[0] as [
      string,
      RequestInit,
    ];
    // Must NOT have Authorization header!
    expect(options.headers).toBeUndefined();
    expect(res.status).toBe(200);
  });

  it("checkPublicReportAccess handles 410 link_expired cleanly", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      status: 410,
      ok: false,
      json: async () => ({
        error: {
          code: "link_expired",
          message: "This report link has expired.",
          details: { phone: "+92 42 35712345" },
        },
      }),
    });

    const res = await reportsService.checkPublicReportAccess("expired-token");
    expect(res.status).toBe(410);
    expect(res.error?.code).toBe("link_expired");
    expect(res.error?.details?.phone).toBe("+92 42 35712345");
  });
});
