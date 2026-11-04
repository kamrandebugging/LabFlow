/**
 * Unit tests for resultsService (frontend/src/features/results/resultsService.ts).
 * Tests all API methods, JWT bearer token injection, headers, error handling, and data transformation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { resultsService } from "../../features/results/resultsService";
import { useAuthStore } from "../../features/auth/authStore";
import { sampleService } from "../../features/samples/sampleService";

describe("resultsService unit tests", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "test-jwt-token-123",
      isAuthenticated: true,
      user: {
        id: "usr-tech-01",
        email: "tech@labflow.pk",
        name: "Usman Tariq",
        role: "technician",
        branch_ids: ["br-01"],
      },
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("submits batch results with JWT bearer token", async () => {
    const mockResponse = {
      message: "Results submitted successfully",
      count: 2,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const rows = [
      { test_id: "test-01", value: "13.5", unit: "g/dL", flag: "normal" as const },
      { test_id: "test-02", value: "8500", unit: "/uL", flag: "normal" as const },
    ];

    const res = await resultsService.submitResults("smp-123", rows);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/samples/smp-123/results",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer test-jwt-token-123",
        }),
        body: JSON.stringify({ results: rows }),
      }),
    );
    expect(res).toEqual(mockResponse);
  });

  it("approves result via POST /api/v1/results/:id/approve", async () => {
    const mockResponse = {
      id: "res-01",
      status: "approved",
      approved_by: "usr-path-01",
      approved_at: "2026-10-20T10:00:00Z",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const res = await resultsService.approveResult("res-01", {
      decision: "approved",
      note: "Clinically correlated.",
      range_override: false,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/results/res-01/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          decision: "approved",
          note: "Clinically correlated.",
          range_override: false,
        }),
      }),
    );
    expect(res).toEqual(mockResponse);
  });

  it("amends result via POST /api/v1/results/:id/amend with mandatory reason", async () => {
    const mockResponse = {
      id: "res-01",
      status: "amended",
      amended_by: "usr-tech-01",
      amended_at: "2026-10-20T11:00:00Z",
      version: 2,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const res = await resultsService.amendResult("res-01", {
      value: "14.2",
      reason: "Transcription typo corrected per bench analyzer log.",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/results/res-01/amend",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          value: "14.2",
          reason: "Transcription typo corrected per bench analyzer log.",
        }),
      }),
    );
    expect(res).toEqual(mockResponse);
  });

  it("withdraws result via POST /api/v1/results/:id/withdraw", async () => {
    const mockResponse = {
      id: "res-01",
      status: "withdrawn",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const res = await resultsService.withdrawResult("res-01", "Sample clotted upon re-run");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/results/res-01/withdraw",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "Sample clotted upon re-run" }),
      }),
    );
    expect(res).toEqual(mockResponse);
  });

  it("records critical notification via POST /api/v1/results/:id/critical-notifications", async () => {
    const mockResponse = {
      id: "notif-01",
      result_id: "res-01",
      read_back_confirmed: true,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const res = await resultsService.recordCriticalNotification("res-01", {
      notified_name: "Dr. Farhan",
      notified_at: "2026-10-20T10:15:00Z",
      read_back: true,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/results/res-01/critical-notifications",
      expect.objectContaining({
        method: "POST",
      }),
    );
    expect(res).toEqual(mockResponse);
  });

  it("throws friendly error message on 400 Bad Request or API error", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: "Mandatory clinical justification is required for critical results.",
      }),
    });

    await expect(
      resultsService.approveResult("res-01", { decision: "approved" }),
    ).rejects.toThrow(/Mandatory clinical justification is required for critical results./i);
  });

  it("handles non-JSON error responses gracefully", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error("HTML error page");
      },
    });

    await expect(
      resultsService.approveResult("res-01", { decision: "approved" }),
    ).rejects.toThrow(/Server error \(502\)/i);
  });

  it("derives worklist correctly from sampleService with oldest first sorting", async () => {
    vi.spyOn(sampleService, "listSamples").mockResolvedValueOnce({
      total: 3,
      results: [
        {
          id: "smp-02",
          accession_id: "CDL002",
          invoice_id: "inv-02",
          patient_id: "pat-02",
          patient_name: "Fatima Noor",
          patient_mrn: "MRN-002",
          branch_id: "br-01",
          branch_name: "Gulberg",
          status: "in_process",
          tests: ["Potassium (K+)"],
          collected_at: "2026-10-20T10:00:00Z",
        },
        {
          id: "smp-01",
          accession_id: "CDL001",
          invoice_id: "inv-01",
          patient_id: "pat-01",
          patient_name: "Muhammad Imran",
          patient_mrn: "MRN-001",
          branch_id: "br-01",
          branch_name: "Gulberg",
          status: "received",
          tests: ["CBC"],
          collected_at: "2026-10-20T08:00:00Z",
        },
        {
          id: "smp-03",
          accession_id: "CDL003",
          invoice_id: "inv-03",
          patient_id: "pat-03",
          patient_name: "Ahmed Ali",
          patient_mrn: "MRN-003",
          branch_id: "br-01",
          branch_name: "Gulberg",
          status: "ready", // ready is not in ["collected", "received", "in_process", "rejected"]
          tests: ["Lipid Profile"],
          collected_at: "2026-10-20T07:00:00Z",
        },
      ],
    });

    const worklist = await resultsService.getWorklist({ branchId: "br-01", statusFilter: "all" });

    // Should contain smp-01 and smp-02, sorted oldest first (08:00 before 10:00)
    expect(worklist).toHaveLength(2);
    expect(worklist[0]!.sample_id).toBe("smp-01");
    expect(worklist[0]!.status).toBe("ready");
    expect(worklist[1]!.sample_id).toBe("smp-02");
    expect(worklist[1]!.status).toBe("in_process");
  });

  it("derives approvals queue prioritizing critical items", async () => {
    vi.spyOn(sampleService, "listSamples").mockResolvedValueOnce({
      total: 2,
      results: [
        {
          id: "smp-01",
          accession_id: "CDL001",
          invoice_id: "inv-01",
          patient_id: "pat-01",
          patient_name: "Muhammad Imran",
          patient_mrn: "MRN-001",
          branch_id: "br-01",
          branch_name: "Gulberg",
          status: "in_process",
          tests: ["Routine Glucose"],
          collected_at: "2026-10-20T08:00:00Z",
        },
        {
          id: "smp-02",
          accession_id: "CDL002",
          invoice_id: "inv-02",
          patient_id: "pat-02",
          patient_name: "Fatima Noor",
          patient_mrn: "MRN-002",
          branch_id: "br-01",
          branch_name: "Gulberg",
          status: "in_process",
          tests: ["Potassium (K+)"], // Critical!
          collected_at: "2026-10-20T09:00:00Z",
        },
      ],
    });

    const queue = await resultsService.getApprovalsQueue();

    // Critical potassium should be sorted first despite being collected later
    expect(queue).toHaveLength(2);
    expect(queue[0]!.test_name).toBe("Potassium (K+)");
    expect(queue[0]!.is_critical).toBe(true);
    expect(queue[1]!.test_name).toBe("Routine Glucose");
    expect(queue[1]!.is_critical).toBe(false);
  });

  it("fetches result detail and generates honest detail record", async () => {
    vi.spyOn(sampleService, "getSample").mockResolvedValueOnce({
      id: "smp-01",
      accession_id: "CDL001",
      invoice_id: "inv-01",
      patient_id: "pat-01",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-001",
      patient_sex: "M",
      patient_age_years: 34,
      branch_id: "br-01",
      branch_name: "Gulberg",
      status: "in_process",
      tests: ["Potassium (K+)"],
      collected_at: "2026-10-20T08:00:00Z",
      collected_by: "usr-tech-01",
      sample_tests: [],
    });

    const detail = await resultsService.getResultDetail("smp-01-res-1");

    expect(detail).not.toBeNull();
    expect(detail?.sample_id).toBe("smp-01");
    expect(detail?.test_name).toBe("Potassium (K+)");
    expect(detail?.is_critical).toBe(true);
    expect(detail?.value).toBe("6.8");
  });

  it("returns null when sample is not found in getResultDetail", async () => {
    vi.spyOn(sampleService, "getSample").mockResolvedValueOnce(null as any);

    const detail = await resultsService.getResultDetail("unknown-id");
    expect(detail).toBeNull();
  });
});
