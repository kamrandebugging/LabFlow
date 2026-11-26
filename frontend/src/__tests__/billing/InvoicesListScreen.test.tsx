import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { billingService } from "../../features/billing/billingService";
import { settingsService } from "../../features/settings/settingsService";
import { InvoicesListScreen } from "../../features/billing/InvoicesListScreen";
import type { InvoiceSummary } from "../../features/billing/types";
import i18n from "../../i18n";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    listInvoices: vi.fn(),
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    recordPayment: vi.fn(),
    cancelInvoice: vi.fn(),
  },
}));

vi.mock("../../features/settings/settingsService", () => ({
  settingsService: {
    getBranches: vi.fn().mockResolvedValue([
      {
        id: "br-01",
        code: "GLB",
        name: "Gulberg Branch",
        address: null,
        phone: null,
        is_collection_centre: false,
        result_entry_enabled: true,
        deleted_at: null,
      },
      {
        id: "br-02",
        code: "NTH",
        name: "North Branch",
        address: null,
        phone: null,
        is_collection_centre: false,
        result_entry_enabled: true,
        deleted_at: null,
      },
    ]),
  },
}));

const mockInvoices: InvoiceSummary[] = [
  {
    id: "inv-uuid-001",
    patient_id: "pat-uuid-001",
    patient_name: "Muhammad Imran",
    patient_mrn: "MRN-2026-00417",
    branch_id: "br-01",
    branch_name: "Gulberg Branch",
    status: "paid",
    subtotal: "3850.00",
    discount_amount: "0.00",
    total: "3850.00",
    net_paid: "3850.00",
    items_summary: "Complete Blood Count, HbA1c",
    created_at: "2026-10-20T10:15:00Z",
  },
  {
    id: "inv-uuid-002",
    patient_id: "pat-uuid-002",
    patient_name: "Fatima Noor",
    patient_mrn: "MRN-2026-00892",
    branch_id: "br-01",
    branch_name: "Gulberg Branch",
    status: "partial",
    subtotal: "2000.00",
    discount_amount: "200.00",
    total: "1800.00",
    net_paid: "1000.00",
    items_summary: "Lipid Profile",
    created_at: "2026-10-20T11:30:00Z",
  },
];

describe("Screen 13: Invoices List (13-invoices.html & Doc 03 §5.3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: mockInvoices,
      daily_total: "5650.00",
    });
  });

  it("renders header, daily total badge, and table data", async () => {
    render(
      <MemoryRouter>
        <InvoicesListScreen />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: /Invoices/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Manage patient billing/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
      expect(screen.getByText("PKR 3850.00")).toBeInTheDocument();
      expect(screen.getByText(/5650\.00/)).toBeInTheDocument();
    });
  });

  it("filters invoices by status pill click", async () => {
    render(
      <MemoryRouter>
        <InvoicesListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const statusSelect = screen.getByLabelText(/Filter by status/i);
    fireEvent.change(statusSelect, { target: { value: "unpaid" } });

    await waitFor(() => {
      expect(billingService.listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ status: "unpaid" }),
      );
    });
  });

  it("triggers onNewInvoice callback when clicking New Invoice button", () => {
    const handleNewInvoice = vi.fn();
    render(
      <MemoryRouter>
        <InvoicesListScreen onNewInvoice={handleNewInvoice} />
      </MemoryRouter>,
    );

    const newBtn = screen.getByRole("button", { name: /New invoice/i });
    fireEvent.click(newBtn);

    expect(handleNewInvoice).toHaveBeenCalledTimes(1);
  });

  it("shows an unavailable daily total when the server omits it", async () => {
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: [],
    });

    render(
      <MemoryRouter>
        <InvoicesListScreen />
      </MemoryRouter>,
    );

    expect(await screen.findByText("—")).toBeInTheDocument();
    expect(screen.queryByText("PKR 0.00")).not.toBeInTheDocument();
  });

  it("triggers onSelectInvoice callback when clicking view invoice action", async () => {
    const handleSelect = vi.fn();
    render(
      <MemoryRouter>
        <InvoicesListScreen onSelectInvoice={handleSelect} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByRole("button", { name: /View/i });
    expect(viewButtons[0]).toBeDefined();
    fireEvent.click(viewButtons[0]!);

    expect(handleSelect).toHaveBeenCalledWith(mockInvoices[0]!.id);
  });

  it("renders Urdu invoice status labels, never raw i18n keys", async () => {
    await i18n.changeLanguage("ur");
    render(
      <MemoryRouter>
        <InvoicesListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    expect(screen.queryByText(/status\.invoice\./)).not.toBeInTheDocument();
    expect(
      screen.getAllByText(i18n.t("status.invoice.paid")).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(i18n.t("status.invoice.partial")).length,
    ).toBeGreaterThan(0);

    await i18n.changeLanguage("en");
  });

  it("passes search query, branch filter, and cursor pagination to listInvoices", async () => {
    vi.mocked(billingService.listInvoices)
      .mockResolvedValueOnce({
        results: [mockInvoices[0]!],
        next_cursor: "cursor-page-2",
        daily_total: "5650.00",
      })
      .mockResolvedValueOnce({
        results: [mockInvoices[1]!],
        next_cursor: null,
        daily_total: "5650.00",
      })
      .mockResolvedValue({
        results: [mockInvoices[0]!],
        next_cursor: null,
        daily_total: "5650.00",
      });

    expect(settingsService.getBranches).toBeDefined();

    render(
      <MemoryRouter>
        <InvoicesListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const nextBtn = screen.getByRole("button", { name: /next/i });
    const prevBtn = screen.getByRole("button", { name: /previous/i });
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();

    fireEvent.click(nextBtn);
    await waitFor(() => {
      expect(billingService.listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ cursor: "cursor-page-2" }),
      );
      expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /previous/i }));
    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const branchSelect = screen.getByLabelText(/Filter by branch/i);
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "North Branch" }),
      ).toBeInTheDocument();
    });
    fireEvent.change(branchSelect, { target: { value: "br-02" } });
    await waitFor(() => {
      expect(billingService.listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ branchId: "br-02" }),
      );
    });

    const searchInput = screen.getByPlaceholderText(/Search Invoice/i);
    fireEvent.change(searchInput, { target: { value: "INV-89521878" } });
    await waitFor(() => {
      expect(billingService.listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ q: "INV-89521878" }),
      );
    });
  });
});
