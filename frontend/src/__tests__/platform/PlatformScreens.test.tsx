import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubscriptionDetailScreen } from "../../features/platform/SubscriptionDetailScreen";
import { SubscriptionsScreen } from "../../features/platform/SubscriptionsScreen";
import { UsersScreen } from "../../features/platform/UsersScreen";
import { platformService } from "../../features/platform/platformService";

vi.mock("../../features/platform/platformService", () => ({
  platformService: {
    listUsers: vi.fn(),
    listSubscriptions: vi.fn(),
    getSubscription: vi.fn(),
  },
}));

describe("D3 — Users screen renders real tenant owner metadata", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows owner_name/owner_email/owner_phone and never fabricates a director", async () => {
    vi.mocked(platformService.listUsers).mockResolvedValue({
      lab_owners: [
        {
          id: "t1",
          owner_name: "Dr. Nazeer Ahmed",
          owner_email: "owner@nazeerhub.pk",
          owner_phone: "+92 300 1234567",
          lab_name: "Nazeer Diagnostic Hub",
          lab_slug: "nazeerhub",
          city: "Lahore",
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          last_active: "2026-11-01T00:00:00Z",
        },
      ],
      platform_team: [],
      invitations: [],
    });

    render(
      <MemoryRouter>
        <UsersScreen />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Dr. Nazeer Ahmed")).toBeInTheDocument();
    expect(screen.getByText("owner@nazeerhub.pk")).toBeInTheDocument();
    expect(screen.getByText("+92 300 1234567")).toBeInTheDocument();
    expect(screen.queryByText("director@nazeerhub.pk")).not.toBeInTheDocument();
  });
});

describe("D4 — Subscriptions summary uses mrr/overdue_amount and last_payment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders real MRR and marks an unpaid row from last_payment null", async () => {
    vi.mocked(platformService.listSubscriptions).mockResolvedValue({
      subscriptions: [
        {
          id: "sub-1",
          tenant: {
            id: "t1",
            name: "Nazeer Diagnostic Hub",
            slug: "nazeerhub",
            city: "Lahore",
          },
          plan: { id: "p1", name: "Growth", price: "5999.00" },
          billing_cycle: "monthly",
          amount: "5999.00",
          status: "active",
          starts_at: "2026-01-01T00:00:00Z",
          ends_at: null,
          next_due: "2026-12-01T00:00:00Z",
          last_payment: null,
        },
      ],
      summary: {
        mrr: "225991.00",
        overdue_count: 0,
        overdue_amount: "0.00",
        lifetime_sold_count: 0,
        lifetime_revenue: "0.00",
        founding_slots_used: 0,
        founding_slots_total: 10,
      },
    });

    render(
      <MemoryRouter>
        <SubscriptionsScreen />
      </MemoryRouter>,
    );

    expect(await screen.findByText("PKR 225,991")).toBeInTheDocument();
    expect(screen.getByText("Nazeer Diagnostic Hub")).toBeInTheDocument();
    expect(screen.getByText("UNPAID")).toBeInTheDocument();
  });
});

describe("D1 — Subscription detail reads nested tenant/plan", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads a nested subscription without crashing and shows real identity", async () => {
    vi.mocked(platformService.getSubscription).mockResolvedValue({
      id: "sub-1",
      tenant: {
        id: "t1",
        name: "Nazeer Diagnostic Hub",
        slug: "nazeerhub",
        city: "Lahore",
        province: "Punjab",
      },
      plan: { id: "p1", name: "Growth", price: "5999.00" },
      billing_cycle: "monthly",
      status: "active",
      starts_at: "2026-01-01T00:00:00Z",
      ends_at: null,
      next_due: "2026-12-01T00:00:00Z",
      payments: [],
      available_plans: [
        {
          id: "p1",
          name: "Growth",
          price: "5999.00",
          max_branches: 3,
          max_staff: 10,
          is_active: true,
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/platform/subscriptions/sub-1"]}>
        <Routes>
          <Route
            path="/platform/subscriptions/:id"
            element={<SubscriptionDetailScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        /Subscription Management — Nazeer Diagnostic Hub/,
      ),
    ).toBeInTheDocument();
    const header = screen.getByText(/Subscription Management/).closest("div");
    expect(
      within(header as HTMLElement).getByText("Growth"),
    ).toBeInTheDocument();
    expect(screen.getByText("nazeerhub")).toBeInTheDocument();
  });
});
