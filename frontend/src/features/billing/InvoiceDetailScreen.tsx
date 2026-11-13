import { useCallback, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  AlertCircle,
  Printer,
  FlaskConical,
  CreditCard,
  RotateCcw,
  Ban,
} from "lucide-react";
import { billingService } from "./billingService";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { InvoiceDetail, InvoiceStatus, PaymentMethod } from "./types";

export interface InvoiceDetailScreenProps {
  invoiceId: string;
  onBack?: () => void;
  onProceedToSamples?: (invoice: InvoiceDetail) => void;
}

function getStatusBadge(
  status: InvoiceStatus,
  t: (key: string) => string,
): JSX.Element {
  switch (status) {
    case "paid":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
          {statusLabel("invoice", "paid", t)}
        </span>
      );
    case "partial":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-600" />
          {statusLabel("invoice", "partial", t)}
        </span>
      );
    case "unpaid":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
          {statusLabel("invoice", "unpaid", t)}
        </span>
      );
    case "refunded":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-600" />
          {statusLabel("invoice", "refunded", t)}
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
          {statusLabel("invoice", "cancelled", t)}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
          {t("common:labels.unknown")}
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
  const { t, i18n } = useTranslation(["billing", "common"]);
  const lang: "en" | "ur" = i18n.resolvedLanguage === "ur" ? "ur" : "en";
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
      setErrorMessage(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [invoiceId, t]);

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
      setErrorMessage(t("billing:detail.error_invalid_payment"));
      return;
    }

    if (payMethod !== "cash" && !payReference.trim()) {
      setErrorMessage(t("billing:detail.error_reference_required"));
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
      showToast(
        t("billing:detail.toast_payment", {
          amount: formatMoney(amt.toFixed(2), lang),
        }),
      );
      setPayReference("");
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
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
      setErrorMessage(t("billing:detail.error_invalid_refund"));
      return;
    }

    const netPaidNum = parseFloat(invoice.net_paid || "0") || 0;
    if (amt > netPaidNum) {
      setErrorMessage(
        t("billing:detail.error_refund_exceeds", {
          amount: formatMoney(netPaidNum.toFixed(2), lang),
        }),
      );
      return;
    }

    if (!refundReason.trim()) {
      setErrorMessage(t("billing:detail.error_refund_reason"));
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
      showToast(
        t("billing:detail.toast_refund", {
          amount: formatMoney(amt.toFixed(2), lang),
        }),
      );
      setRefundAmount("");
      setRefundReason("");
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setSubmittingRefund(false);
    }
  };

  const handleConfirmCancel = async () => {
    if (!invoice) return;
    if (!cancelReason.trim()) {
      setErrorMessage(t("billing:detail.error_cancel_reason"));
      return;
    }

    try {
      setSubmittingCancel(true);
      await billingService.cancelInvoice(invoice.id, cancelReason.trim());
      showToast(t("billing:detail.toast_cancelled"));
      setShowCancelModal(false);
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
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
          <span>{t("billing:detail.loading")}</span>
        </div>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-800 font-semibold mb-2">
            {t("billing:detail.not_found_title")}
          </p>
          <p className="text-xs text-red-600 mb-4">
            {errorMessage || t("billing:detail.not_found_body")}
          </p>
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="px-4 py-2 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              {t("billing:detail.back_to_invoices")}
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
          className="fixed bottom-6 end-6 z-50 bg-slate-900 text-white text-xs px-4 py-3 rounded-lg shadow-lg flex items-center gap-2"
        >
          <CheckCircle2 className="w-4 h-4 text-teal-400" />
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
            {t("billing:shared.invoices")}
          </button>
          <span>/</span>
          <span className="font-mono text-slate-900 font-medium" dir="ltr">
            {invoice.invoice_number || invoice.id}
          </span>
        </div>
        <div className="text-xs font-mono text-slate-500">
          <bdi dir="ltr">{formatPkt(invoice.created_at)}</bdi>
        </div>
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div
          role="alert"
          className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start gap-3"
        >
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{errorMessage}</div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-red-500 hover:text-red-700 font-bold"
            aria-label={t("billing:shared.dismiss_error_aria")}
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
              <h1
                className="text-2xl font-bold font-mono text-slate-900 tracking-tight"
                dir="ltr"
              >
                {invoice.invoice_number || invoice.id}
              </h1>
              {getStatusBadge(invoice.status, t)}
              <span className="text-xs bg-slate-100 text-slate-600 px-2.5 py-0.5 rounded font-medium border border-slate-200">
                {t("billing:detail.type_badge")}
              </span>
            </div>
            <div className="text-sm text-slate-600 flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="font-medium text-slate-900">
                <bdi dir="ltr">{invoice.patient_name || "—"}</bdi>
              </span>
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="font-mono text-slate-500">
                <bdi dir="ltr">
                  {t("billing:detail.mrn_value", {
                    mrn: invoice.patient_mrn || "—",
                  })}
                </bdi>
              </span>
              {invoice.patient_phone && (
                <>
                  <span className="text-slate-300 hidden sm:inline">|</span>
                  <span className="font-mono text-slate-500">
                    <bdi dir="ltr">{invoice.patient_phone}</bdi>
                  </span>
                </>
              )}
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="text-slate-600 font-medium">
                <bdi dir="ltr">{invoice.branch_name || "—"}</bdi>
              </span>
              <span className="text-slate-300 hidden sm:inline">|</span>
              <span className="font-mono text-slate-500">
                <bdi dir="ltr">{formatPkt(invoice.created_at)}</bdi>
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 self-start shrink-0">
            <button
              type="button"
              onClick={handlePrintReceipt}
              className="inline-flex items-center gap-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-800 text-xs font-semibold px-3 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>{t("billing:detail.print_receipt")}</span>
            </button>
            {onProceedToSamples && (
              <button
                type="button"
                onClick={() => onProceedToSamples(invoice)}
                className="inline-flex items-center gap-1.5 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold px-3.5 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
              >
                <FlaskConical className="w-3.5 h-3.5" />
                <span>{t("billing:detail.collect_samples")}</span>
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
                {t("billing:detail.lines_title")}
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {invoice.items?.length || 0}{" "}
                {invoice.items?.length === 1
                  ? t("billing:detail.items_included_one")
                  : t("billing:detail.items_included_other")}
              </span>
            </div>

            {/* Table Header */}
            <div className="grid grid-cols-12 text-xs uppercase font-medium text-slate-400 py-2.5 border-b border-slate-100 mt-2">
              <div className="col-span-7">{t("billing:detail.col_item")}</div>
              <div className="col-span-2 text-center">
                {t("billing:detail.col_qty")}
              </div>
              <div className="col-span-3 text-end">
                {t("billing:detail.col_line_total")}
              </div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-slate-100">
              {invoice.items && invoice.items.length > 0 ? (
                invoice.items.map((it) => (
                  <div
                    key={it.id}
                    className="grid grid-cols-12 py-3 items-center"
                  >
                    <div className="col-span-7 pe-2">
                      <div className="font-medium text-slate-900 text-sm">
                        <bdi dir="ltr">{it.description}</bdi>
                      </div>
                    </div>
                    <div className="col-span-2 text-center text-xs font-mono text-slate-600">
                      {it.quantity}
                    </div>
                    <div className="col-span-3 text-end font-mono text-xs font-medium text-slate-900">
                      {formatMoney(
                        parseFloat(
                          it.line_total || it.unit_price || "0",
                        ).toFixed(2),
                        lang,
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="py-4 text-center text-xs text-slate-400">
                  {t("billing:detail.no_items")}
                </div>
              )}
            </div>

            {/* Calculation Stack */}
            <div className="pt-4 mt-2 border-t border-slate-100 space-y-2.5">
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-600">
                  {t("billing:detail.gross_subtotal")}
                </span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                  {formatMoney(subtotalNum.toFixed(2), lang)}
                </span>
              </div>
              {discountNum > 0 && (
                <div className="flex justify-between items-center text-sm bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  <div>
                    <div className="font-medium text-slate-900 text-xs">
                      {t("billing:detail.discount_applied")}
                    </div>
                    {invoice.discount_reason && (
                      <div className="text-[11px] text-slate-500">
                        {t("billing:detail.discount_reason", {
                          reason: invoice.discount_reason,
                        })}
                      </div>
                    )}
                  </div>
                  <span className="bg-slate-100 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                    - {formatMoney(discountNum.toFixed(2), lang)}
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center text-sm pt-1">
                <span className="text-slate-700 font-semibold">
                  {t("billing:detail.net_payable")}
                </span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-bold">
                  {formatMoney(totalNum.toFixed(2), lang)}
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-600">
                  {t("billing:detail.total_settled")}
                </span>
                <span className="bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono text-slate-900 font-medium">
                  {formatMoney(netPaidNum.toFixed(2), lang)}
                </span>
              </div>
              <div className="border-t border-slate-200 my-2" />

              {/* Balance Due Callout */}
              <div className="flex justify-between items-center pt-1">
                <div>
                  <div className="text-base font-bold text-slate-900">
                    {t("billing:detail.balance_due")}
                  </div>
                  <div className="text-xs text-amber-600 font-medium">
                    {balanceDue > 0
                      ? t("billing:detail.outstanding")
                      : t("billing:detail.fully_settled")}
                  </div>
                </div>
                <div className="text-end">
                  <div
                    className={`text-xl font-bold font-mono px-4 py-2 rounded-lg inline-block border ${
                      balanceDue > 0
                        ? "bg-amber-50 text-amber-900 border-amber-200"
                        : "bg-emerald-50 text-emerald-900 border-emerald-200"
                    }`}
                  >
                    {formatMoney(balanceDue.toFixed(2), lang)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Payments Ledger Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                {t("billing:detail.ledger_title")}
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {invoice.payments?.length || 0}{" "}
                {invoice.payments?.length === 1
                  ? t("billing:detail.entries_recorded_one")
                  : t("billing:detail.entries_recorded_other")}
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
                            <bdi dir="ltr">{formatPkt(p.created_at)}</bdi>
                          </span>
                          <span className="text-slate-400">·</span>
                          <span
                            className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded capitalize ${
                              isRefund
                                ? "bg-red-100 text-red-800"
                                : "bg-slate-100 text-slate-800"
                            }`}
                          >
                            {t(`billing:detail.kind.${p.kind}`)}:{" "}
                            {t(`billing:detail.method.${p.method}`)}
                          </span>
                        </div>
                        {p.reference && (
                          <div className="text-xs text-slate-500 mt-1">
                            {t("billing:detail.reference_label")}{" "}
                            <span className="font-mono">
                              <bdi dir="ltr">{p.reference}</bdi>
                            </span>
                          </div>
                        )}
                        {p.received_by && (
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            {t("billing:detail.cashier_label")}{" "}
                            <bdi dir="ltr">{p.received_by}</bdi>
                          </div>
                        )}
                      </div>
                      <div className="text-end shrink-0">
                        <span
                          className={`font-mono font-bold text-sm px-2.5 py-1 rounded inline-block border ${
                            isRefund
                              ? "bg-red-50 text-red-700 border-red-200"
                              : "bg-slate-50 text-slate-900 border-slate-200"
                          }`}
                        >
                          {isRefund ? "-" : "+"}{" "}
                          {formatMoney(
                            parseFloat(p.amount || "0").toFixed(2),
                            lang,
                          )}
                        </span>
                        <div
                          className={`text-[11px] font-medium mt-1 ${
                            isRefund ? "text-red-600" : "text-teal-700"
                          }`}
                        >
                          {isRefund
                            ? `● ${t("billing:detail.entry_refunded")}`
                            : `● ${t("billing:detail.entry_settled")}`}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="py-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                  {t("billing:detail.no_payments")}
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
                  {t("billing:detail.record_payment_title")}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("billing:detail.record_payment_hint")}
                </p>
              </div>

              <form onSubmit={handleRecordPayment} className="space-y-4">
                <div>
                  <label
                    htmlFor={payAmountId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.amount_label")}{" "}
                    <span className="text-red-600">*</span>
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
                    {t("billing:detail.max_payable", {
                      amount: formatMoney(balanceDue.toFixed(2), lang),
                    })}
                  </span>
                </div>

                <div>
                  <label
                    htmlFor={payMethodId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.payment_method_label")}{" "}
                    <span className="text-red-600">*</span>
                  </label>
                  <select
                    id={payMethodId}
                    value={payMethod}
                    onChange={(e) =>
                      setPayMethod(e.target.value as PaymentMethod)
                    }
                    className="border border-slate-300 rounded-lg px-3 py-2 w-full text-sm bg-white text-slate-900 focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  >
                    <option value="cash">
                      {t("billing:detail.method.cash")}
                    </option>
                    <option value="card">
                      {t("billing:detail.method.card")}
                    </option>
                    <option value="bank_transfer">
                      {t("billing:detail.method.bank_transfer")}
                    </option>
                    <option value="easypaisa">
                      {t("billing:detail.method.easypaisa")}
                    </option>
                    <option value="jazzcash">
                      {t("billing:detail.method.jazzcash")}
                    </option>
                    <option value="other">
                      {t("billing:detail.method.other")}
                    </option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor={payRefId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.reference_field_label")}{" "}
                    {payMethod !== "cash" && (
                      <span className="text-red-600">*</span>
                    )}
                  </label>
                  <input
                    id={payRefId}
                    type="text"
                    value={payReference}
                    onChange={(e) => setPayReference(e.target.value)}
                    placeholder={t("billing:detail.reference_placeholder")}
                    className="text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none placeholder:text-slate-400"
                  />
                  <span className="block text-xs text-slate-500 mt-1">
                    {t("billing:detail.reference_help")}
                  </span>
                </div>

                <button
                  type="submit"
                  disabled={submittingPayment}
                  className="bg-teal-700 hover:bg-teal-800 text-white font-medium text-sm py-2.5 px-4 rounded-lg w-full flex items-center justify-center gap-2 shadow-sm transition-colors cursor-pointer disabled:opacity-50"
                >
                  {submittingPayment ? (
                    <span>{t("billing:detail.recording_payment")}</span>
                  ) : (
                    <>
                      <CreditCard className="w-4 h-4" />
                      <span>{t("billing:detail.record_payment_title")}</span>
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
                  {t("billing:detail.record_refund_title")}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("billing:detail.record_refund_hint")}
                </p>
              </div>

              <form onSubmit={handleRecordRefund} className="space-y-4">
                <div>
                  <label
                    htmlFor={refundAmountId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.refund_amount_label")}{" "}
                    <span className="text-red-600">*</span>
                  </label>
                  <input
                    id={refundAmountId}
                    type="number"
                    step="0.01"
                    min="0.01"
                    max={netPaidNum}
                    value={refundAmount}
                    onChange={(e) => setRefundAmount(e.target.value)}
                    placeholder={t("billing:new.amount_placeholder")}
                    required
                    className="font-mono text-sm border border-slate-300 rounded-lg px-3 py-2 w-full focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  />
                  <span className="block text-xs text-slate-500 mt-1">
                    {t("billing:detail.refund_max", {
                      amount: formatMoney(netPaidNum.toFixed(2), lang),
                    })}
                  </span>
                </div>

                <div>
                  <label
                    htmlFor={refundMethodId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.refund_method_label")}{" "}
                    <span className="text-red-600">*</span>
                  </label>
                  <select
                    id={refundMethodId}
                    value={refundMethod}
                    onChange={(e) =>
                      setRefundMethod(e.target.value as PaymentMethod)
                    }
                    className="border border-slate-300 rounded-lg px-3 py-2 w-full text-sm bg-white text-slate-900 focus:ring-2 focus:ring-teal-600 focus:outline-none"
                  >
                    <option value="cash">
                      {t("billing:detail.refund_method.cash")}
                    </option>
                    <option value="bank_transfer">
                      {t("billing:detail.refund_method.bank_transfer")}
                    </option>
                    <option value="easypaisa">
                      {t("billing:detail.refund_method.easypaisa")}
                    </option>
                    <option value="jazzcash">
                      {t("billing:detail.refund_method.jazzcash")}
                    </option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor={refundReasonId}
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    {t("billing:detail.reason_note_label")}{" "}
                    <span className="text-red-600">*</span>
                  </label>
                  <input
                    id={refundReasonId}
                    type="text"
                    value={refundReason}
                    onChange={(e) => setRefundReason(e.target.value)}
                    placeholder={t("billing:detail.reason_placeholder")}
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
                    <span>{t("billing:detail.recording_refund")}</span>
                  ) : (
                    <>
                      <RotateCcw className="w-4 h-4" />
                      <span>{t("billing:detail.record_refund_title")}</span>
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
                {t("billing:detail.cancel_title")}
              </span>
              <span className="text-xs font-medium text-slate-500">
                {t("billing:detail.cancel_hint")}
              </span>
            </div>
            <p className="text-xs text-slate-600 mb-3 leading-relaxed">
              {t("billing:detail.cancel_description")}
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
              <Ban className="w-4 h-4" />
              <span>{t("billing:detail.cancel_title")}</span>
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
              {t("billing:detail.cancel_modal_title")}
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              {t("billing:detail.cancel_modal_body")}
            </p>
            <div className="mb-4">
              <label
                htmlFor={cancelReasonId}
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                {t("billing:detail.cancel_reason_label")}{" "}
                <span className="text-red-600">*</span>
              </label>
              <textarea
                id={cancelReasonId}
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder={t("billing:detail.cancel_reason_placeholder")}
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
                {t("billing:detail.keep_invoice")}
              </button>
              <button
                type="button"
                onClick={handleConfirmCancel}
                disabled={submittingCancel || !cancelReason.trim()}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50 flex items-center gap-1.5"
              >
                {submittingCancel
                  ? t("billing:detail.cancelling")
                  : t("billing:detail.confirm_cancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
