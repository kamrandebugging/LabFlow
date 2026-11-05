import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SettlementDetailScreen } from "../../features/partners/SettlementDetailScreen";
import {
  PartnerApiError,
  partnersService,
} from "../../features/partners/partnersService";
import { useAuthStore } from "../../features/auth/authStore";
import type {
  ReferralPartner,
  Settlement,
} from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getSettlement: vi.fn(),
      getPartner: vi.fn(),
      approveSettlement: vi.fn(),
      cancelSettlement: vi.fn(),
      markPaidSettlement: vi.fn(),
      sendSettlement: vi.fn(),
      getStatementPdfUrl: vi.fn(
        (id: string) => `/api/v1/settlements/${id}/statement.pdf`,
      ),
    },
  };
});

const mockPartner: ReferralPartner = {
  id: "p-uuid-1",
  name: "Dr. Farhan Qureshi",
  organisation: "Doctor",
  phone: "+92 300 1234567",
  email: "farhan@example.com",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockSettlement: Settlement = {
  id: "set-uuid-001",
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
  lines: [
    {
      id: "line-1",
      share_ledger_entry_id: "entry-uuid-101",
      amount: "486.00",
      entry_period: "2026-10",
    },
    {
      id: "line-2",
      share_ledger_entry_id: "entry-uuid-102",
      amount: "21654.00",
      entry_period: "2026-10",
    },
  ],
};

describe("SettlementDetailScreen (Screen 42)", () => {
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

    vi.mocked(partnersService.getSettlement).mockResolvedValue(mockSettlement);
    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
  });

  const renderComponent = (settlementId = "set-uuid-001") =>
    render(
      <MemoryRouter initialEntries={[`/settlements/${settlementId}`]}>
        <Routes>
          <Route path="/settlements/:id" element={<SettlementDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

  it("renders settlement details, partner info, and line items", async () => {
    renderComponent();

    expect(
      await screen.findByRole("heading", {
        name: /Settlement — Dr. Farhan Qureshi — 2026-10/i,
      }),
    ).toBeInTheDocument();

    expect(screen.getAllByText("DRAFT").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("PKR 22140.00").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByText("+92 300 1234567")).toBeInTheDocument();

    // Check line items
    expect(screen.getByText("PKR 486.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 21654.00")).toBeInTheDocument();

    // Check statement PDF link
    const pdfLink = screen.getByRole("link", {
      name: /download statement pdf/i,
    });
    expect(pdfLink).toHaveAttribute(
      "href",
      "/api/v1/settlements/set-uuid-001/statement.pdf",
    );
  });

  it("allows owner to approve settlement with If-Match version header", async () => {
    vi.mocked(partnersService.approveSettlement).mockResolvedValue({
      ...mockSettlement,
      status: "APPROVED",
      version: "2026-10-31T21:00:00Z",
    });

    renderComponent();

    await screen.findAllByText(/Dr. Farhan Qureshi/i);

    const approveBtn = screen.getByRole("button", {
      name: /approve settlement/i,
    });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(partnersService.approveSettlement).toHaveBeenCalledWith(
        "set-uuid-001",
        "2026-10-31T20:00:00Z",
      );
    });

    expect(
      await screen.findByText("Settlement approved successfully."),
    ).toBeInTheDocument();
  });

  it("handles version conflict 409/412 by re-fetching latest state", async () => {
    vi.mocked(partnersService.approveSettlement).mockRejectedValue(
      new PartnerApiError("Version conflict", "version_conflict", 409),
    );

    renderComponent();

    await screen.findAllByText(/Dr. Farhan Qureshi/i);

    const approveBtn = screen.getByRole("button", {
      name: /approve settlement/i,
    });
    fireEvent.click(approveBtn);

    expect(
      await screen.findByText(
        /Version conflict: This settlement was modified/i,
      ),
    ).toBeInTheDocument();

    // Verify fetchData was called again to retrieve current state
    await waitFor(() => {
      expect(partnersService.getSettlement).toHaveBeenCalledTimes(2);
    });
  });

  it("blocks unauthorized roles from viewing settlement details", async () => {
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
        "Only the Lab Owner and Manager can view settlement details.",
      ),
    ).toBeInTheDocument();
    expect(partnersService.getSettlement).not.toHaveBeenCalled();
  });
});
