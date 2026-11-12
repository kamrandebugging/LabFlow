import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import { billingService } from "../../features/billing/billingService";
import { OwnerDashboardScreen } from "../../features/dashboard/OwnerDashboardScreen";
import { partnersService } from "../../features/partners/partnersService";
import { reportsService } from "../../features/reports/reportsService";
import { resultsService } from "../../features/results/resultsService";
import { sampleService } from "../../features/samples/sampleService";

vi.mock("../../features/billing/billingService", () => ({
  billingService: { listInvoices: vi.fn() },
}));
vi.mock("../../features/samples/sampleService", () => ({
  sampleService: { listSamples: vi.fn() },
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

const owner = {
  id: "owner-1",
  email: "owner@verify-1113.local",
  display_name: "Verification Owner",
  role: "owner" as const,
  branch_ids: [] as string[],
};

describe("Owner dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", owner);
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: [
        {
          id: "inv-1",
          patient_id: "p1",
          branch_id: "b1",
          status: "paid",
          subtotal: "500.00",
          discount_amount: "0.00",
          total: "500.00",
          net_paid: "500.00",
          created_at: new Date().toISOString(),
        },
        {
          id: "inv-2",
          patient_id: "p2",
          branch_id: "b1",
          status: "paid",
          subtotal: "500.00",
          discount_amount: "0.00",
          total: "500.00",
          net_paid: "500.00",
          created_at: new Date().toISOString(),
        },
      ],
      next_cursor: null,
      daily_total: "1000.00",
    });
    vi.mocked(sampleService.listSamples).mockResolvedValue({
      results: [],
      total: 0,
    });
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValue([]);
    vi.mocked(partnersService.getSettlements).mockResolvedValue({
      results: [],
      next_cursor: null,
    });
    vi.mocked(reportsService.getExceptions).mockResolvedValue({
      results: [],
      counts: {
        total: 3,
        failed_generation: 0,
        failed_delivery: 1,
        late_transfer: 2,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    });
  });

  it("renders the owner's real tenant figures", async () => {
    render(
      <MemoryRouter>
        <OwnerDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Business overview" }),
    ).toBeInTheDocument();
    expect((await screen.findAllByText("PKR 1000.00")).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("2 late sample transfers")).toBeInTheDocument();
    expect(screen.getByText("1 failed report deliveries")).toBeInTheDocument();
  });

  it("renders an em dash when the billing read fails", async () => {
    vi.mocked(billingService.listInvoices).mockRejectedValue(
      new Error("offline"),
    );

    render(
      <MemoryRouter>
        <OwnerDashboardScreen />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Invoiced total")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("PKR 0.00")).not.toBeInTheDocument();
  });
});
