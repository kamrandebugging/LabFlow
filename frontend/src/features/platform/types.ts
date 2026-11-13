/**
 * Platform (Super Admin) dashboard types — Master Dashboard Phase 1.
 *
 * Every shape here mirrors a backend payload exactly; nothing is invented on
 * the client. Money is a string with two decimals in PKR.
 */

export type TenantStatus =
  "provisioning" | "provisioning_failed" | "active" | "suspended" | "deleted";

export const TENANT_STATUSES: readonly TenantStatus[] = [
  "active",
  "provisioning",
  "provisioning_failed",
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
  schema_name?: string;
  status: TenantStatus;
  city?: string;
  province?: string;
  branch_count?: number;
  staff_count?: number;
  plan_name?: string | null;
  plan_price?: string | null;
  plan_status?: string | null;
  is_demo?: boolean;
  mrr_contribution?: string;
  domain?: string | null;
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
  /** Extra branches beyond Main Branch, created during provisioning (P-6). */
  branches?: Array<{ name: string; address?: string }>;
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

/* =========================================================================
 * Phase 2 Types
 * ========================================================================= */

export type SubscriptionBillingCycle = "monthly" | "annual" | "lifetime";
export type SubscriptionStatus =
  "active" | "past_due" | "canceled" | "trialing" | "founding";

export interface SubscriptionTenantRef {
  id: string;
  name: string;
  slug: string;
  city: string;
  province?: string;
  owner_name?: string;
  owner_email?: string;
  owner_phone?: string;
  status?: string;
}

export interface SubscriptionPlanRef {
  id: string;
  name: string;
  price: string;
  max_branches?: number | null;
  max_staff?: number | null;
}

export interface SubscriptionLastPayment {
  paid_date: string;
  amount: string;
  method: string;
  reference: string;
}

export interface SubscriptionListItem {
  id: string;
  tenant: SubscriptionTenantRef;
  plan: SubscriptionPlanRef;
  billing_cycle: SubscriptionBillingCycle;
  amount: string;
  status: SubscriptionStatus;
  starts_at: string | null;
  ends_at: string | null;
  next_due: string | null;
  last_payment: SubscriptionLastPayment | null;
}

export interface SubscriptionListSummary {
  mrr: string;
  overdue_count: number;
  overdue_amount: string;
  lifetime_sold_count: number;
  lifetime_revenue: string;
  founding_slots_used: number;
  founding_slots_total: number;
}

export interface SubscriptionListResponse {
  subscriptions: SubscriptionListItem[];
  summary: SubscriptionListSummary;
}

export interface SubscriptionPaymentRecord {
  id: string;
  amount: string;
  method: string;
  reference: string;
  notes: string;
  paid_date: string;
  recorded_by_email: string | null;
  created_at: string;
}

export interface SubscriptionDetailData {
  id: string;
  tenant: SubscriptionTenantRef;
  plan: SubscriptionPlanRef;
  billing_cycle: SubscriptionBillingCycle;
  status: SubscriptionStatus;
  starts_at: string | null;
  ends_at: string | null;
  next_due: string | null;
  payments: SubscriptionPaymentRecord[];
}

export interface SubscriptionDetailResponse extends SubscriptionDetailData {
  available_plans: TenantPlan[];
}

export interface MarkPaidPayload {
  method: string;
  reference: string;
  amount: string;
  notes?: string;
  paid_date?: string;
}

export interface PlatformRoleRow {
  role: "owner" | "manager" | "reception" | "technician" | "pathologist";
  label: string;
  enabled: boolean;
  immutable: boolean;
  active_staff_count: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface AccessControlData {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  plan_name: string;
  max_branches: number | null;
  max_staff: number | null;
  branch_limit: number;
  staff_limit: number | null;
  enabled_roles: string[];
  roles: PlatformRoleRow[];
  feature_flags: Record<string, boolean>;
}

export interface AccessControlPayload {
  branch_limit?: number;
  staff_limit?: number | null;
  enabled_roles?: string[];
  feature_flags?: Record<string, boolean>;
}

export interface LabOwnerUserItem {
  id: string;
  owner_name: string;
  owner_email: string;
  owner_phone: string;
  lab_name: string;
  lab_slug: string;
  city: string;
  status: string;
  created_at: string;
  last_active: string | null;
}

export interface PlatformTeamMember {
  id: string;
  email: string;
  role: string;
  totp_enabled: boolean;
  is_active: boolean;
  created_at: string;
}

export interface PlatformUserInviteItem {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
}

export interface UsersListResponse {
  lab_owners: LabOwnerUserItem[];
  platform_team: PlatformTeamMember[];
  invitations: PlatformUserInviteItem[];
}

export type DemoRequestStatus =
  "new" | "contacted" | "demo_done" | "converted" | "lost";

export interface DemoRequestItem {
  id: string;
  lab_name: string;
  contact_person: string;
  whatsapp: string;
  message: string;
  status: DemoRequestStatus;
  notes: string;
  requested_at: string;
  converted_tenant: {
    id: string;
    name: string;
    slug: string;
  } | null;
}

export interface DemoRequestSummary {
  new_count: number;
  contacted_count: number;
  demo_done_count: number;
  converted_count: number;
  lost_count: number;
  total_count: number;
}

export interface DemoRequestListResponse {
  demo_requests: DemoRequestItem[];
  summary: DemoRequestSummary;
}

export interface HealthTelemetrySignal {
  status: "operational" | "degraded" | "outage";
  failed_count: number;
  pending_count: number;
  avg_render_ms?: number;
  active_workers?: number;
}

export interface HealthFailureItem {
  id: string;
  type: string;
  lab_name: string;
  error: string;
  occurred_at: string;
  retryable: boolean;
}

export interface HealthSchemaSizeItem {
  schema_name: string;
  tenant_name: string;
  total_size: string;
  table_count: number;
}

export interface PlatformHealthResponse {
  report_generation: HealthTelemetrySignal;
  deliveries: HealthTelemetrySignal;
  webhooks: HealthTelemetrySignal;
  celery_queue: HealthTelemetrySignal;
  storage_used_pct: number;
  database: {
    engine: string;
    status: "operational" | "unreachable";
  };
  cache: {
    engine: string;
    status: "operational" | "unreachable";
  };
  failures: HealthFailureItem[];
  schema_sizes: HealthSchemaSizeItem[];
}

export interface CommercialTiersConfig {
  starter_price_pkr: string;
  growth_price_pkr: string;
  scale_price_pkr: string;
  lifetime_single_pkr: string;
  lifetime_multi_pkr: string;
  annual_maintenance_pct: number;
}

export interface FoundingOfferConfig {
  active: boolean;
  slots_used: number;
  slots_total: number;
}

export interface PlatformTogglesConfig {
  allow_new_signups: boolean;
  maintenance_mode: boolean;
}

export interface PlatformSettingsResponse {
  commercial_tiers: CommercialTiersConfig;
  founding_offer: FoundingOfferConfig;
  platform_toggles: PlatformTogglesConfig;
}
