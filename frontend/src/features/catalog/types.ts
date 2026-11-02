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
