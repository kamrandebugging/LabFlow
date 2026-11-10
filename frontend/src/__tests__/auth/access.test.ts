import { describe, expect, it } from "vitest";

import {
  canAccessPath,
  navForRole,
  needsTotpEnrolment,
  roleHome,
} from "../../features/auth/access";

describe("role-aware navigation and route capability map", () => {
  it("gives every staff role its own landing screen", () => {
    expect(roleHome("owner")).toBe("/");
    expect(roleHome("manager")).toBe("/");
    expect(roleHome("reception")).toBe("/invoices");
    expect(roleHome("technician")).toBe("/worklist");
    expect(roleHome("pathologist")).toBe("/results/approvals");
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
  });

  it("shows staff management only to the Owner", () => {
    const ownerLinks = [
      ...navForRole("owner").operations,
      ...navForRole("owner").management,
    ].map((item) => item.to);
    expect(ownerLinks).toContain("/settings/staff");
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
    for (const role of [
      "owner",
      "manager",
      "reception",
      "technician",
      "pathologist",
    ] as const) {
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
