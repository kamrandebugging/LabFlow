/**
 * Invoicing & Billing Types per Doc 03 §5.3, §6.4 & Doc 02 §5.3 (Screens 13, 14, 15).
 */

export type InvoiceStatus =
  "draft" | "unpaid" | "partial" | "paid" | "refunded" | "cancelled";

export type PaymentMethod =
  "cash" | "card" | "bank_transfer" | "easypaisa" | "jazzcash" | "other";

export type PaymentKind = "payment" | "refund";

export interface InvoiceItemInput {
  test_id?: string | null;
  panel_id?: string | null;
  qty: number;
}

export interface InvoiceCreateInput {
  patient_id: string;
  branch_id?: string | null;
  referral_partner_id?: string | null;
  items: InvoiceItemInput[];
  discount_amount?: string;
  discount_reason?: string | null;
}

export interface InvoiceItem {
  id: string;
  test_id?: string | null;
  panel_id?: string | null;
  description: string;
  name?: string;
  unit_price: string;
  quantity: number;
  line_total: string;
}

export interface PaymentRecord {
  id: string;
  invoice_id: string;
  kind: PaymentKind;
  method: PaymentMethod;
  amount: string;
  reference?: string | null;
  received_by?: string | null;
  created_at: string;
}

export interface PaymentCreateInput {
  kind: PaymentKind;
  method: PaymentMethod;
  amount: string;
  reference?: string | null;
}

export interface InvoiceSummary {
  id: string;
  patient_id: string;
  patient_name?: string;
  patient_mrn?: string;
  branch_id: string;
  branch_name?: string;
  status: InvoiceStatus;
  subtotal: string;
  discount_amount: string;
  total: string;
  net_paid?: string;
  items_summary?: string;
  created_at: string;
}

export interface InvoiceDetail {
  id: string;
  invoice_number?: string;
  patient_id: string;
  patient_name?: string;
  patient_mrn?: string;
  patient_phone?: string;
  patient_sex?: string;
  patient_age?: string;
  branch_id: string;
  branch_name?: string;
  referral_partner_id?: string | null;
  status: InvoiceStatus;
  subtotal: string;
  discount_amount: string;
  discount_reason?: string | null;
  total: string;
  items: InvoiceItem[];
  payments: PaymentRecord[];
  net_paid: string;
  created_at: string;
}

export interface InvoiceListResponse {
  results: InvoiceSummary[];
  next_cursor?: string | null;
  total_count?: number;
  /** Present only when the server actually returned a daily aggregate. */
  daily_total?: string;
}
