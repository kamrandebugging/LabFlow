import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PartnerDetailScreen } from "../../features/partners/PartnerDetailScreen";
import { partnersService } from "../../features/partners/partnersService";
import { useAuthStore } from "../../features/auth/authStore";
import type {
  PartnerDashboardData,
  ReferralPartner,
  RevenueShareRule,
} from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartner: vi.fn(),
      getPartnerDashboard: vi.fn(),
      getPartnerRules: vi.fn(),
      updatePartner: vi.fn(),
    },
  };
});

const mockPartner: ReferralPartner = {
  id: "p-uuid-1234",
  name: "Dr. Farhan Qureshi",
  organisation: "Doctor",
  phone: "+92 300 4567890",
  email: "farhan@example.com",
  is_active: true,
  created_at: "2026-01-12T00:00:00Z",
  updated_at: "2026-01-12T00:00:00Z",
};

const mockDashboard: PartnerDashboardData = {
  partner_id: "p-uuid-1234",
  partner_name: "Dr. Farhan Qureshi",
  has_email: true,
  ytd_earned: "22140.00",
  ytd_settled: "0.00",
  pending_total: "7140.00",
  late_entries: 0,
  last_6_settlements: [
    {
      id: "set-1",
      period: "2026-09",
      status: "completed",
      total: "15000.00",
    },
  ],
};

const mockRules: RevenueShareRule[] = [
  {
    id: "r-1",
    referral_partner_id: "p-uuid-1234",
    branch_id: null,
    test_category: "Pathology",
    percent: "12.00",
    effective_from: "2026-01-01",
    effective_to: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

describe("Screen 37: PartnerDetailScreen (/partners/:id)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("mock-token", {
      id: "u1",
      email: "owner@labflow.app",
      name: "Ali Raza",
      role: "owner",
      branch_ids: ["b1"],
    });
  });

  const renderComponent = (partnerId = "p-uuid-1234") => {
    return render(
      <MemoryRouter initialEntries={[`/partners/${partnerId}`]}>
        <Routes>
          <Route path="/partners/:id" element={<PartnerDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );
  };

  it("renders partner profile, dashboard metrics, and configured rules", async () => {
    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue(
      mockDashboard,
    );
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue(mockRules);

    renderComponent();

    expect(screen.getByText("Loading partner details...")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Dr. Farhan Qureshi" }),
      ).toBeInTheDocument();
      expect(screen.getByText("PKR 22140.00")).toBeInTheDocument();
      expect(screen.getByText("PKR 0.00")).toBeInTheDocument();
      expect(screen.getByText("Pathology")).toBeInTheDocument();
      expect(screen.getByText("12.00%")).toBeInTheDocument();
      expect(screen.getByText("Upcoming Screen 38")).toBeInTheDocument();
      expect(screen.getByText("Upcoming Screen 41")).toBeInTheDocument();
    });
  });

  it("edits partner information via modal", async () => {
    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue(
      mockDashboard,
    );
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue(mockRules);
    vi.mocked(partnersService.updatePartner).mockResolvedValue({
      ...mockPartner,
      organisation: "Consultant Clinic",
    });

    renderComponent();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Dr. Farhan Qureshi" }),
      ).toBeInTheDocument();
    });

    const editBtn = screen.getByRole("button", { name: /edit/i });
    fireEvent.click(editBtn);

    expect(
      screen.getByRole("heading", { name: "Edit Referral Partner" }),
    ).toBeInTheDocument();

    const orgInput = screen.getByDisplayValue("Doctor");
    fireEvent.change(orgInput, { target: { value: "Consultant Clinic" } });

    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(partnersService.updatePartner).toHaveBeenCalledWith(
        "p-uuid-1234",
        {
          name: "Dr. Farhan Qureshi",
          organisation: "Consultant Clinic",
          phone: "+92 300 4567890",
          email: "farhan@example.com",
          is_active: true,
        },
      );
    });
  });

  it("toggles active status to deactivate partner", async () => {
    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue(
      mockDashboard,
    );
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue(mockRules);
    vi.mocked(partnersService.updatePartner).mockResolvedValue({
      ...mockPartner,
      is_active: false,
    });

    renderComponent();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /deactivate/i }),
      ).toBeInTheDocument();
    });

    const deactivateBtn = screen.getByRole("button", { name: /deactivate/i });
    fireEvent.click(deactivateBtn);

    await waitFor(() => {
      expect(partnersService.updatePartner).toHaveBeenCalledWith(
        "p-uuid-1234",
        {
          is_active: false,
        },
      );
    });
  });

  it("hides edit and deactivate controls for receptionists", async () => {
    useAuthStore.getState().setSession("mock-token", {
      id: "u3",
      email: "recp@labflow.app",
      name: "Sobia Receptionist",
      role: "reception",
      branch_ids: ["b1"],
    });

    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
    vi.mocked(partnersService.getPartnerDashboard).mockResolvedValue(
      mockDashboard,
    );
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue(mockRules);

    renderComponent();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Dr. Farhan Qureshi" }),
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /^edit$/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /deactivate/i }),
    ).not.toBeInTheDocument();
  });
});
