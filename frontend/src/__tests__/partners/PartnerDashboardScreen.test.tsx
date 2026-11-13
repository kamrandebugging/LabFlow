import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PartnerDashboardScreen } from "../../features/partners/PartnerDashboardScreen";
import { partnersService } from "../../features/partners/partnersService";
import { useAuthStore } from "../../features/auth/authStore";
import type { PartnerDashboardData } from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartnerDashboard: vi.fn(),
    },
  };
});

const mockDashboard: PartnerDashboardData = {
  partner_id: "p-uuid-999",
  partner_name: "Al-Razi Clinical Lab",
  has_email: true,
  ytd_earned: "345000.00",
  ytd_settled: "290000.00",
  pending_total: "55000.00",
  late_entries: 3,
  last_6_settlements: [
    {
      id: "set-101",
      period: "2026-09",
      status: "PAID",
      total: "45000.00",
    },
    {
      id: "set-102",
      period: "2026-10",
      status: "APPROVED",
      total: "52000.00",
    },
  ],
};

describe("PartnerDashboardScreen (Screen 40)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: "u-owner",
        email: "owner@labflow.pk",
        role: "owner",
        name: "Lab Owner",
        branch_ids: ["b-1"],
      },
      accessToken: "mock-token",
    });

    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue(
      mockDashboard,
    );
  });

  const renderComponent = (partnerId = "p-uuid-999") =>
    render(
      <MemoryRouter initialEntries={[`/partners/${partnerId}/dashboard`]}>
        <Routes>
          <Route
            path="/partners/:id/dashboard"
            element={<PartnerDashboardScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

  it("renders partner dashboard using real partner name and KPI cards", async () => {
    renderComponent();

    expect(
      await screen.findByRole("heading", {
        name: "Partner Dashboard — Al-Razi Clinical Lab",
      }),
    ).toBeInTheDocument();

    expect(screen.getByText("PKR 345000.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 290000.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 55000.00")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();

    // Settlements table
    expect(screen.getByText("2026-09")).toBeInTheDocument();
    expect(screen.getByText("PKR 45000.00")).toBeInTheDocument();
    expect(screen.getByText("Paid")).toBeInTheDocument();

    expect(screen.getByText("2026-10")).toBeInTheDocument();
    expect(screen.getByText("PKR 52000.00")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("renders honest empty state when no historical settlements exist", async () => {
    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue({
      ...mockDashboard,
      last_6_settlements: [],
    });

    renderComponent();

    expect(
      await screen.findByText(
        "No historical settlements recorded for this partner.",
      ),
    ).toBeInTheDocument();
  });

  it("blocks non-owner staff from accessing the financial dashboard", async () => {
    useAuthStore.setState({
      user: {
        id: "u-tech",
        email: "tech@labflow.pk",
        role: "technician",
        name: "Lab Tech",
        branch_ids: ["b-1"],
      },
      accessToken: "mock-token",
    });

    renderComponent();

    expect(await screen.findByText("Access Restricted")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Only the Lab Owner may access financial partner dashboards.",
      ),
    ).toBeInTheDocument();
    expect(partnersService.getPartnerDashboard).not.toHaveBeenCalled();
  });
});
