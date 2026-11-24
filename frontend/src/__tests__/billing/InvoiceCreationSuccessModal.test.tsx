import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InvoiceCreationSuccessModal } from "../../features/billing/components/InvoiceCreationSuccessModal";
import type { InvoiceDetail } from "../../features/billing/types";
import i18n from "../../i18n";

describe("InvoiceCreationSuccessModal", () => {
  const mockInvoice: InvoiceDetail = {
    id: "inv-uuid-1234",
    invoice_number: "INV-20261124001",
    patient_id: "pat-123",
    patient_name: "Tariq Mahmood",
    patient_mrn: "MRN-26-000412",
    branch_id: "br-01",
    status: "unpaid",
    subtotal: "3200.00",
    discount_amount: "200.00",
    total: "3000.00",
    net_paid: "0.00",
    created_at: "2026-11-24T12:00:00Z",
    payments: [],
    items: [
      {
        id: "item-1",
        test_id: "t-1",
        description: "Complete Blood Count",
        name: "Complete Blood Count",
        quantity: 1,
        unit_price: "1000.00",
        line_total: "1000.00",
      },
      {
        id: "item-2",
        panel_id: "p-1",
        description: "Lipid Profile",
        name: "Lipid Profile",
        quantity: 1,
        unit_price: "2200.00",
        line_total: "2200.00",
      },
    ],
  };

  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders when open with invoice details, items, amounts, and actions", () => {
    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onRecordPayment={vi.fn()}
        onPrint={vi.fn()}
        onViewDetails={vi.fn()}
        onCreateAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /Invoice Created Successfully/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("INV-20261124001")).toBeInTheDocument();
    expect(screen.getByText("Tariq Mahmood")).toBeInTheDocument();
    expect(screen.getAllByText("PKR 3000.00").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Complete Blood Count")).toBeInTheDocument();
    expect(screen.getByText("Lipid Profile")).toBeInTheDocument();
    expect(screen.getByTestId("record-payment-btn")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <InvoiceCreationSuccessModal
        isOpen={false}
        invoice={mockInvoice}
        onClose={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onRecordPayment when Record Payment button is clicked", () => {
    const handleRecordPayment = vi.fn();
    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onRecordPayment={handleRecordPayment}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("record-payment-btn"));
    expect(handleRecordPayment).toHaveBeenCalledWith("inv-uuid-1234");
  });

  it("calls onCollectSpecimen when invoice is paid and Collect button is clicked", () => {
    const paidInvoice: InvoiceDetail = {
      ...mockInvoice,
      status: "paid",
      net_paid: "3000.00",
    };
    const handleCollect = vi.fn();
    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={paidInvoice}
        onCollectSpecimen={handleCollect}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("collect-specimen-btn"));
    expect(handleCollect).toHaveBeenCalledWith("inv-uuid-1234");
  });

  it("calls onPrint when Print Invoice is clicked", () => {
    const handlePrint = vi.fn();
    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onPrint={handlePrint}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("print-invoice-btn"));
    expect(handlePrint).toHaveBeenCalledWith("inv-uuid-1234");
  });

  it("calls onViewDetails and onCreateAnother on respective clicks", () => {
    const handleView = vi.fn();
    const handleCreateAnother = vi.fn();
    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onViewDetails={handleView}
        onCreateAnother={handleCreateAnother}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("view-invoice-details-btn"));
    expect(handleView).toHaveBeenCalledWith("inv-uuid-1234");

    fireEvent.click(screen.getByTestId("create-another-invoice-btn"));
    expect(handleCreateAnother).toHaveBeenCalledTimes(1);
  });

  it("copies invoice number to clipboard on copy button click", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("copy-invoice-btn"));
    expect(writeTextMock).toHaveBeenCalledWith("INV-20261124001");

    await waitFor(() => {
      expect(screen.getByText(/Copied!/i)).toBeInTheDocument();
    });
  });

  it("renders in Urdu properly when language is set to ur", async () => {
    await i18n.changeLanguage("ur");

    render(
      <InvoiceCreationSuccessModal
        isOpen={true}
        invoice={mockInvoice}
        onRecordPayment={vi.fn()}
        onPrint={vi.fn()}
        onViewDetails={vi.fn()}
        onCreateAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /انوائس کامیابی سے تیار ہو گئی/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/انوائس نمبر/i)).toBeInTheDocument();
    expect(screen.getByText(/ابھی ادائیگی درج کریں/i)).toBeInTheDocument();
    expect(screen.getByText(/انوائس پرنٹ کریں/i)).toBeInTheDocument();
  });
});
