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
  refund_reason?: string | null;
  received_by?: string | null;
  created_at: string;
}

export interface PaymentCreateInput {
  kind: PaymentKind;
  method: PaymentMethod;
  amount: string;
  reference?: string | null;
  refund_reason?: string | null;
}

export type InvoiceHistoryEventType =
  "created" | "payment" | "refund" | "credit_note" | "cancel" | "discount";

export interface InvoiceHistoryEvent {
  event: InvoiceHistoryEventType;
  at: string;
  actor?: string | null;
  amount?: string | null;
  reason?: string | null;
  number?: string | null;
}

export interface CreditNote {
  id: string;
  number: string;
  invoice_id: string;
  amount: string;
  reason: string;
  issued_by?: string | null;
  issued_by_name?: string | null;
  issued_at: string;
}

export interface InvoiceHistoryResponse {
  invoice_id: string;
  events: InvoiceHistoryEvent[];
}

export interface InvoiceSummary {
  id: string;
  /** Human invoice number when the server provides one. */
  invoice_number?: string;
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
  net_revenue?: string;
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
  credit_notes?: CreditNote[];
  net_paid: string;
  net_revenue?: string;
  created_at: string;
}

export interface InvoiceListResponse {
  results: InvoiceSummary[];
  next_cursor?: string | null;
  total_count?: number;
  /** Present only when the server actually returned a daily aggregate. */
  daily_total?: string;
}

/** Day Close — one branch's reconciled, locked business day. */
export interface DayCloseMethodTotal {
  in: string;
  out: string;
  net: string;
}

export interface DayCloseTotals {
  method_totals: Record<string, DayCloseMethodTotal>;
  total_in: string;
  total_out: string;
  net_total: string;
  total_invoices: number;
  total_discount: string;
  total_credit_notes: string;
  expected_cash: string;
}

export interface DayCloseRecord {
  id: string;
  branch_id: string;
  business_date: string;
  method_totals: Record<string, DayCloseMethodTotal>;
  total_invoices: number;
  total_discount: string;
  total_credit_notes: string;
  expected_cash: string;
  counted_cash: string;
  difference: string;
  difference_note?: string | null;
  closed_by?: string | null;
  closed_by_name?: string | null;
  closed_at: string;
}

export interface DayCloseResponse {
  branch_id: string;
  date: string;
  closed: boolean;
  totals?: DayCloseTotals;
  close?: DayCloseRecord | null;
}

export interface DayCloseInput {
  branch_id: string;
  date?: string;
  counted_cash: string;
  difference_note?: string;
}
