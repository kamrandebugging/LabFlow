import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { billingService } from "../../features/billing/billingService";
import { InvoiceDetailScreen } from "../../features/billing/InvoiceDetailScreen";
import type {
  InvoiceDetail,
  PaymentRecord,
} from "../../features/billing/types";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    getInvoice: vi.fn(),
    recordPayment: vi.fn(),
    cancelInvoice: vi.fn(),
  },
}));

const mockInvoiceDetail: InvoiceDetail = {
  id: "0891a000-0000-0000-0000-000000000000",
  patient_id: "pat-uuid-001",
  patient_name: "Muhammad Imran",
  patient_mrn: "MRN-2026-00417",
  patient_phone: "+92 300 1234567",
  branch_id: "br-01",
  branch_name: "Gulberg Branch",
  status: "partial",
  subtotal: "2000.00",
  discount_amount: "200.00",
  discount_reason: "staff family",
  total: "1800.00",
  net_paid: "1000.00",
  items: [
    {
      id: "item-1",
      test_id: "test-haem-01",
      description: "CBC (Complete Blood Count)",
      unit_price: "800.00",
      quantity: 1,
      line_total: "800.00",
    },
    {
      id: "item-2",
      test_id: "test-bio-14",
      description: "HbA1c (Glycated Hemoglobin)",
      unit_price: "1200.00",
      quantity: 1,
      line_total: "1200.00",
    },
  ],
  payments: [
    {
      id: "pay-1",
      invoice_id: "0891a000-0000-0000-0000-000000000000",
      kind: "payment",
      method: "cash",
      amount: "1000.00",
      reference: "RCPT-2026-0914",
      received_by: "Bilal Ahmed",
      created_at: "2026-10-20T10:20:00Z",
    },
  ],
  created_at: "2026-10-20T10:15:00Z",
};

describe("Screen 15: Invoice Detail (15-invoice-detail.html & Doc 03 §5.3, §6.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(billingService.getInvoice).mockResolvedValue(mockInvoiceDetail);
  });

  it("renders invoice header, status badge, patient demographics, and balance due", async () => {
    render(<InvoiceDetailScreen invoiceId={mockInvoiceDetail.id} />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "INV-0891A000" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("MRN: MRN-2026-00417")).toBeInTheDocument();
      expect(screen.getByText("Gulberg Branch")).toBeInTheDocument();
      expect(screen.getAllByText("PKR 800.00").length).toBeGreaterThanOrEqual(
        1,
      ); // Balance Due and line item
    });
  });

  it("renders itemized tests and payments ledger", async () => {
    render(<InvoiceDetailScreen invoiceId={mockInvoiceDetail.id} />);

    await waitFor(() => {
      expect(
        screen.getByText("CBC (Complete Blood Count)"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("HbA1c (Glycated Hemoglobin)"),
      ).toBeInTheDocument();
      expect(screen.getByText(/RCPT-2026-0914/)).toBeInTheDocument();
    });
  });

  it("records payment against balance due", async () => {
    const mockPayment: PaymentRecord = {
      id: "pay-2",
      invoice_id: mockInvoiceDetail.id,
      kind: "payment",
      method: "cash",
      amount: "800.00",
      created_at: "2026-10-20T10:35:00Z",
    };
    vi.mocked(billingService.recordPayment).mockResolvedValue(mockPayment);

    render(<InvoiceDetailScreen invoiceId={mockInvoiceDetail.id} />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Record payment/i }),
      ).toBeInTheDocument();
    });

    const payBtn = screen.getByRole("button", { name: /Record payment/i });
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(billingService.recordPayment).toHaveBeenCalledWith(
        mockInvoiceDetail.id,
        expect.objectContaining({
          kind: "payment",
          amount: "800.00",
          method: "cash",
        }),
      );
    });
  });

  it("records refund with reason note", async () => {
    const mockRefund: PaymentRecord = {
      id: "ref-1",
      invoice_id: mockInvoiceDetail.id,
      kind: "refund",
      method: "cash",
      amount: "200.00",
      reference: "Test cancelled by doctor",
      created_at: "2026-10-20T10:40:00Z",
    };
    vi.mocked(billingService.recordPayment).mockResolvedValue(mockRefund);

    render(<InvoiceDetailScreen invoiceId={mockInvoiceDetail.id} />);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/Clinical or billing justification/i),
      ).toBeInTheDocument();
    });

    const refundAmountInput = screen.getByPlaceholderText("0.00");
    fireEvent.change(refundAmountInput, { target: { value: "200.00" } });

    const reasonInput = screen.getByPlaceholderText(
      /Clinical or billing justification/i,
    );
    fireEvent.change(reasonInput, {
      target: { value: "Test cancelled by doctor" },
    });

    const refundBtn = screen.getByRole("button", { name: /Record refund/i });
    fireEvent.click(refundBtn);

    await waitFor(() => {
      expect(billingService.recordPayment).toHaveBeenCalledWith(
        mockInvoiceDetail.id,
        expect.objectContaining({
          kind: "refund",
          amount: "200.00",
          reference: "Test cancelled by doctor",
        }),
      );
    });
  });

  it("cancels unpaid invoice when no payments settled", async () => {
    const unpaidInvoice: InvoiceDetail = {
      ...mockInvoiceDetail,
      status: "unpaid",
      net_paid: "0.00",
      payments: [],
    };
    vi.mocked(billingService.getInvoice).mockResolvedValue(unpaidInvoice);
    vi.mocked(billingService.cancelInvoice).mockResolvedValue({
      ...unpaidInvoice,
      status: "cancelled",
    });

    render(<InvoiceDetailScreen invoiceId={unpaidInvoice.id} />);

    await waitFor(() => {
      const cancelBtn = screen.getByRole("button", { name: /Cancel invoice/i });
      expect(cancelBtn).not.toBeDisabled();
      fireEvent.click(cancelBtn);
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const cancelReasonInput = screen.getByPlaceholderText(
      /Patient did not arrive/i,
    );
    fireEvent.change(cancelReasonInput, {
      target: { value: "Ordered by mistake" },
    });

    const confirmBtn = screen.getByRole("button", {
      name: "Confirm Cancellation",
    });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(billingService.cancelInvoice).toHaveBeenCalledWith(
        unpaidInvoice.id,
        "Ordered by mistake",
      );
    });
  });
});
