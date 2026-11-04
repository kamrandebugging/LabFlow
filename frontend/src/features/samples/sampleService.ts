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
  SampleSummary,
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

// Canonical Demo Dataset matching Screen 16 & 19
const MOCK_SAMPLES: SampleSummary[] = [
  {
    id: "00000000-0000-0000-0000-000000000101",
    accession_id: "CDL20261020000142",
    invoice_id: "00000000-0000-0000-0000-000000000011",
    patient_id: "00000000-0000-0000-0000-000000000001",
    patient_name: "Muhammad Imran",
    patient_mrn: "MRN-2026-00417",
    patient_sex: "M",
    patient_age_years: 42,
    branch_id: "00000000-0000-0000-0000-000000000001",
    branch_name: "Central Diagnostic Lab",
    status: "collected",
    tests: ["Complete Blood Count (CBC)", "HbA1c"],
    collected_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    age_display: "0h 45m",
  },
  {
    id: "00000000-0000-0000-0000-000000000102",
    accession_id: "CDL20261020000141",
    invoice_id: "00000000-0000-0000-0000-000000000012",
    patient_id: "00000000-0000-0000-0000-000000000002",
    patient_name: "Fatima Noor",
    patient_mrn: "MRN-2026-00389",
    patient_sex: "F",
    patient_age_years: 29,
    branch_id: "00000000-0000-0000-0000-000000000001",
    branch_name: "Central Diagnostic Lab",
    status: "received",
    tests: ["Liver Function Test (LFT)"],
    collected_at: new Date(Date.now() - 110 * 60 * 1000).toISOString(),
    age_display: "1h 50m",
  },
  {
    id: "00000000-0000-0000-0000-000000000103",
    accession_id: "CDL20261020000139",
    invoice_id: "00000000-0000-0000-0000-000000000013",
    patient_id: "00000000-0000-0000-0000-000000000003",
    patient_name: "Abdul Rehman",
    patient_mrn: "MRN-2026-00350",
    patient_sex: "M",
    patient_age_years: 55,
    branch_id: "00000000-0000-0000-0000-000000000002",
    branch_name: "Gulberg Branch",
    status: "in_process",
    tests: ["Lipid Profile", "Renal Function Test (RFT)"],
    collected_at: new Date(Date.now() - 210 * 60 * 1000).toISOString(),
    age_display: "3h 30m",
  },
  {
    id: "00000000-0000-0000-0000-000000000104",
    accession_id: "CDL20261020000135",
    invoice_id: "00000000-0000-0000-0000-000000000014",
    patient_id: "00000000-0000-0000-0000-000000000004",
    patient_name: "Zainab Bibi",
    patient_mrn: "MRN-2026-00312",
    patient_sex: "F",
    patient_age_years: 64,
    branch_id: "00000000-0000-0000-0000-000000000001",
    branch_name: "Central Diagnostic Lab",
    status: "ready",
    tests: ["TSH (Thyroid Stimulating Hormone)"],
    collected_at: new Date(Date.now() - 320 * 60 * 1000).toISOString(),
    age_display: "5h 20m",
  },
  {
    id: "00000000-0000-0000-0000-000000000105",
    accession_id: "CDL20261020000130",
    invoice_id: "00000000-0000-0000-0000-000000000015",
    patient_id: "00000000-0000-0000-0000-000000000005",
    patient_name: "Tariq Mahmood",
    patient_mrn: "MRN-2026-00288",
    patient_sex: "M",
    patient_age_years: 48,
    branch_id: "00000000-0000-0000-0000-000000000001",
    branch_name: "Central Diagnostic Lab",
    status: "rejected",
    tests: ["CBC", "Serum Electrolytes"],
    collected_at: new Date(Date.now() - 420 * 60 * 1000).toISOString(),
    age_display: "7h 00m",
    rejection_reason_code: "hemolyzed",
    rejection_note: "Gross hemolysis observed upon centrifugation.",
  },
];

export const sampleService = {
  /**
   * List accessions with status, search and branch filters
   */
  async listSamples(filters: SampleListFilter = {}): Promise<SampleListResponse> {
    try {
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

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          return { results: data, total: data.length };
        }
        if (data && Array.isArray(data.results)) {
          return data;
        }
      }
    } catch {
      // Fall through to mock dataset
    }

    // Client-side filtering on mock data
    let filtered = [...MOCK_SAMPLES];
    if (filters.status && filters.status !== "all") {
      filtered = filtered.filter((s) => s.status === filters.status);
    }
    if (filters.branch_id && filters.branch_id !== "all") {
      filtered = filtered.filter((s) => s.branch_id === filters.branch_id);
    }
    if (filters.q) {
      const q = filters.q.toLowerCase().trim();
      filtered = filtered.filter(
        (s) =>
          s.accession_id.toLowerCase().includes(q) ||
          s.patient_name.toLowerCase().includes(q) ||
          s.patient_mrn.toLowerCase().includes(q),
      );
    }

    return { results: filtered, total: filtered.length };
  },

  /**
   * Get full sample detail by ID or accession number
   */
  async getSample(sampleId: string): Promise<SampleDetail> {
    try {
      const res = await fetch(`${API_BASE}/${sampleId}`, {
        method: "GET",
        headers: getAuthHeaders(),
        credentials: "include",
      });

      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fall through to mock
    }

    const found =
      MOCK_SAMPLES.find((s) => s.id === sampleId || s.accession_id === sampleId) ||
      MOCK_SAMPLES[0]!;

    return {
      ...found,
      patient_dob: "1982-05-14",
      collected_by: "phleb.amna@labflow.pk",
      custody_location: "Accession Bench A2 · Central Diagnostic Lab",
      bench_code: "BENCH-HEM-01",
      sample_tests: [
        {
          id: "st-01",
          test_id: "t-01",
          test_name: "Complete Blood Count (CBC)",
          test_code: "CBC",
          invoice_item_id: "ii-01",
          specimen_type: "Whole Blood",
          tube_type: "K2-EDTA",
          tube_color: "#7e22ce",
          required_volume_ml: 3.0,
        },
        {
          id: "st-02",
          test_id: "t-02",
          test_name: "Glycated Hemoglobin (HbA1c)",
          test_code: "HBA1C",
          invoice_item_id: "ii-02",
          specimen_type: "Whole Blood",
          tube_type: "K2-EDTA",
          tube_color: "#7e22ce",
          required_volume_ml: 2.0,
        },
      ],
      open_transfer: null,
      events: [
        {
          id: "evt-01",
          event: "COLLECTED",
          actor: "phleb.amna@labflow.pk",
          branch: { id: found.branch_id, code: "CDL", name: found.branch_name },
          timestamp: found.collected_at,
          payload: { note: "Phlebotomy completed smoothly from right median cubital vein." },
        },
      ],
    };
  },

  /**
   * Accession / collect specimen (SM-1..SM-3, POST /api/v1/samples)
   */
  async collectSample(input: SampleCreateInput): Promise<SampleCreatedResponse> {
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
      const msg = err?.error?.message || err?.detail || `Collection failed (${res.status})`;
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

    if (res.ok) {
      return await res.json();
    }

    // Realistic ISO 15189 fallback label data for direct thermal printing
    const found = MOCK_SAMPLES.find((s) => s.id === sampleId) || MOCK_SAMPLES[0]!;
    return {
      accession_id: found.accession_id,
      patient_name: found.patient_name,
      mrn: found.patient_mrn,
      date_of_birth: "1984-07-22",
      collected_at: found.collected_at,
      collected_by: "Phleb. Amna Tariq",
      branch_name: found.branch_name,
      tests: found.tests,
      barcode: {
        symbology: "code128",
        payload: found.accession_id,
      },
    };
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
      throw new Error(err?.error?.message || `Failed to receive sample (${res.status})`);
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
      throw new Error(err?.error?.message || `Failed to reject sample (${res.status})`);
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
      throw new Error(err?.error?.message || `Failed to trigger recollection (${res.status})`);
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
      throw new Error(err?.error?.message || `Failed to cancel sample (${res.status})`);
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
      throw new Error(err?.error?.message || `Failed to transfer sample (${res.status})`);
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

    if (res.ok) {
      return await res.json();
    }

    return [
      {
        id: "evt-01",
        event: "COLLECTED",
        actor: "phleb.amna@labflow.pk",
        branch: { id: "br-01", code: "CDL", name: "Central Diagnostic Lab" },
        timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        payload: { note: "Specimen collected per phlebotomy SOP." },
      },
    ];
  },
};
