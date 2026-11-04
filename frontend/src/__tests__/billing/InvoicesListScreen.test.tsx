import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { billingService } from "../../features/billing/billingService";
import { InvoicesListScreen } from "../../features/billing/InvoicesListScreen";
import type { InvoiceSummary } from "../../features/billing/types";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    listInvoices: vi.fn(),
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    recordPayment: vi.fn(),
    cancelInvoice: vi.fn(),
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
    render(<InvoicesListScreen />);

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
    render(<InvoicesListScreen />);

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
    render(<InvoicesListScreen onNewInvoice={handleNewInvoice} />);

    const newBtn = screen.getByRole("button", { name: /New invoice/i });
    fireEvent.click(newBtn);

    expect(handleNewInvoice).toHaveBeenCalledTimes(1);
  });

  it("triggers onSelectInvoice callback when clicking view invoice action", async () => {
    const handleSelect = vi.fn();
    render(<InvoicesListScreen onSelectInvoice={handleSelect} />);

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByRole("button", { name: /View/i });
    expect(viewButtons[0]).toBeDefined();
    fireEvent.click(viewButtons[0]!);

    expect(handleSelect).toHaveBeenCalledWith(mockInvoices[0]!.id);
  });
});
