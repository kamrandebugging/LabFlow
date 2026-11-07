/**
 * Platform (Super Admin) dashboard types — Master Dashboard Phase 1.
 *
 * Every shape here mirrors a backend payload exactly; nothing is invented on
 * the client. Money is a string with two decimals in PKR.
 */

export type TenantStatus = "provisioning" | "active" | "suspended" | "deleted";

export const TENANT_STATUSES: readonly TenantStatus[] = [
  "active",
  "provisioning",
  "suspended",
  "deleted",
];

export interface PlatformUser {
  id: string;
  email: string;
  role: string;
  totp_enabled: boolean;
}

export interface PlatformSession {
  access: string;
  expires_in: number;
  user: PlatformUser;
}

export interface TenantListItem {
  id: string;
  slug: string;
  name: string;
  status: TenantStatus;
  city?: string;
  province?: string;
  branch_count?: number;
  staff_count?: number;
  plan_name?: string;
  plan_price?: string;
  mrr_contribution?: string;
  created_at: string;
  updated_at: string;
}

export interface TenantListResponse {
  tenants: TenantListItem[];
  next_cursor: string | null;
}

export interface TenantListParams {
  q?: string;
  status?: TenantStatus | "";
  cursor?: string | null;
  limit?: number;
}

export interface TenantDomain {
  domain: string;
  is_primary: boolean;
}

export interface TenantPlan {
  id: string;
  name: string;
  price: string;
  max_branches: number | null;
  max_staff?: number | null;
  is_active: boolean;
}

export interface TenantSubscription {
  id: string;
  plan_id: string;
  status: string;
  started_at: string | null;
  ends_at: string | null;
}

export interface MigrationState {
  schema_exists: boolean;
  applied_migrations: number;
  pending_migrations: number;
  in_sync: boolean;
  latest_applied: {
    app: string;
    name: string;
    applied_at: string | null;
  } | null;
}

export interface ProvisioningState {
  current_step: string | null;
  completed_steps: string[];
  failed_step: string | null;
  error: string | null;
  owner_email: string;
  last_action: string | null;
  last_action_at: string | null;
}

export interface TenantOwnerInfo {
  name: string;
  email: string;
  phone: string;
  whatsapp: string;
}

export interface BillingSummary {
  plan_name: string;
  price: string;
  status: string;
  billing_cycle: string;
  started_at: string | null;
  ends_at: string | null;
}

export interface TenantDetail extends TenantListItem {
  schema_name: string;
  domains: TenantDomain[];
  owner?: TenantOwnerInfo;
  owner_name?: string;
  owner_email?: string;
  owner_phone?: string;
  subscription: TenantSubscription | null;
  plan: TenantPlan | null;
  branches_used: number;
  branches_limit: number | null;
  staff_seats_limit?: number | null;
  schema_size_bytes: number | null;
  migration_state: MigrationState;
  provisioning: ProvisioningState;
  billing_summary?: BillingSummary;
  audit_timeline?: AuditEntry[];
  temp_password?: string;
  temp_password_expires_at?: string | null;
}

export interface AccessModeCensus {
  full: number;
  read_only: number;
  grace: number;
}

export interface OverdueSubscriptionItem {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  plan_name: string;
  amount_pkr: string;
  overdue_since: string;
}

export interface MonthGrowthItem {
  month: string;
  starter: number;
  growth: number;
  scale: number;
  total: number;
}

export interface NeedsAttentionItem {
  id: string;
  type: string;
  severity: "high" | "medium" | "low" | string;
  title: string;
  detail: string;
  tenant_id?: string;
  action: string;
}

export interface OverviewMetrics {
  total_labs: number;
  active_labs: number;
  suspended_labs: number;
  provisioning_labs: number;
  mrr_pkr: string;
  lifetime_revenue_pkr?: string;
  overdue_count: number;
  overdue_subscriptions?: {
    count: number;
    list: OverdueSubscriptionItem[];
  };
  labs_growth_6months?: MonthGrowthItem[];
  needs_attention?: NeedsAttentionItem[];
  recent_audits?: AuditEntry[];
  lifetime_sold: number;
  founding_slots_used: number;
  founding_slots_total: number;
  access_mode_census: AccessModeCensus;
  generated_at: string;
}

export interface AuditEntry {
  id: string;
  actor_id: string | null;
  action: string;
  entity_type?: string;
  entity_id?: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip?: string | null;
  at: string | null;
}

export interface AuditListResponse {
  audit: AuditEntry[];
}

export interface ProvisionTenantPayload {
  name: string;
  slug: string;
  plan_id: string;
  owner_email: string;
  owner_name: string;
  city?: string;
  province?: string;
  phone?: string;
  whatsapp?: string;
  staff_seats?: number | null;
  branch_count?: number;
  enabled_roles?: string[];
}

export interface ProvisionTenantResult {
  id: string;
  slug: string;
  name: string;
  schema_name: string;
  status: TenantStatus;
  domain: string;
  plan_id: string;
  subscription_id: string;
  owner_email: string;
  owner_name: string;
  temp_password?: string;
  created_at: string;
}

/**
 * Slug rules from Doc 04 §5.1, mirrored from `apps.platform.provisioning`.
 * The server stays the authority; this only gives immediate feedback.
 */
export const SLUG_PATTERN = /^[a-z][a-z0-9]{2,29}$/;

export const RESERVED_SLUGS: readonly string[] = [
  "www",
  "api",
  "admin",
  "app",
  "platform",
  "internal",
  "static",
  "media",
  "assets",
  "cdn",
  "n8n",
  "sentry",
  "minio",
  "staging",
  "health",
  "metrics",
  "login",
  "signup",
  "register",
  "account",
  "billing",
  "support",
  "help",
  "mail",
  "smtp",
  "imap",
  "ftp",
  "public",
  "tenant",
  "tenants",
  "system",
  "root",
  "labflow",
  "test",
  "demo",
  "example",
  "null",
];

export function slugProblem(slug: string): string | null {
  if (!slug) return "Slug is required.";
  if (!SLUG_PATTERN.test(slug)) {
    return "3–30 lowercase letters or digits, starting with a letter, no hyphens.";
  }
  if (RESERVED_SLUGS.includes(slug))
    return "This slug is reserved by the platform.";
  return null;
}
