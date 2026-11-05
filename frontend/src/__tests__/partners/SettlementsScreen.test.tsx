import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SettlementsScreen } from "../../features/partners/SettlementsScreen";
import { partnersService } from "../../features/partners/partnersService";
import { useAuthStore } from "../../features/auth/authStore";
import type {
  ReferralPartner,
  Settlement,
  SettlementExceptionsData,
} from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartners: vi.fn(),
      getSettlements: vi.fn(),
      getSettlementExceptions: vi.fn(),
    },
  };
});

const mockPartners: ReferralPartner[] = [
  {
    id: "p-uuid-1",
    name: "Dr. Farhan Qureshi",
    organisation: "Doctor",
    phone: "+92 300 1234567",
    email: "farhan@example.com",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockSettlements: Settlement[] = [
  {
    id: "set-uuid-001-aaaa",
    referral_partner_id: "p-uuid-1",
    period: "2026-10",
    status: "DRAFT",
    total: "22140.00",
    statement_pdf_key: null,
    approved_by: null,
    approved_at: null,
    version: "2026-10-31T20:00:00Z",
    created_at: "2026-10-31T20:00:00Z",
    updated_at: "2026-10-31T20:00:00Z",
  },
  {
    id: "set-uuid-002-bbbb",
    referral_partner_id: "p-uuid-1",
    period: "2026-09",
    status: "PAID",
    total: "18500.00",
    statement_pdf_key: "reports/statements/set-2.pdf",
    approved_by: "u-owner",
    approved_at: "2026-10-02T10:00:00Z",
    version: "2026-10-03T11:00:00Z",
    created_at: "2026-09-30T20:00:00Z",
    updated_at: "2026-10-03T11:00:00Z",
  },
];

const mockExceptions: SettlementExceptionsData = {
  drafts_awaiting_approval: 1,
  drafts_older_than_7_days: 0,
  failed_deliveries: 0,
};

describe("SettlementsScreen (Screen 41)", () => {
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

    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);
    vi.mocked(partnersService.getSettlementExceptions).mockResolvedValue(
      mockExceptions,
    );
    vi.mocked(partnersService.getSettlements).mockResolvedValue({
      results: mockSettlements,
      next_cursor: null,
    });
  });

  const renderComponent = (initialRoute = "/settlements") =>
    render(
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/settlements" element={<SettlementsScreen />} />
        </Routes>
      </MemoryRouter>,
    );

  it("renders settlements header, exceptions banner, and settlements table", async () => {
    renderComponent();

    expect(
      await screen.findByRole("heading", { name: "Settlements" }),
    ).toBeInTheDocument();

    // Exceptions banner
    expect(
      screen.getByText("Settlement Exceptions Detected"),
    ).toBeInTheDocument();
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument();

    // Table rows
    expect(
      (await screen.findAllByText("Dr. Farhan Qureshi")).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("2026-10")).toBeInTheDocument();
    expect(screen.getByText("PKR 22140.00")).toBeInTheDocument();
    expect(screen.getByText("DRAFT")).toBeInTheDocument();

    expect(screen.getByText("2026-09")).toBeInTheDocument();
    expect(screen.getByText("PKR 18500.00")).toBeInTheDocument();
    expect(screen.getByText("PAID")).toBeInTheDocument();
  });

  it("switches status filter tab and calls API with status", async () => {
    renderComponent();

    await screen.findAllByText("Dr. Farhan Qureshi");

    const draftTab = screen.getByRole("button", { name: /^Draft$/i });
    fireEvent.click(draftTab);

    await waitFor(() => {
      expect(partnersService.getSettlements).toHaveBeenCalledWith(
        expect.objectContaining({
          status: "DRAFT",
        }),
      );
    });
  });

  it("renders honest empty state when no settlements match", async () => {
    vi.mocked(partnersService.getSettlements).mockResolvedValue({
      results: [],
      next_cursor: null,
    });

    renderComponent();

    expect(
      await screen.findByText("No settlements found matching the criteria."),
    ).toBeInTheDocument();
  });

  it("blocks unauthorized roles (e.g. receptionist) from viewing settlements", async () => {
    useAuthStore.setState({
      user: {
        id: "u-rec",
        email: "rec@labflow.pk",
        role: "receptionist",
        name: "Reception Staff",
        branch_ids: ["b-1"],
      },
      accessToken: "mock-token",
    });

    renderComponent();

    expect(await screen.findByText("Access Restricted")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Only the Lab Owner and Manager can view monthly settlements.",
      ),
    ).toBeInTheDocument();
    expect(partnersService.getSettlements).not.toHaveBeenCalled();
  });
});
