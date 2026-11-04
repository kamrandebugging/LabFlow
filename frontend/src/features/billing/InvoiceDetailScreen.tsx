import { useCallback, useEffect, useId, useState } from "react";
import { billingService } from "./billingService";
import type { InvoiceDetail, InvoiceStatus, PaymentMethod } from "./types";

export interface InvoiceDetailScreenProps {
  invoiceId: string;
  onBack?: () => void;
  onProceedToSamples?: (invoice: InvoiceDetail) => void;
}

function getStatusBadge(status: InvoiceStatus): JSX.Element {
  switch (status) {
    case "paid":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
          Paid
        </span>
      );
    case "partial":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-600" />
          Partial
        </span>
      );
    case "unpaid":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
          Unpaid
        </span>
      );
    case "refunded":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-600" />
          Refunded
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
          Cancelled
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
          {status}
        </span>
      );
  }
}

function formatPkt(dateStr?: string): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return (
      d.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "Asia/Karachi",
      }) +
      " · " +
      d.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Asia/Karachi",
      }) +
      " PKT"
    );
  } catch {
    return dateStr;
  }
}

export function InvoiceDetailScreen({
  invoiceId,
  onBack,
  onProceedToSamples,
}: InvoiceDetailScreenProps): JSX.Element {
  const payAmountId = useId();
  const payMethodId = useId();
  const payRefId = useId();
  const refundAmountId = useId();
  const refundMethodId = useId();
  const refundReasonId = useId();
  const cancelReasonId = useId();

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Payment Form State
  const [payAmount, setPayAmount] = useState<string>("");
  const [payMethod, setPayMethod] = useState<PaymentMethod>("cash");
  const [payReference, setPayReference] = useState<string>("");
  const [submittingPayment, setSubmittingPayment] = useState(false);

  // Refund Form State
  const [refundAmount, setRefundAmount] = useState<string>("");
  const [refundMethod, setRefundMethod] = useState<PaymentMethod>("cash");
  const [refundReason, setRefundReason] = useState<string>("");
  const [submittingRefund, setSubmittingRefund] = useState(false);

  // Cancel Modal State
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [submittingCancel, setSubmittingCancel] = useState(false);

  const fetchInvoice = useCallback(async () => {
    try {
      setLoading(true);
      const data = await billingService.getInvoice(invoiceId);
      setInvoice(data);
      // Pre-fill payment amount with balance due if any
      const totalNum = parseFloat(data.total || "0") || 0;
      const netPaidNum = parseFloat(data.net_paid || "0") || 0;
      const balance = Math.max(0, totalNum - netPaidNum);
      setPayAmount(balance > 0 ? balance.toFixed(2) : "");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load invoice.",
      );
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    fetchInvoice();
  }, [fetchInvoice]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const handleRecordPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invoice) return;
    setErrorMessage(null);

    const amt = parseFloat(payAmount);
    if (isNaN(amt) || amt <= 0) {
      setErrorMessage("Please enter a valid positive payment amount.");
      return;
    }

    if (payMethod !== "cash" && !payReference.trim()) {
      setErrorMessage(
        "Reference / Transaction note is required for non-cash payments.",
      );
      return;
    }

    try {
      setSubmittingPayment(true);
      await billingService.recordPayment(invoice.id, {
        kind: "payment",
        method: payMethod,
        amount: amt.toFixed(2),
        reference: payReference.trim() || undefined,
      });
      showToast(`Payment of PKR ${amt.toFixed(2)} recorded successfully.`);
      setPayReference("");
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to record payment.",
      );
    } finally {
      setSubmittingPayment(false);
    }
  };

  const handleRecordRefund = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invoice) return;
    setErrorMessage(null);

    const amt = parseFloat(refundAmount);
    if (isNaN(amt) || amt <= 0) {
      setErrorMessage("Please enter a valid positive refund amount.");
      return;
    }

    const netPaidNum = parseFloat(invoice.net_paid || "0") || 0;
    if (amt > netPaidNum) {
      setErrorMessage(
        `Refund amount cannot exceed total settled funds (PKR ${netPaidNum.toFixed(2)}).`,
      );
      return;
    }

    if (!refundReason.trim()) {
      setErrorMessage("A refund reason note is required.");
      return;
    }

    try {
      setSubmittingRefund(true);
      await billingService.recordPayment(invoice.id, {
        kind: "refund",
        method: refundMethod,
        amount: amt.toFixed(2),
        reference: refundReason.trim(),
      });
      showToast(`Refund of PKR ${amt.toFixed(2)} recorded successfully.`);
      setRefundAmount("");
      setRefundReason("");
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to record refund.",
      );
    } finally {
      setSubmittingRefund(false);
    }
  };

  const handleConfirmCancel = async () => {
    if (!invoice) return;
    if (!cancelReason.trim()) {
      setErrorMessage("Cancellation reason is required.");
      return;
    }

    try {
      setSubmittingCancel(true);
      await billingService.cancelInvoice(invoice.id, cancelReason.trim());
      showToast("Invoice has been successfully cancelled.");
      setShowCancelModal(false);
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to cancel invoice.",
      );
    } finally {
      setSubmittingCancel(false);
    }
  };

  const handlePrintReceipt = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3 text-slate-500 text-sm">
          <div className="w-8 h-8 border-4 border-teal-600 border-t-transparent rounded-full animate-spin" />
          <span>Loading invoice statement...</span>
        </div>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-800 font-semibold mb-2">Invoice Not Found</p>
          <p className="text-xs text-red-600 mb-4">
            {errorMessage || "The requested invoice could not be loaded."}
          </p>
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="px-4 py-2 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              Back to Invoices
            </button>
          )}
        </div>
      </div>
    );
  }

  const subtotalNum = parseFloat(invoice.subtotal || "0") || 0;
  const discountNum = parseFloat(invoice.discount_amount || "0") || 0;
  const totalNum = parseFloat(invoice.total || "0") || 0;
  const netPaidNum = parseFloat(invoice.net_paid || "0") || 0;
  const balanceDue = Math.max(0, totalNum - netPaidNum);
  const canCancel = invoice.status === "unpaid" && netPaidNum === 0;

  return (
    <div className="w-full max-w-7xl mx-auto px-4 py-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          role="status"
          className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs px-4 py-3 rounded-lg shadow-lg flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px] text-teal-400">
            check_circle
          </span>
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Breadcrumb & Timestamp */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <button
            type="button"
            onClick={onBack}
            className="hover:text-slate-700 transition-colors cursor-pointer"
          >
            Invoices
          </button>
          <span>/</span>
          <span className="font-mono text-slate-900 font-medium">
            {invoice.id
              ? `INV-${invoice.id.substring(0, 8).toUpperCase()}`
              : "Detail"}
          </span>
        </div>
        <div className="text-xs font-mono text-slate-500">
          {formatPkt(invoice.created_at)}
        </div>
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div
          role="alert"
          className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start gap-3"
        >
          <span className="material-symbols-outlined text-red-600 text-[20px] shrink-0 mt-0.5">
            error
          </span>
          <div className="flex-1 font-medium">{errorMessage}</div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-red-500 hover:text-red-700 font-bold"
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* INVOICE HEADER CARD */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm mb-6">
        <div className="flex flex-col lg:flex-row justify-between lg:items-start gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
                {`INV-${invoice.id.substring(0, 8).toUpperCase()}`}
              </h1>
              {getStatusBadge(invoice.status)}
              <span className="text-xs bg-slate-100 text-slate-600 px-2.5 py-0.5 rounded font-medium border border-slate-200">
                Outpatient Accession
              </span>
            </div>
            <div className="text-sm text-slate-600 flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="font-medium text-slate-900">
                {invoice.patient_name || "Patient Record"}
              </span>
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="font-mono text-slate-500">
                {invoice.patient_mrn
                  ? `MRN: ${invoice.patient_mrn}`
                  : "MRN: Pending"}
              </span>
              {invoice.patient_phone && (
                <>
                  <span className="text-slate-300 hidden sm:inline">|</span>
                  <span className="font-mono text-slate-500">
                    {invoice.patient_phone}
                  </span>
                </>
              )}
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="text-slate-600 font-medium">
                {invoice.branch_name || "Branch Counter"}
              </span>
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="font-mono text-slate-500">
                {formatPkt(invoice.created_at)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 self-start shrink-0">
            <button
              type="button"
              onClick={handlePrintReceipt}
              className="inline-flex items-center gap-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-800 text-xs font-semibold px-3 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">
                print
              </span>
              <span>Print Receipt</span>
            </button>
            {onProceedToSamples && (
              <button
                type="button"
                onClick={() => onProceedToSamples(invoice)}
                className="inline-flex items-center gap-1.5 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold px-3.5 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">
                  science
                </span>
                <span>Collect Samples</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* MAIN 12-COL GRID */}
      <div className="grid grid-cols-12 gap-6">
        {/* LEFT COLUMN: LINES & PAYMENT LEDGER (7 COLS) */}
        <div className="col-span-12 lg:col-span-7 space-y-6">
          {/* Lines & Pricing Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                Lines &amp; Pricing
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {invoice.items?.length || 0}{" "}
                {invoice.items?.length === 1 ? "item" : "items"} included
              </span>
            </div>

            {/* Table Header */}
            <div className="grid grid-cols-12 text-xs uppercase font-medium text-slate-400 py-2.5 border-b border-slate-100 mt-2">
              <div className="col-span-7">Item / Description</div>
              <div className="col-span-2 text-center">Qty</div>
              <div className="col-span-3 text-right">Line Total</div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-slate-100">
              {invoice.items && invoice.items.length > 0 ? (
                invoice.items.map((it) => (
                  <div
                    key={it.id}
                    className="grid grid-cols-12 py-3 items-center"
                  >
                    <div className="col-span-7 pr-2">
                      <div className="font-medium text-slate-900 text-sm">
                        {it.description}
                      </div>
                    </div>
                    <div className="col-span-2 text-center text-xs font-mono text-slate-600">
                      {it.quantity}
                    </div>
                    <div className="col-span-3 text-right font-mono text-xs font-medium text-slate-900">
                      PKR{" "}
                      {parseFloat(
                        it.line_total || it.unit_price || "0",
                      ).toFixed(2)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="py-4 text-center text-xs text-slate-400">
                  No items on this invoice.
                </div>
              )}
            </div>

            {/* Calculation Stack */}
            <div className="pt-4 mt-2 border-t border-slate-100 space-y-2.5">
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-600">Gross Subtotal</span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                  PKR {subtotalNum.toFixed(2)}
                </span>
              </div>
              {discountNum > 0 && (
                <div className="flex justify-between items-center text-sm bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  <div>
                    <div className="font-medium text-slate-900 text-xs">
                      Discount Applied
                    </div>
                    {invoice.discount_reason && (
                      <div className="text-[11px] text-slate-500">
                        Reason: {invoice.discount_reason}
                      </div>
                    )}
                  </div>
                  <span className="bg-slate-100 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                    - PKR {discountNum.toFixed(2)}
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center text-sm pt-1">
                <span className="text-slate-700 font-semibold">
                  Net Payable
                </span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-bold">
                  PKR {totalNum.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-600">Total Settled Funds</span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                  PKR {netPaidNum.toFixed(2)}
                </span>
              </div>
              <div className="border-t border-slate-200 my-2" />

              {/* Balance Due Callout */}
              <div className="flex justify-between items-center pt-1">
                <div>
                  <div className="text-base font-bold text-slate-900">
                    Balance Due
                  </div>
                  <div className="text-xs text-amber-600 font-medium">
                    {balanceDue > 0
                      ? "Payment outstanding at counter"
                      : "Fully settled"}
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`text-xl font-bold font-mono px-4 py-2 rounded-lg inline-block border ${
                      balanceDue > 0
                        ? "bg-amber-50 text-amber-900 border-amber-200"
                        : "bg-emerald-50 text-emerald-900 border-emerald-200"
                    }`}
                  >
                    PKR {balanceDue.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Payments Ledger Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                Payments Ledger
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {invoice.payments?.length || 0}{" "}
                {invoice.payments?.length === 1 ? "entry" : "entries"} recorded
              </span>
            </div>

            <div className="mt-4 space-y-3">
              {invoice.payments && invoice.payments.length > 0 ? (
                invoice.payments.map((p) => {
                  const isRefund = p.kind === "refund";
                  return (
                    <div
                      key={p.id}
                      className={`border rounded-lg p-3.5 flex justify-between items-start transition-colors ${
                        isRefund
                          ? "bg-red-50/40 border-red-200"
                          : "bg-white border-slate-200"
                      }`}
                    >
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-medium text-slate-700">
                            {formatPkt(p.created_at)}
                          </span>
                          <span className="text-slate-400">·</span>
                          <span
                            className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded capitalize ${
                              isRefund
                                ? "bg-red-100 text-red-800"
                                : "bg-slate-100 text-slate-800"
                            }`}
                          >
                            {p.kind}: {p.method.replace("_", " ")}
                          </span>
                        </div>
                        {p.reference && (
                          <div className="text-xs text-slate-500 mt-1">
                            Ref:{" "}
                            <span className="font-mono">{p.reference}</span>
                          </div>
                        )}
                        {p.received_by && (
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            Cashier / Operator: {p.received_by}
                          </div>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <span
                          className={`font-mono font-bold text-sm px-2.5 py-1 rounded inline-block border ${
                            isRefund
                              ? "bg-red-50 text-red-700 border-red-200"
                              : "bg-slate-50 text-slate-900 border-slate-200"
                          }`}
                        >
                          {isRefund ? "-" : "+"} PKR{" "}
                          {parseFloat(p.amount || "0").toFixed(2)}
                        </span>
                        <div
                          className={`text-[11px] font-medium mt-1 ${
                            isRefund ? "text-red-600" : "text-teal-700"
                          }`}
                        >
                          {isRefund ? "● Refunded" : "● Settled"}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="py-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                  No payments have been recorded for this invoice yet.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: RECORD PAYMENT & REFUND & DANGER (5 COLS) */}
        <div className="col-span-12 lg:col-span-5 space-y-6">
          {/* Card 1: Record payment */}
          {invoice.status !== "cancelled" && balanceDue > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="pb-3 border-b border-slate-100 mb-4">
                <h2 className="text-base font-semibold text-slate-900">
                  Record payment
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Apply cash, card, or digital payment towards balance
                </p>
              </div>

              <form onSubmit={handleRecordPayment} className="space-y-4">
                <div>
                  <label
                    htmlFor={payAmountId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Amount (PKR) <span className="text-red-600">*</span>
                  </label>
                  <input
                    id={payAmountId}
                    type="number"
                    step="0.01"
                    min="0.01"
                    max={balanceDue}
                    value={payAmount}
                    onChange={(e) => setPayAmount(e.target.value)}
                    required
                    className="font-mono text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  />
                  <span className="block text-xs text-slate-500 mt-1">
                    Maximum balance payable: PKR {balanceDue.toFixed(2)}
                  </span>
                </div>

                <div>
                  <label
                    htmlFor={payMethodId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Payment Method <span className="text-red-600">*</span>
                  </label>
                  <select
                    id={payMethodId}
                    value={payMethod}
                    onChange={(e) =>
                      setPayMethod(e.target.value as PaymentMethod)
                    }
                    className="border border-slate-300 rounded-lg px-3 py-2 w-full text-sm bg-white text-slate-900 focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  >
                    <option value="cash">Cash</option>
                    <option value="card">Credit / Debit Card</option>
                    <option value="bank_transfer">Bank Transfer</option>
                    <option value="easypaisa">Easypaisa</option>
                    <option value="jazzcash">JazzCash</option>
                    <option value="other">Other</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor={payRefId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Reference / Transaction Note{" "}
                    {payMethod !== "cash" && (
                      <span className="text-red-600">*</span>
                    )}
                  </label>
                  <input
                    id={payRefId}
                    type="text"
                    value={payReference}
                    onChange={(e) => setPayReference(e.target.value)}
                    placeholder="e.g. TRX-98214 or Approval Code"
                    className="text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none placeholder:text-slate-400"
                  />
                  <span className="block text-xs text-slate-500 mt-1">
                    Required for non-cash settlement records
                  </span>
                </div>

                <button
                  type="submit"
                  disabled={submittingPayment}
                  className="bg-teal-700 hover:bg-teal-800 text-white font-medium text-sm py-2.5 px-4 rounded-lg w-full flex items-center justify-center gap-2 shadow-sm transition-colors cursor-pointer disabled:opacity-50"
                >
                  {submittingPayment ? (
                    <span>Recording payment...</span>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-[18px]">
                        add_card
                      </span>
                      <span>Record payment</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Card 2: Record refund */}
          {invoice.status !== "cancelled" && netPaidNum > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="pb-3 border-b border-slate-100 mb-4">
                <h2 className="text-base font-semibold text-slate-900">
                  Record refund
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Reverse settled funds to patient
                </p>
              </div>

              <form onSubmit={handleRecordRefund} className="space-y-4">
                <div>
                  <label
                    htmlFor={refundAmountId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Refund Amount (PKR) <span className="text-red-600">*</span>
                  </label>
                  <input
                    id={refundAmountId}
                    type="number"
                    step="0.01"
                    min="0.01"
                    max={netPaidNum}
                    value={refundAmount}
                    onChange={(e) => setRefundAmount(e.target.value)}
                    placeholder="0.00"
                    required
                    className="font-mono text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  />
                  <span className="block text-xs text-slate-500 mt-1">
                    Cannot exceed settled funds: PKR {netPaidNum.toFixed(2)}
                  </span>
                </div>

                <div>
                  <label
                    htmlFor={refundMethodId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Refund Method <span className="text-red-600">*</span>
                  </label>
                  <select
                    id={refundMethodId}
                    value={refundMethod}
                    onChange={(e) =>
                      setRefundMethod(e.target.value as PaymentMethod)
                    }
                    className="border border-slate-300 rounded-lg px-3 py-2 w-full text-sm bg-white text-slate-900 focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  >
                    <option value="cash">Cash Reversal</option>
                    <option value="bank_transfer">Bank Reversal</option>
                    <option value="easypaisa">Easypaisa</option>
                    <option value="jazzcash">JazzCash</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor={refundReasonId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Reason note <span className="text-red-600">*</span>
                  </label>
                  <input
                    id={refundReasonId}
                    type="text"
                    value={refundReason}
                    onChange={(e) => setRefundReason(e.target.value)}
                    placeholder="Clinical or billing justification (e.g. test cancelled)"
                    required
                    className="text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none placeholder:text-slate-400"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submittingRefund}
                  className="border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium text-sm py-2 px-4 rounded-lg w-full flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {submittingRefund ? (
                    <span>Recording refund...</span>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-[18px]">
                        currency_exchange
                      </span>
                      <span>Record refund</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Card 3: Danger Zone / Cancel invoice */}
          <div className="bg-red-50/20 rounded-xl border border-red-200 p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-red-700">
                Cancel invoice
              </span>
              <span className="text-xs font-medium text-slate-500">
                (unpaid invoices only)
              </span>
            </div>
            <p className="text-xs text-slate-600 mb-3 leading-relaxed">
              Cancellation is strictly restricted to invoices with zero settled
              payments. To cancel this invoice, all payments must first be fully
              refunded.
            </p>
            <button
              type="button"
              onClick={() => setShowCancelModal(true)}
              disabled={!canCancel}
              className={`border text-sm font-medium py-2 px-4 rounded-lg w-full flex items-center justify-center gap-2 transition-colors ${
                canCancel
                  ? "border-red-300 text-red-700 bg-white hover:bg-red-50 cursor-pointer"
                  : "border-red-200 text-red-400 bg-white cursor-not-allowed opacity-60"
              }`}
            >
              <span className="material-symbols-outlined text-[18px]">
                block
              </span>
              <span>Cancel invoice</span>
            </button>
          </div>
        </div>
      </div>

      {/* Cancel Modal Dialog */}
      {showCancelModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="cancel-dialog-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        >
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200">
            <h3
              id="cancel-dialog-title"
              className="text-lg font-bold text-slate-900 mb-2"
            >
              Cancel Invoice?
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              This action cannot be undone. Please provide a mandatory
              cancellation reason for the audit log.
            </p>
            <div className="mb-4">
              <label
                htmlFor={cancelReasonId}
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                Cancellation Reason <span className="text-red-600">*</span>
              </label>
              <textarea
                id={cancelReasonId}
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Patient did not arrive, test ordered in error..."
                className="w-full text-sm border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-red-600 focus:outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                disabled={submittingCancel}
                className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Keep Invoice
              </button>
              <button
                type="button"
                onClick={handleConfirmCancel}
                disabled={submittingCancel || !cancelReason.trim()}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50 flex items-center gap-1.5"
              >
                {submittingCancel ? "Cancelling..." : "Confirm Cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
