import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import type { UserRole } from "../../features/auth/types";
import { TenantLayout } from "../../features/layout/TenantLayout";
import { partnersService } from "../../features/partners/partnersService";
import { reportsService } from "../../features/reports/reportsService";
import { resultsService } from "../../features/results/resultsService";

vi.mock("../../features/auth/tenantContext", () => ({
  fetchTenantContext: vi.fn().mockResolvedValue({
    name: "Test Lab",
    slug: "test-lab",
    city: "Lahore",
  }),
  getSubdomainTenant: vi.fn().mockReturnValue(null),
}));
vi.mock("../../features/results/resultsService", () => ({
  resultsService: { getApprovalsQueue: vi.fn() },
}));
vi.mock("../../features/partners/partnersService", () => ({
  partnersService: { getSettlements: vi.fn() },
}));
vi.mock("../../features/reports/reportsService", () => ({
  reportsService: { getExceptions: vi.fn() },
}));

function renderShell(): void {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<TenantLayout />}>
          <Route path="/" element={<div>Dashboard outlet</div>} />
        </Route>
        <Route path="/login" element={<div>Login screen</div>} />
        <Route path="/login/enroll" element={<div>Enroll screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TenantLayout role sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValue([]);
    vi.mocked(partnersService.getSettlements).mockResolvedValue({
      results: [],
      next_cursor: null,
    });
    vi.mocked(reportsService.getExceptions).mockResolvedValue({
      results: [],
      counts: {
        total: 0,
        failed_generation: 0,
        failed_delivery: 0,
        late_transfer: 0,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    });
  });

  it("shows the manager only the nav items the policy allows", async () => {
    useAuthStore.getState().setSession("token", {
      id: "m1",
      email: "manager@lab.pk",
      role: "manager",
      branch_ids: ["b1"],
      totp_enabled: true,
      enabled_roles: ["owner", "manager"],
    });

    renderShell();

    expect(await screen.findByText("Test Lab")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Invoices & Payments/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Settlements/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Approvals/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Worklist/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /^Staff$/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Branches/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Partners/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Catalog/i }),
    ).not.toBeInTheDocument();

    // The manager badge loader must not probe the pathologist-only queue.
    expect(resultsService.getApprovalsQueue).not.toHaveBeenCalled();
    expect(partnersService.getSettlements).toHaveBeenCalled();
    expect(reportsService.getExceptions).toHaveBeenCalled();
  });

  it("keeps billing and approvals out of the technician sidebar", async () => {
    useAuthStore.getState().setSession("token", {
      id: "t1",
      email: "technician@lab.pk",
      role: "technician",
      branch_ids: ["b1"],
      totp_enabled: false,
      enabled_roles: ["owner", "technician"],
    });

    renderShell();

    expect(await screen.findByText("Test Lab")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Worklist/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Invoices & Payments/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Approvals/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Settlements/i }),
    ).not.toBeInTheDocument();
    expect(resultsService.getApprovalsQueue).not.toHaveBeenCalled();
  });

  it("fails closed when the lab has disabled the current role", async () => {
    useAuthStore.getState().setSession("token", {
      id: "m1",
      email: "manager@lab.pk",
      role: "manager",
      branch_ids: ["b1"],
      totp_enabled: true,
      enabled_roles: ["owner", "reception"],
    });

    renderShell();

    expect(await screen.findByText("Login screen")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Patients/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Invoices & Payments/i }),
    ).not.toBeInTheDocument();
  });

  it("sends an unknown role back to login", async () => {
    useAuthStore.getState().setSession("token", {
      id: "x1",
      email: "unknown@lab.pk",
      role: "auditor" as UserRole,
      branch_ids: [],
      totp_enabled: true,
    });

    renderShell();

    expect(await screen.findByText("Login screen")).toBeInTheDocument();
  });
});
