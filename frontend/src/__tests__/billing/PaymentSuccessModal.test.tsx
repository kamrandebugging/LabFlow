import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PaymentSuccessModal } from "../../features/billing/components/PaymentSuccessModal";
import type { InvoiceDetail } from "../../features/billing/types";
import i18n from "../../i18n";

describe("PaymentSuccessModal", () => {
  const mockInvoice: InvoiceDetail = {
    id: "inv-uuid-5678",
    invoice_number: "INV-20261124002",
    patient_id: "pat-456",
    patient_name: "Fatima Noor",
    patient_mrn: "MRN-26-000413",
    branch_id: "br-01",
    status: "paid",
    subtotal: "2500.00",
    discount_amount: "0.00",
    total: "2500.00",
    net_paid: "2500.00",
    created_at: "2026-11-24T12:30:00Z",
    items: [],
    payments: [],
  };

  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders when open with payment amount, method, reference, and settled balance", () => {
    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        reference="REC-20261124001"
        invoice={mockInvoice}
        onPrintReceipt={vi.fn()}
        onProceedToSamples={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /Payment Recorded Successfully/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("REC-20261124001")).toBeInTheDocument();
    expect(screen.getByText("PKR 2500.00")).toBeInTheDocument();
    expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
    expect(screen.getByText(/Fully Settled/i)).toBeInTheDocument();
    expect(screen.getByTestId("print-receipt-btn")).toBeInTheDocument();
    expect(screen.getByTestId("proceed-to-samples-btn")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <PaymentSuccessModal
        isOpen={false}
        amount="2500.00"
        method="cash"
        invoice={mockInvoice}
        onClose={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("displays partial remaining balance when invoice is not fully settled", () => {
    const partialInvoice: InvoiceDetail = {
      ...mockInvoice,
      status: "partial",
      total: "5000.00",
      net_paid: "2000.00",
    };

    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2000.00"
        method="bank_transfer"
        invoice={partialInvoice}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("PKR 3000.00")).toBeInTheDocument();
  });

  it("calls onPrintReceipt when print button is clicked", () => {
    const handlePrint = vi.fn();
    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        invoice={mockInvoice}
        onPrintReceipt={handlePrint}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("print-receipt-btn"));
    expect(handlePrint).toHaveBeenCalledTimes(1);
  });

  it("calls onProceedToSamples when proceed to samples button is clicked", () => {
    const handleProceed = vi.fn();
    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        invoice={mockInvoice}
        onProceedToSamples={handleProceed}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("proceed-to-samples-btn"));
    expect(handleProceed).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when done or view invoice is clicked", () => {
    const handleClose = vi.fn();
    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        invoice={mockInvoice}
        onClose={handleClose}
      />,
    );

    fireEvent.click(screen.getByTestId("done-payment-btn"));
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("view-invoice-btn"));
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it("copies receipt reference to clipboard on copy click", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        reference="REC-TEST-REF-999"
        invoice={mockInvoice}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("copy-payment-ref-btn"));
    expect(writeTextMock).toHaveBeenCalledWith("REC-TEST-REF-999");

    await waitFor(() => {
      expect(screen.getByText(/Copied!/i)).toBeInTheDocument();
    });
  });

  it("renders properly in Urdu when language is changed to ur", async () => {
    await i18n.changeLanguage("ur");

    render(
      <PaymentSuccessModal
        isOpen={true}
        amount="2500.00"
        method="cash"
        invoice={mockInvoice}
        onPrintReceipt={vi.fn()}
        onProceedToSamples={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /ادائیگی کامیابی سے درج ہو گئی/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/رسید \/ حوالہ نمبر/i)).toBeInTheDocument();
    expect(screen.getByText(/ادائیگی کی رسید پرنٹ کریں/i)).toBeInTheDocument();
    expect(
      screen.getByText(/نمونہ جمع کرنے کی طرف جائیں/i),
    ).toBeInTheDocument();
  });
});
