/**
 * Role-aware navigation and route capability map.
 *
 * The map mirrors the backend policy:
 * - `apps.core.authorization.ROLE_POLICY`
 * - `apps.samples.services.SAMPLE_*_ROLES`
 * - `apps.results.services.RESULT_*_ROLES`
 * - Doc 03 §4.3 (billing: Technicians and Pathologists read only; payments are
 *   front-desk only)
 *
 * This is a UX guard only. The server re-checks every role on every request
 * (S15); hiding a link is never the enforcement. The sidebar is additionally
 * filtered by the tenant's Platform-enabled role list when the session carries
 * it, so a role disabled for a lab cannot keep its old navigation.
 */

import type { UserRole } from "./types";

export interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

export const ROLE_LABELS: Record<UserRole, string> = {
  owner: "Lab Owner",
  manager: "Branch Manager",
  reception: "Receptionist",
  technician: "Lab Technician",
  pathologist: "Pathologist",
};

export const MANDATORY_TOTP_ROLES: UserRole[] = [
  "owner",
  "manager",
  "pathologist",
];

const KNOWN_ROLES: readonly UserRole[] = [
  "owner",
  "manager",
  "reception",
  "technician",
  "pathologist",
];

export function isUserRole(value: unknown): value is UserRole {
  return typeof value === "string" && KNOWN_ROLES.includes(value as UserRole);
}

/**
 * Fail closed when the session carries the Platform-enabled role list.
 * Sessions created before the field existed fall back to the role itself.
 */
export function isRoleEnabled(
  role: UserRole | undefined,
  enabledRoles?: readonly UserRole[],
): boolean {
  if (!isUserRole(role)) return false;
  if (role === "owner") return true;
  if (enabledRoles === undefined) return true;
  return enabledRoles.includes(role);
}

/**
 * Every authenticated role lands on `/`, where the role-specific dashboard is
 * rendered. An unknown role must never fall through to a tenant screen.
 */
export function roleHome(role: UserRole | undefined): string {
  return isUserRole(role) ? "/" : "/login";
}

const OPS_NAV: NavItem[] = [
  { to: "/", label: "Home", icon: "home", end: true },
  { to: "/patients", label: "Patients", icon: "personal_injury" },
  { to: "/invoices", label: "Invoices & Payments", icon: "receipt_long" },
  { to: "/samples", label: "Samples", icon: "colorize" },
  { to: "/worklist", label: "Worklist", icon: "assignment" },
  { to: "/results/approvals", label: "Approvals", icon: "verified" },
  {
    to: "/exceptions",
    label: "Critical Notifications",
    icon: "notification_important",
  },
  { to: "/reports", label: "Reports", icon: "lab_profile" },
];

const MANAGEMENT_NAV: NavItem[] = [
  { to: "/partners", label: "Partners & Share Ledger", icon: "handshake" },
  { to: "/settlements", label: "Settlements", icon: "account_balance_wallet" },
  { to: "/catalog", label: "Catalog", icon: "medical_services" },
  { to: "/settings/staff", label: "Staff", icon: "groups" },
  { to: "/settings/account", label: "Account & Security", icon: "shield" },
  { to: "/settings/tenant", label: "Settings", icon: "settings" },
  { to: "/settings/branches", label: "Branches", icon: "domain" },
];

const pick = (paths: string[]): NavItem[] =>
  [...OPS_NAV, ...MANAGEMENT_NAV].filter((item) => paths.includes(item.to));

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  owner: [...OPS_NAV, ...MANAGEMENT_NAV],
  manager: pick([
    "/",
    "/patients",
    "/invoices",
    "/samples",
    "/reports",
    "/exceptions",
    "/settlements",
    "/settings/account",
    "/settings/tenant",
  ]),
  reception: pick([
    "/",
    "/patients",
    "/invoices",
    "/samples",
    "/reports",
    "/exceptions",
    "/settings/account",
  ]),
  technician: pick([
    "/",
    "/patients",
    "/samples",
    "/worklist",
    "/reports",
    "/exceptions",
    "/settings/account",
  ]),
  pathologist: pick([
    "/",
    "/patients",
    "/samples",
    "/worklist",
    "/results/approvals",
    "/reports",
    "/exceptions",
    "/settings/account",
  ]),
};

export function navForRole(
  role: UserRole | undefined,
  enabledRoles?: readonly UserRole[],
): {
  operations: NavItem[];
  management: NavItem[];
} {
  if (!isUserRole(role) || !isRoleEnabled(role, enabledRoles)) {
    return { operations: [], management: [] };
  }

  // The Owner is a superrole and is always enabled. For every other role, a
  // tenant-level disable removes the whole role's navigation (fail closed).

  const items = NAV_BY_ROLE[role];
  return {
    operations: items.filter((item) => OPS_NAV.some((op) => op.to === item.to)),
    management: items.filter((item) =>
      MANAGEMENT_NAV.some((mg) => mg.to === item.to),
    ),
  };
}

const ALLOWED_PREFIXES: Record<UserRole, string[]> = {
  owner: ["/"],
  manager: [
    "/patients",
    "/invoices",
    "/samples",
    "/results",
    "/reports",
    "/exceptions",
    "/settlements",
    "/settings/account",
    "/settings/tenant",
  ],
  reception: [
    "/patients",
    "/invoices",
    "/samples",
    "/results",
    "/reports",
    "/exceptions",
    "/settings/account",
  ],
  technician: [
    "/patients",
    "/samples",
    "/worklist",
    "/results",
    "/reports",
    "/exceptions",
    "/settings/account",
  ],
  pathologist: [
    "/patients",
    "/samples",
    "/worklist",
    "/results",
    "/reports",
    "/exceptions",
    "/settings/account",
  ],
};

export function canAccessPath(
  role: UserRole | undefined,
  pathname: string,
): boolean {
  if (!isUserRole(role) || !ALLOWED_PREFIXES[role]) return false;
  if (role === "owner") return true;

  // Treat /patients/new/ the same as /patients/new.
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (path === "/") return true;

  // Action-level overrides: a read-only role must not land on a screen whose
  // only action the API will refuse.
  if (path.startsWith("/results/approvals")) {
    return role === "pathologist";
  }
  if (path.startsWith("/results/entry")) {
    return role === "technician" || role === "pathologist";
  }
  if (path.startsWith("/results/") && path.endsWith("/amend")) {
    return role === "technician" || role === "pathologist";
  }
  if (path.startsWith("/invoices")) {
    // Doc 03 §4.3: invoice read is allowed to T/P, but the combined
    // Invoices & Payments screen exposes front-desk writes. The stricter
    // product rule keeps the whole billing screen away from bench/clinical
    // roles; reads remain available through their own screens.
    return role === "manager" || role === "reception";
  }
  if (path.startsWith("/worklist")) {
    return role === "technician" || role === "pathologist";
  }
  if (path.startsWith("/patients/") && path.endsWith("/edit")) {
    return role === "manager" || role === "reception";
  }
  if (path === "/invoices/new" || path === "/patients/new") {
    return role === "manager" || role === "reception";
  }
  if (path.startsWith("/samples/collect")) {
    return role === "manager" || role === "reception";
  }

  return ALLOWED_PREFIXES[role].some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

export function needsTotpEnrolment(
  role: UserRole | undefined,
  totpEnabled: boolean | undefined,
): boolean {
  return Boolean(role && MANDATORY_TOTP_ROLES.includes(role) && !totpEnabled);
}
