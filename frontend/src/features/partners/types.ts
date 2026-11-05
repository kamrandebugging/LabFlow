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
