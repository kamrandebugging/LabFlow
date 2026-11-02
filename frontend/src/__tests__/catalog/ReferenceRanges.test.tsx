import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { catalogService } from "@/features/catalog/catalogService";
import type {
  ReferenceRange,
  ReferenceRangeCreateInput,
} from "@/features/catalog/types";

const sampleRange: ReferenceRange = {
  id: "range-001",
  test_id: "test-001",
  sex: "M",
  age_min_days: 0,
  age_max_days: 365,
  low: "13.500",
  high: "17.500",
  critical_low: "7.000",
  critical_high: "20.000",
  unit: "g/dL",
  effective_from: "2026-01-01",
  effective_to: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const createInput: ReferenceRangeCreateInput = {
  sex: "M",
  age_min_days: 0,
  age_max_days: 365,
  low: "13.500",
  high: "17.500",
  critical_low: "7.000",
  critical_high: "20.000",
  unit: "g/dL",
  effective_from: "2026-01-01",
  effective_to: null,
};

function mockFetchOnce(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("KAN-119: Reference range service (catalogService)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listTestRanges calls GET /api/v1/tests/{id}/ranges", async () => {
    mockFetchOnce(200, [sampleRange]);

    const ranges = await catalogService.listTestRanges("test-001");

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/tests/test-001/ranges",
      expect.objectContaining({ method: "GET" }),
    );
    expect(ranges).toHaveLength(1);
    expect(ranges[0]?.low).toBe("13.500");
  });

  it("listTestRanges throws on non-OK status", async () => {
    mockFetchOnce(403, { error: { code: "forbidden", message: "No." } });

    await expect(catalogService.listTestRanges("test-001")).rejects.toThrow(
      "Failed to load reference ranges (403)",
    );
  });

  it("createTestRange POSTs the payload and returns the range", async () => {
    mockFetchOnce(201, sampleRange);

    const created = await catalogService.createTestRange(
      "test-001",
      createInput,
    );

    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    const [, init] = calls[0] as [string, { method: string; body: string }];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({
      sex: "M",
      age_min_days: 0,
      unit: "g/dL",
    });
    expect(created.id).toBe("range-001");
  });

  it("createTestRange surfaces the overlapping_range error code", async () => {
    mockFetchOnce(422, {
      error: { code: "overlapping_range", message: "Overlaps existing range." },
    });

    const err = (await catalogService
      .createTestRange("test-001", createInput)
      .catch((e: unknown) => e)) as Error & { code?: string };

    expect(err).toBeInstanceOf(Error);
    expect(err.code).toBe("overlapping_range");
    expect(err.message).toBe("Overlaps existing range.");
  });

  it("updateTestRange PATCHes the range and returns the successor", async () => {
    const successor = { ...sampleRange, id: "range-002", high: "18.000" };
    mockFetchOnce(200, successor);

    const updated = await catalogService.updateTestRange(
      "test-001",
      "range-001",
      {
        high: "18.000",
      },
    );

    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    const [url, init] = calls[0] as [string, { method: string; body: string }];
    expect(url).toBe("/api/v1/tests/test-001/ranges/range-001");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ high: "18.000" });
    expect(updated.id).toBe("range-002");
    expect(updated.high).toBe("18.000");
  });

  it("updateTestRange surfaces the invalid_effective_window error code", async () => {
    mockFetchOnce(422, {
      error: {
        code: "invalid_effective_window",
        message: "Cannot rewrite history.",
      },
    });

    const err = (await catalogService
      .updateTestRange("test-001", "range-001", {
        effective_from: "2020-01-01",
      })
      .catch((e: unknown) => e)) as Error & { code?: string };

    expect(err.code).toBe("invalid_effective_window");
  });
});
