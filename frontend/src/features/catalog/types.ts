/**
 * Diagnostic Catalog Types (Doc 03 §5.2, §6.3, KAN-118, Screens 31 & 32).
 */

export interface DiagnosticTest {
  id: string;
  code: string;
  name: string;
  category: string | null;
  unit: string | null;
  is_active: boolean;
  price?: string | null;
  panel_codes?: string[];
  is_panel_only?: boolean;
  created_at: string;
  updated_at: string;
}

export interface TestCreateInput {
  code: string;
  name: string;
  category?: string | null;
  unit?: string | null;
  is_active?: boolean;
  initial_price?: string;
}

export interface TestUpdateInput {
  name?: string;
  category?: string | null;
  unit?: string | null;
  is_active?: boolean;
}

export interface PanelComponentTest {
  id: string;
  code: string;
  name: string;
  category: string | null;
  unit: string | null;
  is_active: boolean;
}

export interface DiagnosticPanel {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  test_ids: string[];
  tests: PanelComponentTest[];
  price?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PanelCreateInput {
  code: string;
  name: string;
  test_ids: string[];
  is_active?: boolean;
  initial_price?: string;
}

export interface PanelUpdateInput {
  name?: string;
  test_ids?: string[];
  is_active?: boolean;
}

export interface CatalogPrice {
  id: string;
  test_id?: string | null;
  panel_id?: string | null;
  branch_id?: string | null;
  price: string;
  effective_from: string;
  effective_to?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PriceCreateInput {
  amount: string;
  effective_from?: string;
  branch_id?: string | null;
}

/**
 * Biological Reference Range Types (Doc 03 §5.2, §8.2, KAN-119).
 */

export type RangeSex = "M" | "F" | "B";

export interface ReferenceRange {
  id: string;
  test_id: string;
  sex: RangeSex;
  age_min_days: number;
  age_max_days: number | null;
  low: string | null;
  high: string | null;
  critical_low: string | null;
  critical_high: string | null;
  unit: string;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReferenceRangeCreateInput {
  sex: RangeSex;
  age_min_days: number;
  age_max_days?: number | null;
  low?: string | null;
  high?: string | null;
  critical_low?: string | null;
  critical_high?: string | null;
  unit: string;
  effective_from: string;
  effective_to?: string | null;
}

export interface ReferenceRangeUpdateInput {
  sex?: RangeSex;
  age_min_days?: number;
  age_max_days?: number | null;
  low?: string | null;
  high?: string | null;
  critical_low?: string | null;
  critical_high?: string | null;
  unit?: string;
  effective_from?: string;
  effective_to?: string | null;
}
