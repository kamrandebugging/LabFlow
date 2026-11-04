/**
 * Diagnostic Catalog API Service (Doc 03 §5.2, §6.3, KAN-118).
 */

import { useAuthStore } from "../auth/authStore";
import type {
  CatalogPrice,
  DiagnosticPanel,
  DiagnosticTest,
  PanelCreateInput,
  PanelUpdateInput,
  PriceCreateInput,
  ReferenceRange,
  ReferenceRangeCreateInput,
  ReferenceRangeUpdateInput,
  TestCreateInput,
  TestUpdateInput,
} from "./types";

const API_BASE = "/api/v1";

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

export const DEFAULT_FALLBACK_TESTS: DiagnosticTest[] = [
  {
    id: "65cfd909-503d-421c-a4b2-cae254c8ce15",
    code: "HB",
    name: "Haemoglobin",
    category: "Haematology",
    unit: "g/dL",
    price: "500.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "67acc0be-a9b8-4ff9-adee-86d28e4ea261",
    code: "HBA1C",
    name: "HbA1c (Glycated Hemoglobin)",
    category: "Biochemistry",
    unit: "%",
    price: "1500.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "db42b6e3-8328-46d7-8cab-44796c58a1a8",
    code: "BSF",
    name: "Blood Sugar (Fasting)",
    category: "Biochemistry",
    unit: "mg/dL",
    price: "400.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "44741a87-2a10-4154-9da8-85d90bbdc6a9",
    code: "BSR",
    name: "Blood Sugar (Random)",
    category: "Biochemistry",
    unit: "mg/dL",
    price: "350.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "736eb3ad-a1de-4548-9be2-ed385e488b69",
    code: "URE",
    name: "Urine Routine Examination",
    category: "Clinical Pathology",
    unit: "pH",
    price: "600.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "9fa4509d-a7cd-4841-89c7-b15887df6423",
    code: "TSH",
    name: "Thyroid Stimulating Hormone",
    category: "Endocrinology",
    unit: "mIU/L",
    price: "1800.00",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const DEFAULT_FALLBACK_PANELS: DiagnosticPanel[] = [
  {
    id: "f77f8243-af52-4653-bcce-eaa7e38af87a",
    code: "CBC",
    name: "Complete Blood Count (CBC)",
    price: "800.00",
    is_active: true,
    test_ids: ["65cfd909-503d-421c-a4b2-cae254c8ce15"],
    tests: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "92ce4c3d-b8f6-4bc7-95b8-5034e77ac76a",
    code: "LFT",
    name: "Liver Function Tests (LFT)",
    price: "1800.00",
    is_active: true,
    test_ids: [],
    tests: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "dc398512-739a-43ca-b2f4-faa38af51fed",
    code: "RFT",
    name: "Renal Function Tests (RFT)",
    price: "1600.00",
    is_active: true,
    test_ids: [],
    tests: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "57e34ea4-bb91-494d-a03b-4d25e929aef6",
    code: "LIPID",
    name: "Lipid Profile",
    price: "2000.00",
    is_active: true,
    test_ids: [],
    tests: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const catalogService = {
  // Tests
  async listTests(
    params: { q?: string; category?: string; isActive?: boolean } = {},
  ): Promise<DiagnosticTest[]> {
    try {
      const url = new URL(`${API_BASE}/tests`, window.location.origin);
      if (params.q) url.searchParams.set("q", params.q);
      if (params.category) url.searchParams.set("category", params.category);
      if (params.isActive !== undefined) {
        url.searchParams.set("active", String(params.isActive));
        url.searchParams.set("is_active", String(params.isActive));
      }

      const res = await fetch(url.toString(), {
        method: "GET",
        headers: getAuthHeaders(),
        credentials: "include",
      });

      if (!res.ok) {
        return DEFAULT_FALLBACK_TESTS;
      }

      const data = await res.json();
      return Array.isArray(data) && data.length > 0 ? data : DEFAULT_FALLBACK_TESTS;
    } catch {
      return DEFAULT_FALLBACK_TESTS;
    }
  },

  async getTest(id: string): Promise<DiagnosticTest> {
    const res = await fetch(`${API_BASE}/tests/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Test not found (${res.status})`);
    }

    return res.json();
  },

  async createTest(input: TestCreateInput): Promise<DiagnosticTest> {
    const res = await fetch(`${API_BASE}/tests`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify({
        code: input.code,
        name: input.name,
        category: input.category || null,
        unit: input.unit || null,
        is_active: input.is_active ?? true,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const code = err?.error?.code || err?.code?.[0];
      const message =
        err?.code?.[0] ||
        err?.name?.[0] ||
        err?.error?.message ||
        `Failed to create test (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = code;
      throw error;
    }

    const test: DiagnosticTest = await res.json();

    // If initial price was supplied, set base price
    if (input.initial_price) {
      try {
        await this.setTestPrice(test.id, { amount: input.initial_price });
        return { ...test, price: input.initial_price };
      } catch (priceErr) {
        throw new Error(
          `Test '${test.name}' created, but setting initial price failed: ${
            priceErr instanceof Error
              ? priceErr.message
              : "Price validation error"
          }`,
        );
      }
    }

    return test;
  },

  async updateTest(
    id: string,
    input: TestUpdateInput,
  ): Promise<DiagnosticTest> {
    const res = await fetch(`${API_BASE}/tests/${id}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.name?.[0] ||
          err?.error?.message ||
          `Failed to update test (${res.status})`,
      );
    }

    return res.json();
  },

  async getTestPrices(testId: string): Promise<CatalogPrice[]> {
    const res = await fetch(`${API_BASE}/tests/${testId}/prices`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      return [];
    }

    return res.json();
  },

  async setTestPrice(
    testId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    const res = await fetch(`${API_BASE}/tests/${testId}/prices`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.amount?.[0] || `Failed to set price (${res.status})`,
      );
    }

    return res.json();
  },

  // Reference ranges (KAN-119)
  async listTestRanges(testId: string): Promise<ReferenceRange[]> {
    const res = await fetch(`${API_BASE}/tests/${testId}/ranges`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Failed to load reference ranges (${res.status})`);
    }

    return res.json();
  },

  async createTestRange(
    testId: string,
    input: ReferenceRangeCreateInput,
  ): Promise<ReferenceRange> {
    const res = await fetch(`${API_BASE}/tests/${testId}/ranges`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const code = err?.error?.code;
      const message =
        err?.error?.message ||
        `Failed to create reference range (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = code;
      throw error;
    }

    return res.json();
  },

  async updateTestRange(
    testId: string,
    rangeId: string,
    input: ReferenceRangeUpdateInput,
  ): Promise<ReferenceRange> {
    const res = await fetch(`${API_BASE}/tests/${testId}/ranges/${rangeId}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const code = err?.error?.code;
      const message =
        err?.error?.message ||
        `Failed to update reference range (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = code;
      throw error;
    }

    return res.json();
  },

  // Panels
  async listPanels(params: { q?: string } = {}): Promise<DiagnosticPanel[]> {
    try {
      const url = new URL(`${API_BASE}/panels`, window.location.origin);
      if (params.q) url.searchParams.set("q", params.q);

      const res = await fetch(url.toString(), {
        method: "GET",
        headers: getAuthHeaders(),
        credentials: "include",
      });

      if (!res.ok) {
        return DEFAULT_FALLBACK_PANELS;
      }

      const data = await res.json();
      return Array.isArray(data) && data.length > 0 ? data : DEFAULT_FALLBACK_PANELS;
    } catch {
      return DEFAULT_FALLBACK_PANELS;
    }
  },

  async getPanel(id: string): Promise<DiagnosticPanel> {
    const res = await fetch(`${API_BASE}/panels/${id}`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error(`Panel not found (${res.status})`);
    }

    return res.json();
  },

  async createPanel(input: PanelCreateInput): Promise<DiagnosticPanel> {
    const res = await fetch(`${API_BASE}/panels`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify({
        code: input.code,
        name: input.name,
        test_ids: input.test_ids,
        is_active: input.is_active ?? true,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const code = err?.error?.code || err?.test_ids?.[0];
      const message =
        err?.test_ids?.[0] ||
        err?.code?.[0] ||
        err?.name?.[0] ||
        err?.error?.message ||
        `Failed to create panel (${res.status})`;
      const error = new Error(String(message));
      (error as Error & { code?: string }).code = code;
      throw error;
    }

    const panel: DiagnosticPanel = await res.json();

    if (input.initial_price) {
      try {
        await this.setPanelPrice(panel.id, { amount: input.initial_price });
        return { ...panel, price: input.initial_price };
      } catch (priceErr) {
        throw new Error(
          `Panel '${panel.name}' created, but setting initial price failed: ${
            priceErr instanceof Error
              ? priceErr.message
              : "Price validation error"
          }`,
        );
      }
    }

    return panel;
  },

  async updatePanel(
    id: string,
    input: PanelUpdateInput,
  ): Promise<DiagnosticPanel> {
    const res = await fetch(`${API_BASE}/panels/${id}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.test_ids?.[0] || `Failed to update panel (${res.status})`,
      );
    }

    return res.json();
  },

  async getPanelPrices(panelId: string): Promise<CatalogPrice[]> {
    const res = await fetch(`${API_BASE}/panels/${panelId}/prices`, {
      method: "GET",
      headers: getAuthHeaders(),
      credentials: "include",
    });

    if (!res.ok) {
      return [];
    }

    return res.json();
  },

  async setPanelPrice(
    panelId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    const res = await fetch(`${API_BASE}/panels/${panelId}/prices`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err?.amount?.[0] || `Failed to set panel price (${res.status})`,
      );
    }

    return res.json();
  },
};
