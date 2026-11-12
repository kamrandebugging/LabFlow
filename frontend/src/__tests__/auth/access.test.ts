import { describe, expect, it } from "vitest";

import {
  canAccessPath,
  isRoleEnabled,
  navForRole,
  needsTotpEnrolment,
  roleHome,
} from "../../features/auth/access";

const STAFF_ROLES = [
  "owner",
  "manager",
  "reception",
  "technician",
  "pathologist",
] as const;

describe("role-aware navigation and route capability map", () => {
  it("lands every known role on its own dashboard at /", () => {
    for (const role of STAFF_ROLES) {
      expect(roleHome(role)).toBe("/");
    }
    expect(roleHome(undefined)).toBe("/login");
    expect(roleHome("auditor" as unknown as "reception")).toBe("/login");
  });

  it("never shows owner-only links to staff", () => {
    for (const role of [
      "manager",
      "reception",
      "technician",
      "pathologist",
    ] as const) {
      const nav = navForRole(role);
      const links = [...nav.operations, ...nav.management].map(
        (item) => item.to,
      );
      expect(links).not.toContain("/settings/staff");
      expect(links).not.toContain("/settings/branches");
      expect(links).not.toContain("/partners");
      expect(links).not.toContain("/catalog");
    }
    for (const role of ["manager", "reception", "technician"] as const) {
      const links = [
        ...navForRole(role).operations,
        ...navForRole(role).management,
      ].map((item) => item.to);
      expect(links).not.toContain("/results/approvals");
    }
  });

  it("shows staff management only to the Owner", () => {
    const ownerLinks = [
      ...navForRole("owner").operations,
      ...navForRole("owner").management,
    ].map((item) => item.to);
    expect(ownerLinks).toContain("/settings/staff");
    expect(ownerLinks).toContain("/catalog");
    expect(ownerLinks).toContain("/partners");
  });

  it("hides billing from bench and clinical roles", () => {
    for (const role of ["technician", "pathologist"] as const) {
      const links = [
        ...navForRole(role).operations,
        ...navForRole(role).management,
      ].map((item) => item.to);
      expect(links).not.toContain("/invoices");
      expect(canAccessPath(role, "/invoices")).toBe(false);
    }
    expect(canAccessPath("manager", "/invoices")).toBe(true);
    expect(canAccessPath("reception", "/invoices")).toBe(true);
  });

  it("blocks owner-only routes for staff and allows them for the Owner", () => {
    expect(canAccessPath("owner", "/settings/staff")).toBe(true);
    expect(canAccessPath("manager", "/settings/staff")).toBe(false);
    expect(canAccessPath("reception", "/settings/staff")).toBe(false);
    expect(canAccessPath("technician", "/results/entry/abc")).toBe(true);
    expect(canAccessPath("reception", "/results/entry/abc")).toBe(false);
    expect(canAccessPath("reception", "/patients/new")).toBe(true);
    expect(canAccessPath("reception", "/settings/branches")).toBe(false);
    expect(canAccessPath("pathologist", "/results/approvals")).toBe(true);
    expect(canAccessPath("manager", "/results/approvals")).toBe(false);
    expect(canAccessPath("technician", "/results/approvals")).toBe(false);
    expect(canAccessPath("technician", "/patients/abc/edit")).toBe(false);
    expect(canAccessPath("pathologist", "/patients/abc/edit")).toBe(false);
    expect(canAccessPath("reception", "/patients/abc/edit")).toBe(true);
    expect(canAccessPath("technician", "/patients/new/")).toBe(false);
  });

  it("gates the sidebar by the per-lab enabled roles", () => {
    expect(
      navForRole("manager", ["owner", "reception"]).operations,
    ).toHaveLength(0);
    expect(
      navForRole("manager", ["owner", "manager"]).operations.length,
    ).toBeGreaterThan(0);
    // The Owner is a superrole and is never hidden.
    expect(navForRole("owner", ["owner"]).management.length).toBeGreaterThan(0);

    expect(isRoleEnabled("manager", ["owner", "reception"])).toBe(false);
    expect(isRoleEnabled("manager", ["owner", "manager"])).toBe(true);
    expect(isRoleEnabled("owner", ["owner"])).toBe(true);
    expect(isRoleEnabled("auditor" as unknown as "manager", ["owner"])).toBe(
      false,
    );
  });

  it("fails safely for an unknown role instead of throwing", () => {
    expect(canAccessPath(undefined, "/patients")).toBe(false);
    expect(
      canAccessPath("auditor" as unknown as "reception", "/patients"),
    ).toBe(false);
    expect(
      navForRole("auditor" as unknown as "reception").operations,
    ).toHaveLength(0);
  });

  it("keeps every visible nav link and role home reachable", () => {
    for (const role of STAFF_ROLES) {
      const nav = navForRole(role);
      for (const item of [...nav.operations, ...nav.management]) {
        expect(canAccessPath(role, item.to)).toBe(true);
      }
      expect(canAccessPath(role, roleHome(role))).toBe(true);
    }
  });

  it("requires TOTP only for mandatory roles", () => {
    expect(needsTotpEnrolment("owner", false)).toBe(true);
    expect(needsTotpEnrolment("manager", false)).toBe(true);
    expect(needsTotpEnrolment("pathologist", false)).toBe(true);
    expect(needsTotpEnrolment("reception", false)).toBe(false);
    expect(needsTotpEnrolment("technician", false)).toBe(false);
    expect(needsTotpEnrolment("owner", true)).toBe(false);
  });
});
