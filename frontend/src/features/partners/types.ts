/**
 * Type definitions for Referral Partners suite (Screens 36–37).
 * Strictly mirrors backend/apps/partners/ models and serializers.
 */

export interface ReferralPartner {
  id: string;
  name: string;
  organisation: string | null;
  phone: string | null;
  email: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreatePartnerPayload {
  name: string;
  organisation?: string | null;
  phone?: string | null;
  email?: string | null;
  is_active?: boolean;
}

export interface UpdatePartnerPayload {
  name?: string;
  organisation?: string | null;
  phone?: string | null;
  email?: string | null;
  is_active?: boolean;
}

export interface PartnerSettlementSummary {
  id: string;
  period: string;
  status: string;
  total: string;
}

export interface PartnerDashboardData {
  partner_id: string;
  partner_name: string;
  has_email: boolean;
  ytd_earned: string;
  ytd_settled: string;
  pending_total: string;
  late_entries: number;
  last_6_settlements: PartnerSettlementSummary[];
}

export interface RevenueShareRule {
  id: string;
  referral_partner_id: string;
  branch_id: string | null;
  test_category: string | null;
  percent: string;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
}

export interface CreateRulePayload {
  branch_id?: string | null;
  test_category?: string | null;
  percent: string;
  effective_from: string;
}

export interface UpdateRulePayload {
  percent?: string;
  effective_from?: string;
}

export interface LedgerSettlementSummary {
  id: string;
  period: string;
  status: string;
}

export interface ShareLedgerEntry {
  id: string;
  payment_id: string;
  referral_partner_id: string;
  referral_partner_name: string;
  rule_id: string | null;
  rule_percent: string | null;
  amount: string;
  percent_applied: string;
  basis_amount: string;
  period: string;
  created_at: string;
  settlement: LedgerSettlementSummary | null;
}

export interface ShareLedgerResponse {
  results: ShareLedgerEntry[];
  next_cursor: string | null;
  totals: {
    count: number;
    amount: string;
  };
}

export type SettlementStatus =
  "DRAFT" | "APPROVED" | "SENT" | "PAID" | "CANCELLED";

export interface SettlementLine {
  id: string;
  share_ledger_entry_id: string;
  amount: string;
  entry_period: string;
}

export interface Settlement {
  id: string;
  referral_partner_id: string;
  period: string;
  status: SettlementStatus;
  total: string;
  statement_pdf_key: string | null;
  approved_by: string | null;
  approved_at: string | null;
  version: string;
  created_at: string;
  updated_at: string;
  lines?: SettlementLine[];
}

export interface SettlementListResponse {
  results: Settlement[];
  next_cursor: string | null;
}

export interface SettlementExceptionsData {
  drafts_awaiting_approval: number;
  drafts_older_than_7_days: number;
  failed_deliveries: number;
}
