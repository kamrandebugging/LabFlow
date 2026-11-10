import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PartnersListScreen } from "../../features/partners/PartnersListScreen";
import {
  PartnerApiError,
  partnersService,
} from "../../features/partners/partnersService";
import { useAuthStore } from "../../features/auth/authStore";
import type { ReferralPartner } from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartners: vi.fn(),
      createPartner: vi.fn(),
      deletePartner: vi.fn(),
    },
  };
});

const mockPartners: ReferralPartner[] = [
  {
    id: "p1",
    name: "Dr. Farhan Qureshi",
    organisation: "Doctor",
    phone: "+92 300 4567890",
    email: "farhan@example.com",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "p2",
    name: "Al-Shifa Clinic",
    organisation: "Clinic",
    phone: "+92 42 35887766",
    email: "alshifa@example.com",
    is_active: false,
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  },
];

describe("Screen 36: PartnersListScreen (/partners)", () => {
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

  it("renders header, summary metrics, and partner table", async () => {
    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);

    render(
      <MemoryRouter>
        <PartnersListScreen />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Referral Partners" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Loading referral partners..."),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Dr. Farhan Qureshi")).toBeInTheDocument();
      expect(screen.getByText("Al-Shifa Clinic")).toBeInTheDocument();
      expect(screen.getByText("Showing 2 partners")).toBeInTheDocument();
    });

    // Check summary metrics
    expect(screen.getByText("Total Partners")).toBeInTheDocument();
    expect(screen.getByText("Active Referrals")).toBeInTheDocument();
    expect(screen.getByText("Inactive / Paused")).toBeInTheDocument();
  });

  it("filters partners by search input", async () => {
    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);

    render(
      <MemoryRouter>
        <PartnersListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Dr. Farhan Qureshi")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search by name/i);
    fireEvent.change(searchInput, { target: { value: "Al-Shifa" } });

    expect(screen.queryByText("Dr. Farhan Qureshi")).not.toBeInTheDocument();
    expect(screen.getByText("Al-Shifa Clinic")).toBeInTheDocument();
  });

  it("creates a new partner via modal", async () => {
    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);
    vi.mocked(partnersService.createPartner).mockResolvedValue({
      id: "p3",
      name: "Dr. Nadia Aslam",
      organisation: "Hospital",
      phone: "+92 321 9876543",
      email: "nadia@example.com",
      is_active: true,
      created_at: "2026-01-03T00:00:00Z",
      updated_at: "2026-01-03T00:00:00Z",
    });

    render(
      <MemoryRouter>
        <PartnersListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Dr. Farhan Qureshi")).toBeInTheDocument();
    });

    const addBtn = screen.getByRole("button", { name: /\+ add partner/i });
    fireEvent.click(addBtn);

    expect(
      screen.getByRole("heading", { name: "Add Referral Partner" }),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(/e\.g\. Dr\. Farhan Qureshi/i),
      {
        target: { value: "Dr. Nadia Aslam" },
      },
    );
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. Al-Shifa Clinic/i), {
      target: { value: "Hospital" },
    });

    const submitBtn = screen.getByRole("button", { name: /create partner/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(partnersService.createPartner).toHaveBeenCalledWith({
        name: "Dr. Nadia Aslam",
        organisation: "Hospital",
        phone: null,
        email: null,
        is_active: true,
      });
    });
  });

  it("surfaces 409 partner_has_ledger_entries blocker on delete", async () => {
    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);
    vi.mocked(partnersService.deletePartner).mockRejectedValue(
      new PartnerApiError(
        "Cannot delete partner with ledger entries.",
        "partner_has_ledger_entries",
        409,
      ),
    );

    render(
      <MemoryRouter>
        <PartnersListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Dr. Farhan Qureshi")).toBeInTheDocument();
    });

    const deleteBtn = screen.getByLabelText(
      "Delete partner Dr. Farhan Qureshi",
    );
    fireEvent.click(deleteBtn);

    expect(
      screen.getByRole("heading", { name: "Delete Referral Partner" }),
    ).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: /confirm delete/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/financial integrity blocker/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Partners with ledger history cannot be deleted/i),
      ).toBeInTheDocument();
    });
  });

  it("hides add and delete actions for receptionist", async () => {
    useAuthStore.getState().setSession("mock-token", {
      id: "u3",
      email: "recp@labflow.app",
      name: "Sobia Receptionist",
      role: "reception",
      branch_ids: ["b1"],
    });

    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);

    render(
      <MemoryRouter>
        <PartnersListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Dr. Farhan Qureshi")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /\+ add partner/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/delete partner/i)).not.toBeInTheDocument();
  });
});
