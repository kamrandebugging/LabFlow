import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  AlertCircle,
  Printer,
  FlaskConical,
  CreditCard,
  RotateCcw,
  Ban,
  Clock,
} from "lucide-react";
import { billingService } from "./billingService";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import { useDialogFocus } from "../../lib/dialogFocus";
import styles from "./InvoiceDetailScreen.module.css";
import type { InvoiceDetail, InvoiceStatus, PaymentMethod } from "./types";
import { PaymentSuccessModal } from "./components";

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
        <span className={`${styles.statusBadge} ${styles.statusPaid}`}>
          <CheckCircle2 className={styles.statusIconWrap} aria-hidden="true" />
          {statusLabel("invoice", "paid", (key) => t(`common:${key}`))}
        </span>
      );
    case "partial":
      return (
        <span className={`${styles.statusBadge} ${styles.statusPartial}`}>
          <Clock className={styles.statusIconWrap} aria-hidden="true" />
          {statusLabel("invoice", "partial", (key) => t(`common:${key}`))}
        </span>
      );
    case "unpaid":
      return (
        <span className={`${styles.statusBadge} ${styles.statusUnpaid}`}>
          <AlertCircle className={styles.statusIconWrap} aria-hidden="true" />
          {statusLabel("invoice", "unpaid", (key) => t(`common:${key}`))}
        </span>
      );
    case "refunded":
      return (
        <span className={`${styles.statusBadge} ${styles.statusRefunded}`}>
          <RotateCcw className={styles.statusIconWrap} aria-hidden="true" />
          {statusLabel("invoice", "refunded", (key) => t(`common:${key}`))}
        </span>
      );
    case "cancelled":
      return (
        <span className={`${styles.statusBadge} ${styles.statusCancelled}`}>
          <Ban className={styles.statusIconWrap} aria-hidden="true" />
          {statusLabel("invoice", "cancelled", (key) => t(`common:${key}`))}
        </span>
      );
    default:
      return (
        <span className={`${styles.statusBadge} ${styles.statusUnknown}`}>
          <AlertCircle className={styles.statusIconWrap} aria-hidden="true" />
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
  const refundReferenceId = useId();
  const cancelReasonId = useId();
  const lineCancelReasonId = useId();

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Payment Form State
  const [payAmount, setPayAmount] = useState<string>("");
  const [payMethod, setPayMethod] = useState<PaymentMethod>("cash");
  const [payReference, setPayReference] = useState<string>("");
  const [submittingPayment, setSubmittingPayment] = useState(false);
  const [lastPayment, setLastPayment] = useState<{
    amount: string;
    method: string;
    reference?: string | null;
  } | null>(null);

  // Refund Form State
  const [refundAmount, setRefundAmount] = useState<string>("");
  const [refundMethod, setRefundMethod] = useState<PaymentMethod>("cash");
  const [refundReason, setRefundReason] = useState<string>("");
  const [refundReference, setRefundReference] = useState<string>("");
  const [submittingRefund, setSubmittingRefund] = useState(false);
  const [showRefundForm, setShowRefundForm] = useState(false);
  const [showRefundModal, setShowRefundModal] = useState(false);

  // Cancel Modal State
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [submittingCancel, setSubmittingCancel] = useState(false);

  // Line-cancel Modal State (unperformed test, Owner/Manager)
  const [lineCancelItemId, setLineCancelItemId] = useState<string | null>(null);
  const [lineCancelReason, setLineCancelReason] = useState<string>("");
  const [submittingLineCancel, setSubmittingLineCancel] = useState(false);

  const cancelTriggerRef = useRef<HTMLButtonElement>(null);
  const refundTriggerRef = useRef<HTMLButtonElement>(null);
  const cancelPanelRef = useDialogFocus<HTMLDivElement>(
    showCancelModal,
    () => setShowCancelModal(false),
    cancelTriggerRef,
  );
  const refundPanelRef = useDialogFocus<HTMLDivElement>(
    showRefundModal,
    () => setShowRefundModal(false),
    refundTriggerRef,
  );

  const fetchInvoice = useCallback(async () => {
    try {
      setLoading(true);
      const data = await billingService.getInvoice(invoiceId);
      setInvoice(data);
      // Amount is left empty on load: the "Pay full balance" chip fills it in
      // one deliberate tap instead of silently pre-populating the field.
      setPayAmount("");
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
      const paidAmt = amt.toFixed(2);
      const paidRef = payReference.trim() || undefined;
      const paidMeth = payMethod;
      await billingService.recordPayment(invoice.id, {
        kind: "payment",
        method: paidMeth,
        amount: paidAmt,
        reference: paidRef,
      });
      setLastPayment({
        amount: paidAmt,
        method: paidMeth,
        reference: paidRef,
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

  const handleRecordRefund = (e: React.FormEvent) => {
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

    if (refundMethod !== "cash" && !refundReference.trim()) {
      setErrorMessage(t("billing:detail.error_reference_required"));
      return;
    }

    // Validation passed — review the restated values before the call fires.
    setShowRefundModal(true);
  };

  const handleConfirmRefund = async () => {
    if (!invoice) return;
    const amt = parseFloat(refundAmount);
    if (isNaN(amt) || amt <= 0) return;

    try {
      setSubmittingRefund(true);
      await billingService.recordPayment(invoice.id, {
        kind: "refund",
        method: refundMethod,
        amount: amt.toFixed(2),
        refund_reason: refundReason.trim(),
        reference: refundMethod === "cash" ? null : refundReference.trim(),
      });
      showToast(
        t("billing:detail.toast_refund", {
          amount: formatMoney(amt.toFixed(2), lang),
        }),
      );
      setRefundAmount("");
      setRefundReason("");
      setRefundReference("");
      setShowRefundModal(false);
      await fetchInvoice();
    } catch (err) {
      setShowRefundModal(false);
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

  const handleConfirmLineCancel = async () => {
    if (!invoice || !lineCancelItemId) return;
    if (!lineCancelReason.trim()) {
      setErrorMessage(t("billing:detail.error_line_cancel_reason"));
      return;
    }

    try {
      setSubmittingLineCancel(true);
      await billingService.cancelInvoiceLine(
        invoice.id,
        lineCancelItemId,
        lineCancelReason.trim(),
      );
      showToast(t("billing:detail.toast_line_cancelled"));
      setLineCancelItemId(null);
      setLineCancelReason("");
      await fetchInvoice();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setSubmittingLineCancel(false);
    }
  };

  const handlePrintReceipt = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} aria-hidden="true" />
        <span>{t("billing:detail.loading")}</span>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <div className={styles.notFound}>
            <p className={styles.notFoundTitle}>
              {t("billing:detail.not_found_title")}
            </p>
            <p className={styles.notFoundText}>
              {errorMessage || t("billing:detail.not_found_body")}
            </p>
            {onBack && (
              <button
                type="button"
                onClick={onBack}
                className={styles.secondaryButton}
              >
                {t("billing:detail.back_to_invoices")}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const subtotalNum = parseFloat(invoice.subtotal || "0") || 0;
  const discountNum = parseFloat(invoice.discount_amount || "0") || 0;
  const totalNum = parseFloat(invoice.total || "0") || 0;
  const netPaidNum = parseFloat(invoice.net_paid || "0") || 0;
  const hasActiveCreditNote = Boolean(
    invoice.credit_notes && invoice.credit_notes.some((cn) => !cn.voided_at),
  );
  const balanceDue =
    invoice.balance !== undefined && invoice.balance !== null
      ? parseFloat(invoice.balance)
      : invoice.status === "cancelled" || hasActiveCreditNote
        ? 0
        : Math.max(
            0,
            totalNum -
              (parseFloat(invoice.net_revenue ?? invoice.net_paid ?? "0") || 0),
          );
  const hasVoidedCreditNote = Boolean(
    invoice.credit_notes && invoice.credit_notes.some((cn) => cn.voided_at),
  );
  const netRevenueNum =
    parseFloat(invoice.net_revenue ?? invoice.net_paid ?? "0") || 0;
  // Phase 6: unpaid, zero-total, and terminal (post-void full refund) closures.
  const canCancel =
    (invoice.status === "unpaid" && netPaidNum === 0) ||
    (invoice.status === "paid" && totalNum === 0 && netPaidNum === 0) ||
    (invoice.status === "refunded" &&
      netRevenueNum === 0 &&
      hasVoidedCreditNote);
  const canCancelLines =
    invoice.status !== "cancelled" && invoice.status !== "refunded";

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Toast Notification */}
        {toastMessage && (
          <div role="status" className={styles.toast}>
            <CheckCircle2 className={styles.toastIcon} aria-hidden="true" />
            <span>{toastMessage}</span>
          </div>
        )}

        {/* Top Breadcrumb & Timestamp */}
        <div className={styles.breadcrumbRow}>
          <div className={styles.breadcrumb}>
            <button type="button" onClick={onBack} className={styles.crumbBtn}>
              {t("billing:shared.invoices")}
            </button>
            <span className={styles.crumbSep}>/</span>
            <span className={styles.crumbId} dir="ltr">
              {invoice.invoice_number || invoice.id}
            </span>
          </div>
          <div className={styles.timestamp}>
            <bdi dir="ltr">{formatPkt(invoice.created_at)}</bdi>
          </div>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div role="alert" className={styles.alert}>
            <AlertCircle className={styles.alertIcon} aria-hidden="true" />
            <div className={styles.alertText}>{errorMessage}</div>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              className={styles.alertDismiss}
              aria-label={t("billing:shared.dismiss_error_aria")}
            >
              ×
            </button>
          </div>
        )}

        {/* INVOICE HEADER CARD */}
        <div className={styles.headerCard}>
          <div className={styles.headerTop}>
            <div>
              <div className={styles.titleRow}>
                <h1 className={styles.invoiceTitle} dir="ltr">
                  {invoice.invoice_number || invoice.id}
                </h1>
                {getStatusBadge(invoice.status, t)}
                <span className={styles.typeBadge}>
                  {t("billing:detail.type_badge")}
                </span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaStrong}>
                  <bdi dir="ltr">{invoice.patient_name || "—"}</bdi>
                </span>
                <span className={styles.metaSep}>|</span>
                <span className={styles.metaMono}>
                  <bdi dir="ltr">
                    {t("billing:detail.mrn_value", {
                      mrn: invoice.patient_mrn || "—",
                    })}
                  </bdi>
                </span>
                {invoice.patient_phone && (
                  <>
                    <span className={styles.metaSep}>|</span>
                    <span className={styles.metaMono}>
                      <bdi dir="ltr">{invoice.patient_phone}</bdi>
                    </span>
                  </>
                )}
                <span className={styles.metaSep}>|</span>
                <span className={styles.metaStrong}>
                  <bdi dir="ltr">{invoice.branch_name || "—"}</bdi>
                </span>
                <span className={styles.metaSep}>|</span>
                <span className={styles.metaMono}>
                  <bdi dir="ltr">{formatPkt(invoice.created_at)}</bdi>
                </span>
              </div>
            </div>
            <div className={styles.headerActions}>
              <button
                type="button"
                onClick={handlePrintReceipt}
                className={styles.secondaryButton}
              >
                <Printer className={styles.buttonIcon} aria-hidden="true" />
                <span>{t("billing:detail.print_receipt")}</span>
              </button>
              {onProceedToSamples && (
                <button
                  type="button"
                  onClick={() => onProceedToSamples(invoice)}
                  className={styles.primaryButton}
                >
                  <FlaskConical
                    className={styles.buttonIcon}
                    aria-hidden="true"
                  />
                  <span>{t("billing:detail.collect_samples")}</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* MAIN GRID */}
        <div className={styles.layout}>
          {/* LEFT COLUMN: LINES & PAYMENT LEDGER */}
          <div className={styles.leftCol}>
            {/* Lines & Pricing Card */}
            <div className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:detail.lines_title")}
                </h2>
                <span className={styles.countText}>
                  {invoice.items?.length || 0}{" "}
                  {invoice.items?.length === 1
                    ? t("billing:detail.items_included_one")
                    : t("billing:detail.items_included_other")}
                </span>
              </div>

              {/* Table Header */}
              <div className={styles.tableHead}>
                <div>{t("billing:detail.col_item")}</div>
                <div className={styles.alignCenter}>
                  {t("billing:detail.col_qty")}
                </div>
                <div className={styles.alignEnd}>
                  {t("billing:detail.col_line_total")}
                </div>
              </div>

              {/* Rows */}
              <div className={styles.tableRows}>
                {invoice.items && invoice.items.length > 0 ? (
                  invoice.items.map((it) => (
                    <div key={it.id} className={styles.tableRow}>
                      <div className={styles.itemName}>
                        <bdi dir="ltr">{it.description}</bdi>
                        {it.is_cancelled ? (
                          <span className={styles.lineCancelled}>
                            {t("billing:detail.line_cancelled_badge")}
                          </span>
                        ) : canCancelLines ? (
                          <button
                            type="button"
                            onClick={() => {
                              setLineCancelItemId(it.id);
                              setLineCancelReason("");
                            }}
                            className={styles.lineCancelBtn}
                          >
                            {t("billing:detail.line_cancel_action")}
                          </button>
                        ) : null}
                      </div>
                      <div className={styles.qty}>{it.quantity}</div>
                      <div
                        className={
                          it.is_cancelled
                            ? `${styles.lineTotal} ${styles.lineTotalCancelled}`
                            : styles.lineTotal
                        }
                        dir="ltr"
                      >
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
                  <div className={styles.noItems}>
                    {t("billing:detail.no_items")}
                  </div>
                )}
              </div>

              {/* Calculation Stack */}
              <div className={styles.calc}>
                <div className={styles.calcRow}>
                  <span className={styles.calcLabel}>
                    {t("billing:detail.gross_subtotal")}
                  </span>
                  <span className={styles.chip} dir="ltr">
                    {formatMoney(subtotalNum.toFixed(2), lang)}
                  </span>
                </div>
                {discountNum > 0 && (
                  <div className={styles.discountBox}>
                    <div>
                      <div className={styles.discountTitle}>
                        {t("billing:detail.discount_applied")}
                      </div>
                      {invoice.discount_reason && (
                        <div className={styles.discountReason}>
                          {t("billing:detail.discount_reason", {
                            reason: invoice.discount_reason,
                          })}
                        </div>
                      )}
                    </div>
                    <span className={styles.chip} dir="ltr">
                      - {formatMoney(discountNum.toFixed(2), lang)}
                    </span>
                  </div>
                )}
                <div className={styles.calcRow}>
                  <span className={styles.calcLabelStrong}>
                    {t("billing:detail.net_payable")}
                  </span>
                  <span
                    className={`${styles.chip} ${styles.chipStrong}`}
                    dir="ltr"
                  >
                    {formatMoney(totalNum.toFixed(2), lang)}
                  </span>
                </div>
                <div className={styles.calcRow}>
                  <span className={styles.calcLabel}>
                    {t("billing:detail.total_settled")}
                  </span>
                  <span className={styles.chip} dir="ltr">
                    {formatMoney(netPaidNum.toFixed(2), lang)}
                  </span>
                </div>

                {/* Balance Due Callout */}
                <div className={styles.balanceRow}>
                  <div>
                    <div className={styles.balanceLabel}>
                      {t("billing:detail.balance_due")}
                    </div>
                    <div className={styles.balanceHint}>
                      {balanceDue > 0
                        ? t("billing:detail.outstanding")
                        : t("billing:detail.fully_settled")}
                    </div>
                  </div>
                  <div
                    className={
                      balanceDue > 0
                        ? styles.balanceChipDue
                        : styles.balanceChipSettled
                    }
                    dir="ltr"
                  >
                    {formatMoney(balanceDue.toFixed(2), lang)}
                  </div>
                </div>
              </div>
            </div>

            {/* Payments Ledger Card */}
            <div className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:detail.ledger_title")}
                </h2>
                <span className={styles.countText}>
                  {invoice.payments?.length || 0}{" "}
                  {invoice.payments?.length === 1
                    ? t("billing:detail.entries_recorded_one")
                    : t("billing:detail.entries_recorded_other")}
                </span>
              </div>

              <div className={styles.ledger}>
                {invoice.payments && invoice.payments.length > 0 ? (
                  invoice.payments.map((p) => {
                    const isRefund = p.kind === "refund";
                    return (
                      <div
                        key={p.id}
                        className={`${styles.paymentRow} ${
                          isRefund ? styles.paymentRowRefund : ""
                        }`}
                      >
                        <div>
                          <div className={styles.paymentMeta}>
                            <span className={styles.paymentDate}>
                              <bdi dir="ltr">{formatPkt(p.created_at)}</bdi>
                            </span>
                            <span className={styles.metaSep}>·</span>
                            <span
                              className={
                                isRefund
                                  ? styles.kindPillRefund
                                  : styles.kindPill
                              }
                            >
                              {t(`billing:detail.kind.${p.kind}`)}:{" "}
                              {t(`billing:detail.method.${p.method}`)}
                            </span>
                          </div>
                          {p.reference && (
                            <div className={styles.referenceLine}>
                              {t("billing:detail.reference_label")}{" "}
                              <bdi dir="ltr">{p.reference}</bdi>
                            </div>
                          )}
                          {p.received_by && (
                            <div className={styles.cashierLine}>
                              {t("billing:detail.cashier_label")}{" "}
                              <bdi dir="ltr">{p.received_by}</bdi>
                            </div>
                          )}
                        </div>
                        <div className={styles.amountBlock}>
                          <span
                            className={`${styles.amountChip} ${
                              isRefund ? styles.amountChipRefund : ""
                            }`}
                            dir="ltr"
                          >
                            {isRefund ? "-" : "+"}{" "}
                            {formatMoney(
                              parseFloat(p.amount || "0").toFixed(2),
                              lang,
                            )}
                          </span>
                          <div
                            className={`${styles.entryState} ${
                              isRefund
                                ? styles.entryRefund
                                : styles.entrySettled
                            }`}
                          >
                            {isRefund
                              ? t("billing:detail.entry_refunded")
                              : t("billing:detail.entry_settled")}
                          </div>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className={styles.noPayments}>
                    {t("billing:detail.no_payments")}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: RECORD PAYMENT & REFUND & DANGER */}
          <div className={styles.rightCol}>
            {/* Card 1: Record payment */}
            {invoice.status !== "cancelled" && balanceDue > 0 && (
              <div className={styles.formCard}>
                <div className={styles.formHead}>
                  <h2 className={styles.formTitle}>
                    {t("billing:detail.record_payment_title")}
                  </h2>
                  <p className={styles.formHint}>
                    {t("billing:detail.record_payment_hint")}
                  </p>
                </div>

                <form onSubmit={handleRecordPayment} className={styles.form}>
                  <div className={styles.field}>
                    <label htmlFor={payAmountId} className={styles.label}>
                      {t("billing:detail.amount_label")}{" "}
                      <span className={styles.required}>*</span>
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
                      className={styles.input}
                    />
                    <span className={styles.hint}>
                      {t("billing:detail.max_payable", {
                        amount: formatMoney(balanceDue.toFixed(2), lang),
                      })}{" "}
                      <button
                        type="button"
                        onClick={() => setPayAmount(balanceDue.toFixed(2))}
                        className={styles.fillChip}
                      >
                        Pay full balance
                      </button>
                    </span>
                  </div>

                  <div className={styles.field}>
                    <label htmlFor={payMethodId} className={styles.label}>
                      {t("billing:detail.payment_method_label")}{" "}
                      <span className={styles.required}>*</span>
                    </label>
                    <select
                      id={payMethodId}
                      value={payMethod}
                      onChange={(e) =>
                        setPayMethod(e.target.value as PaymentMethod)
                      }
                      className={styles.select}
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

                  <div className={styles.field}>
                    <label htmlFor={payRefId} className={styles.label}>
                      {t("billing:detail.reference_field_label")}{" "}
                      {payMethod !== "cash" && (
                        <span className={styles.required}>*</span>
                      )}
                    </label>
                    <input
                      id={payRefId}
                      type="text"
                      value={payReference}
                      onChange={(e) => setPayReference(e.target.value)}
                      placeholder={t("billing:detail.reference_placeholder")}
                      className={styles.select}
                    />
                    <span className={styles.hint}>
                      {t("billing:detail.reference_help")}
                    </span>
                  </div>

                  <button
                    type="submit"
                    disabled={submittingPayment}
                    className={styles.submitButton}
                  >
                    {submittingPayment ? (
                      <span>{t("billing:detail.recording_payment")}</span>
                    ) : (
                      <>
                        <CreditCard
                          className={styles.buttonIcon}
                          aria-hidden="true"
                        />
                        <span>{t("billing:detail.record_payment_title")}</span>
                      </>
                    )}
                  </button>
                </form>
              </div>
            )}

            {/* Card 2: Record refund. Collapsed behind a disclosure while a
                balance is still due, so only settlement is expanded. */}
            {invoice.status !== "cancelled" &&
              netPaidNum > 0 &&
              (balanceDue > 0 && !showRefundForm ? (
                <button
                  type="button"
                  onClick={() => setShowRefundForm(true)}
                  className={styles.refundToggle}
                >
                  <RotateCcw className={styles.buttonIcon} aria-hidden="true" />
                  <span>Issue a refund…</span>
                </button>
              ) : (
                <div className={styles.formCard}>
                  <div className={styles.formHead}>
                    <h2 className={styles.formTitle}>
                      {t("billing:detail.record_refund_title")}
                    </h2>
                    <p className={styles.formHint}>
                      {t("billing:detail.record_refund_hint")}
                    </p>
                  </div>

                  <form onSubmit={handleRecordRefund} className={styles.form}>
                    <div className={styles.field}>
                      <label htmlFor={refundAmountId} className={styles.label}>
                        {t("billing:detail.refund_amount_label")}{" "}
                        <span className={styles.required}>*</span>
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
                        className={styles.input}
                      />
                      <span className={styles.hint}>
                        {t("billing:detail.refund_max", {
                          amount: formatMoney(netPaidNum.toFixed(2), lang),
                        })}
                      </span>
                    </div>

                    <div className={styles.field}>
                      <label htmlFor={refundMethodId} className={styles.label}>
                        {t("billing:detail.refund_method_label")}{" "}
                        <span className={styles.required}>*</span>
                      </label>
                      <select
                        id={refundMethodId}
                        value={refundMethod}
                        onChange={(e) =>
                          setRefundMethod(e.target.value as PaymentMethod)
                        }
                        className={styles.select}
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

                    <div className={styles.field}>
                      <label htmlFor={refundReasonId} className={styles.label}>
                        {t("billing:detail.reason_note_label")}{" "}
                        <span className={styles.required}>*</span>
                      </label>
                      <input
                        id={refundReasonId}
                        type="text"
                        value={refundReason}
                        onChange={(e) => setRefundReason(e.target.value)}
                        placeholder={t("billing:detail.reason_placeholder")}
                        required
                        className={styles.select}
                      />
                    </div>

                    {refundMethod !== "cash" && (
                      <div className={styles.field}>
                        <label
                          htmlFor={refundReferenceId}
                          className={styles.label}
                        >
                          {t("billing:detail.reference_label")}{" "}
                          <span className={styles.required}>*</span>
                        </label>
                        <input
                          id={refundReferenceId}
                          type="text"
                          value={refundReference}
                          onChange={(e) => setRefundReference(e.target.value)}
                          placeholder={t(
                            "billing:detail.reference_placeholder",
                          )}
                          required
                          className={styles.input}
                        />
                        <span className={styles.hint}>
                          {t("billing:detail.reference_help")}
                        </span>
                      </div>
                    )}

                    <button
                      type="submit"
                      ref={refundTriggerRef}
                      disabled={submittingRefund}
                      className={styles.textButton}
                    >
                      {submittingRefund ? (
                        <span>{t("billing:detail.recording_refund")}</span>
                      ) : (
                        <>
                          <RotateCcw
                            className={styles.buttonIcon}
                            aria-hidden="true"
                          />
                          <span>{t("billing:detail.record_refund_title")}</span>
                        </>
                      )}
                    </button>
                  </form>
                </div>
              ))}

            {/* Card 3: Danger Zone / Cancel invoice */}
            <div className={styles.dangerCard}>
              <div className={styles.dangerHead}>
                <span className={styles.dangerTitle}>
                  {t("billing:detail.cancel_title")}
                </span>
                <span className={styles.dangerHint}>
                  {t("billing:detail.cancel_hint")}
                </span>
              </div>
              <p className={styles.dangerText}>
                {t("billing:detail.cancel_description")}
              </p>
              {invoice.status === "paid" && totalNum === 0 && (
                <p className={styles.dangerText}>
                  {t("billing:detail.zero_total_close_hint")}
                </p>
              )}
              {invoice.status === "refunded" &&
                netRevenueNum === 0 &&
                hasVoidedCreditNote && (
                  <p className={styles.dangerText}>
                    {t("billing:detail.terminal_close_hint")}
                  </p>
                )}
              <button
                type="button"
                ref={cancelTriggerRef}
                onClick={() => setShowCancelModal(true)}
                disabled={!canCancel}
                className={styles.dangerButton}
              >
                <Ban className={styles.buttonIcon} aria-hidden="true" />
                <span>{t("billing:detail.cancel_title")}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Cancel Modal Dialog */}
      {showCancelModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="cancel-dialog-title"
          className={styles.scrim}
        >
          <div ref={cancelPanelRef} tabIndex={-1} className={styles.modal}>
            <h3 id="cancel-dialog-title" className={styles.modalTitle}>
              {t("billing:detail.cancel_modal_title")}
            </h3>
            <p className={styles.modalText}>
              {t("billing:detail.cancel_modal_body")}
            </p>
            <div className={styles.field}>
              <label htmlFor={cancelReasonId} className={styles.label}>
                {t("billing:detail.cancel_reason_label")}{" "}
                <span className={styles.required}>*</span>
              </label>
              <textarea
                id={cancelReasonId}
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder={t("billing:detail.cancel_reason_placeholder")}
                className={styles.textarea}
              />
            </div>
            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                disabled={submittingCancel}
                className={styles.textButton}
              >
                {t("billing:detail.keep_invoice")}
              </button>
              <button
                type="button"
                onClick={handleConfirmCancel}
                disabled={submittingCancel || !cancelReason.trim()}
                className={styles.confirmDanger}
              >
                {submittingCancel
                  ? t("billing:detail.cancelling")
                  : t("billing:detail.confirm_cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Line-cancel Modal Dialog — unperformed test, Owner/Manager only. */}
      {lineCancelItemId && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="line-cancel-dialog-title"
          className={styles.scrim}
        >
          <div className={styles.modal}>
            <h3 id="line-cancel-dialog-title" className={styles.modalTitle}>
              {t("billing:detail.line_cancel_title")}
            </h3>
            <p className={styles.modalText}>
              {t("billing:detail.line_cancel_hint")}
            </p>
            <div className={styles.field}>
              <label htmlFor={lineCancelReasonId} className={styles.label}>
                {t("billing:detail.cancel_reason_label")}{" "}
                <span className={styles.required}>*</span>
              </label>
              <textarea
                id={lineCancelReasonId}
                rows={3}
                value={lineCancelReason}
                onChange={(e) => setLineCancelReason(e.target.value)}
                placeholder={t("billing:detail.line_cancel_placeholder")}
                className={styles.textarea}
              />
            </div>
            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => {
                  setLineCancelItemId(null);
                  setLineCancelReason("");
                }}
                disabled={submittingLineCancel}
                className={styles.textButton}
              >
                {t("billing:detail.keep_invoice")}
              </button>
              <button
                type="button"
                onClick={handleConfirmLineCancel}
                disabled={submittingLineCancel || !lineCancelReason.trim()}
                className={styles.confirmDanger}
              >
                {submittingLineCancel
                  ? t("billing:detail.cancelling_line")
                  : t("billing:detail.confirm_line_cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Refund Confirmation Modal — same .scrim pattern as Cancel invoice. */}
      {showRefundModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="refund-dialog-title"
          className={styles.scrim}
        >
          <div ref={refundPanelRef} tabIndex={-1} className={styles.modal}>
            <h3 id="refund-dialog-title" className={styles.modalTitle}>
              Confirm Refund
            </h3>
            <p className={styles.modalText}>
              {t("billing:detail.record_refund_hint")}
            </p>
            <dl className={styles.summaryList}>
              <div className={styles.summaryRow}>
                <dt className={styles.summaryLabel}>
                  {t("billing:detail.refund_amount_label")}
                </dt>
                <dd className={styles.summaryValue} dir="ltr">
                  {formatMoney(
                    (parseFloat(refundAmount) || 0).toFixed(2),
                    lang,
                  )}
                </dd>
              </div>
              <div className={styles.summaryRow}>
                <dt className={styles.summaryLabel}>
                  {t("billing:detail.refund_method_label")}
                </dt>
                <dd className={styles.summaryValue}>
                  {t(`billing:detail.method.${refundMethod}`)}
                </dd>
              </div>
              <div className={styles.summaryRow}>
                <dt className={styles.summaryLabel}>
                  {t("billing:detail.reason_note_label")}
                </dt>
                <dd className={styles.summaryValue}>{refundReason}</dd>
              </div>
            </dl>
            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setShowRefundModal(false)}
                disabled={submittingRefund}
                className={styles.textButton}
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleConfirmRefund}
                disabled={submittingRefund}
                className={styles.confirmDanger}
              >
                {submittingRefund
                  ? t("billing:detail.recording_refund")
                  : "Confirm Refund"}
              </button>
            </div>
          </div>
        </div>
      )}

      {lastPayment && invoice && (
        <PaymentSuccessModal
          isOpen={Boolean(lastPayment)}
          amount={lastPayment.amount}
          method={lastPayment.method}
          reference={lastPayment.reference}
          invoice={invoice}
          onPrintReceipt={() => {
            window.open(`/invoices/${invoice.id}/print`, "_blank");
          }}
          onProceedToSamples={
            onProceedToSamples
              ? () => {
                  setLastPayment(null);
                  onProceedToSamples(invoice);
                }
              : () => {
                  setLastPayment(null);
                  if (typeof window !== "undefined") {
                    window.location.assign(
                      `/samples/collect/step1?invoice=${invoice.invoice_number || invoice.id}`,
                    );
                  }
                }
          }
          onClose={() => setLastPayment(null)}
          onViewInvoice={() => {
            if (typeof window !== "undefined") {
              window.location.assign(`/invoices/${invoice.id}`);
            }
          }}
        />
      )}
    </div>
  );
}
