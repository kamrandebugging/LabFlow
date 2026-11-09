/**
 * Diagnostic Catalog API Service (Doc 03 §5.2, §6.3, KAN-118, KAN-119).
 */

import { apiRequest, ApiError } from "../../lib/apiClient";
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

export const catalogService = {
  // Tests
  async listTests(
    params: { q?: string; category?: string; isActive?: boolean } = {},
  ): Promise<DiagnosticTest[]> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (params.q) query.q = params.q;
    if (params.category) query.category = params.category;
    if (params.isActive !== undefined) {
      query.active = String(params.isActive);
      query.is_active = String(params.isActive);
    }

    try {
      const data = await apiRequest<
        DiagnosticTest[] | { results: DiagnosticTest[] }
      >("/tests", { query });

      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.results)) return data.results;
      return [];
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Failed to fetch tests (${err.status})`);
      }
      throw err;
    }
  },

  async getTest(id: string): Promise<DiagnosticTest> {
    try {
      return await apiRequest<DiagnosticTest>(`/tests/${id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(`Test not found (${err.status})`);
      }
      throw err;
    }
  },

  async createTest(input: TestCreateInput): Promise<DiagnosticTest> {
    let test: DiagnosticTest;
    try {
      test = await apiRequest<DiagnosticTest>("/tests", {
        method: "POST",
        body: {
          code: input.code,
          name: input.name,
          category: input.category || null,
          unit: input.unit || null,
          is_active: input.is_active ?? true,
        },
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to create test (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }

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
    try {
      return await apiRequest<DiagnosticTest>(`/tests/${id}`, {
        method: "PATCH",
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to update test (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async deleteTest(id: string): Promise<void> {
    try {
      await apiRequest<void>(`/tests/${id}`, {
        method: "DELETE",
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Delete failed (${err.status})`);
      }
      throw err;
    }
  },

  // Test Prices
  async getTestPrices(testId: string): Promise<CatalogPrice[]> {
    return this.listTestPrices(testId);
  },

  async listTestPrices(testId: string): Promise<CatalogPrice[]> {
    try {
      const data = await apiRequest<
        CatalogPrice[] | { results: CatalogPrice[] }
      >(`/tests/${testId}/prices`);
      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.results)) return data.results;
      return [];
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch test prices (${err.status})`,
        );
      }
      throw err;
    }
  },

  async setTestPrice(
    testId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    return this.createTestPrice(testId, input);
  },

  async createTestPrice(
    testId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    try {
      return await apiRequest<CatalogPrice>(`/tests/${testId}/prices`, {
        method: "POST",
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Failed to set price (${err.status})`);
      }
      throw err;
    }
  },

  // Reference ranges (KAN-119)
  async listTestRanges(testId: string): Promise<ReferenceRange[]> {
    try {
      return await apiRequest<ReferenceRange[]>(`/tests/${testId}/ranges`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(`Failed to load reference ranges (${err.status})`);
      }
      throw err;
    }
  },

  async createTestRange(
    testId: string,
    input: ReferenceRangeCreateInput,
  ): Promise<ReferenceRange> {
    try {
      return await apiRequest<ReferenceRange>(`/tests/${testId}/ranges`, {
        method: "POST",
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to create reference range (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async updateTestRange(
    testId: string,
    rangeId: string,
    input: ReferenceRangeUpdateInput,
  ): Promise<ReferenceRange> {
    try {
      return await apiRequest<ReferenceRange>(
        `/tests/${testId}/ranges/${rangeId}`,
        {
          method: "PATCH",
          body: input,
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to update reference range (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async deleteTestRange(testId: string, rangeId: string): Promise<void> {
    try {
      await apiRequest<void>(`/tests/${testId}/ranges/${rangeId}`, {
        method: "DELETE",
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to delete reference range (${err.status})`,
        );
      }
      throw err;
    }
  },

  // Panels
  async listPanels(
    params: { q?: string; isActive?: boolean } = {},
  ): Promise<DiagnosticPanel[]> {
    const query: Record<string, string | number | boolean | null | undefined> =
      {};
    if (params.q) query.q = params.q;
    if (params.isActive !== undefined) {
      query.active = String(params.isActive);
      query.is_active = String(params.isActive);
    }

    try {
      const data = await apiRequest<
        DiagnosticPanel[] | { results: DiagnosticPanel[] }
      >("/panels", { query });

      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.results)) return data.results;
      return [];
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch panels (${err.status})`,
        );
      }
      throw err;
    }
  },

  async getPanel(id: string): Promise<DiagnosticPanel> {
    try {
      return await apiRequest<DiagnosticPanel>(`/panels/${id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(`Panel not found (${err.status})`);
      }
      throw err;
    }
  },

  async createPanel(input: PanelCreateInput): Promise<DiagnosticPanel> {
    let panel: DiagnosticPanel;
    try {
      panel = await apiRequest<DiagnosticPanel>("/panels", {
        method: "POST",
        body: {
          code: input.code,
          name: input.name,
          test_ids: input.test_ids,
          is_active: input.is_active ?? true,
        },
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to create panel (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }

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
    try {
      return await apiRequest<DiagnosticPanel>(`/panels/${id}`, {
        method: "PATCH",
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const error = new Error(
          err.message || `Failed to update panel (${err.status})`,
        );
        (error as Error & { code?: string }).code = err.code ?? undefined;
        throw error;
      }
      throw err;
    }
  },

  async deletePanel(id: string): Promise<void> {
    try {
      await apiRequest<void>(`/panels/${id}`, {
        method: "DELETE",
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Delete failed (${err.status})`);
      }
      throw err;
    }
  },

  // Panel Prices
  async getPanelPrices(panelId: string): Promise<CatalogPrice[]> {
    return this.listPanelPrices(panelId);
  },

  async listPanelPrices(panelId: string): Promise<CatalogPrice[]> {
    try {
      const data = await apiRequest<
        CatalogPrice[] | { results: CatalogPrice[] }
      >(`/panels/${panelId}/prices`);
      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.results)) return data.results;
      return [];
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(
          err.message || `Failed to fetch panel prices (${err.status})`,
        );
      }
      throw err;
    }
  },

  async setPanelPrice(
    panelId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    return this.createPanelPrice(panelId, input);
  },

  async createPanelPrice(
    panelId: string,
    input: PriceCreateInput,
  ): Promise<CatalogPrice> {
    try {
      return await apiRequest<CatalogPrice>(`/panels/${panelId}/prices`, {
        method: "POST",
        body: input,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        throw new Error(err.message || `Failed to set price (${err.status})`);
      }
      throw err;
    }
  },
};
