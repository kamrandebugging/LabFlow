/**
 * Role-aware navigation and route capability map.
 *
 * This is a UX guard only. The server re-checks every role on every request
 * (S15); hiding a link is never the enforcement.
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

export function roleHome(role: UserRole | undefined): string {
  switch (role) {
    case "technician":
      return "/worklist";
    case "pathologist":
      return "/results/approvals";
    case "reception":
      return "/invoices";
    case "manager":
    case "owner":
    default:
      return "/";
  }
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
  manager: [
    ...pick([
      "/",
      "/patients",
      "/invoices",
      "/samples",
      "/worklist",
      "/reports",
      "/exceptions",
      "/settlements",
      "/settings/account",
      "/settings/tenant",
    ]),
  ],
  reception: [
    ...pick([
      "/",
      "/patients",
      "/invoices",
      "/samples",
      "/reports",
      "/exceptions",
      "/settings/account",
    ]),
  ],
  technician: [
    ...pick([
      "/",
      "/samples",
      "/worklist",
      "/reports",
      "/exceptions",
      "/settings/account",
    ]),
  ],
  pathologist: [
    ...pick([
      "/",
      "/samples",
      "/worklist",
      "/results/approvals",
      "/reports",
      "/exceptions",
      "/settings/account",
    ]),
  ],
};

export function navForRole(role: UserRole | undefined): {
  operations: NavItem[];
  management: NavItem[];
} {
  const items = role && NAV_BY_ROLE[role] ? NAV_BY_ROLE[role] : [];
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
    "/worklist",
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
    "/reports",
    "/exceptions",
    "/settings/account",
  ],
  technician: [
    "/samples",
    "/worklist",
    "/results",
    "/reports",
    "/exceptions",
    "/settings/account",
  ],
  pathologist: [
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
  if (!role || !ALLOWED_PREFIXES[role]) return false;
  if (role === "owner") return true;
  if (pathname === "/") return true;

  // Action-level overrides: a read-only role must not land on a screen whose
  // only action the API will refuse.
  if (pathname.startsWith("/results/approvals")) {
    return role === "pathologist";
  }
  if (pathname.startsWith("/results/entry")) {
    return role === "technician" || role === "pathologist";
  }
  if (pathname === "/invoices/new" || pathname === "/patients/new") {
    return role === "manager" || role === "reception";
  }
  if (pathname.startsWith("/samples/collect")) {
    return role === "manager" || role === "reception";
  }

  return ALLOWED_PREFIXES[role].some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function needsTotpEnrolment(
  role: UserRole | undefined,
  totpEnabled: boolean | undefined,
): boolean {
  return Boolean(role && MANDATORY_TOTP_ROLES.includes(role) && !totpEnabled);
}
