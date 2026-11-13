import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LedgerScreen } from "../../features/partners/LedgerScreen";
import { partnersService } from "../../features/partners/partnersService";
import type {
  ReferralPartner,
  ShareLedgerResponse,
} from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartners: vi.fn(),
      getShareLedger: vi.fn(),
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

const mockLedgerResponse: ShareLedgerResponse = {
  results: [
    {
      id: "entry-1",
      payment_id: "PAY-202610-001",
      referral_partner_id: "p-uuid-1",
      referral_partner_name: "Dr. Farhan Qureshi",
      rule_id: "rule-1",
      rule_percent: "12.00",
      amount: "486.00",
      percent_applied: "12.00",
      basis_amount: "4050.00",
      period: "2026-10",
      created_at: "2026-10-19T17:15:00Z",
      settlement: {
        id: "set-uuid-101",
        period: "2026-10",
        status: "DRAFT",
      },
    },
    {
      id: "entry-2",
      payment_id: "PAY-202610-002",
      referral_partner_id: "p-uuid-1",
      referral_partner_name: "Dr. Farhan Qureshi",
      rule_id: "rule-1",
      rule_percent: "10.00",
      amount: "250.00",
      percent_applied: "10.00",
      basis_amount: "2500.00",
      period: "2026-10",
      created_at: "2026-10-18T10:00:00Z",
      settlement: null,
    },
  ],
  next_cursor: "cursor-token-xyz",
  totals: {
    count: 2,
    amount: "736.00",
  },
};

describe("LedgerScreen (Screen 39)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(partnersService.getPartners).mockResolvedValue(mockPartners);
    vi.mocked(partnersService.getShareLedger).mockResolvedValue(
      mockLedgerResponse,
    );
  });

  const renderComponent = (initialRoute = "/partners/ledger") =>
    render(
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/partners/ledger" element={<LedgerScreen />} />
        </Routes>
      </MemoryRouter>,
    );

  it("renders ledger header, audit lock, and summary stat cards", async () => {
    renderComponent();

    expect(
      await screen.findByRole("heading", { name: "Revenue Share Ledger" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Append-only — entries cannot be edited or deleted."),
    ).toBeInTheDocument();
    expect(screen.getByText("PKR 736.00")).toBeInTheDocument();
    expect(screen.getByText("2 total ledger entries")).toBeInTheDocument();
    expect(screen.getByText("1 Unsettled")).toBeInTheDocument();
  });

  it("renders ledger entries with payment ref, amounts, and settlement badges", async () => {
    renderComponent();

    expect(await screen.findByText("PAY-202610-001")).toBeInTheDocument();
    expect(screen.getByText("PAY-202610-002")).toBeInTheDocument();
    expect(screen.getByText("PKR 486.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 250.00")).toBeInTheDocument();

    // Check linked settlement badge
    expect(screen.getByText("Draft")).toBeInTheDocument();
    // Check unsettled badge
    expect(screen.getByText("Unsettled")).toBeInTheDocument();
  });

  it("filters ledger by partner using partner dropdown", async () => {
    renderComponent();

    await screen.findByText("PAY-202610-001");

    const partnerSelect = screen.getByRole("combobox", {
      name: /filter by partner/i,
    });
    fireEvent.change(partnerSelect, { target: { value: "p-uuid-1" } });

    await waitFor(() => {
      expect(partnersService.getShareLedger).toHaveBeenCalledWith(
        expect.objectContaining({
          partner_id: "p-uuid-1",
        }),
      );
    });
  });

  it("filters rows client-side via search input", async () => {
    renderComponent();

    await screen.findByText("PAY-202610-001");

    const searchInput = screen.getByPlaceholderText(
      /search invoice ref, partner or entry id/i,
    );
    fireEvent.change(searchInput, { target: { value: "PAY-202610-002" } });

    expect(screen.queryByText("PAY-202610-001")).not.toBeInTheDocument();
    expect(screen.getByText("PAY-202610-002")).toBeInTheDocument();
  });

  it("renders honest empty state when no entries are returned", async () => {
    vi.mocked(partnersService.getShareLedger).mockResolvedValue({
      results: [],
      next_cursor: null,
      totals: { count: 0, amount: "0.00" },
    });

    renderComponent();

    expect(
      await screen.findByText("No ledger entries found for this selection."),
    ).toBeInTheDocument();
  });
});
