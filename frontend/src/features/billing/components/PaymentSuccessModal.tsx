import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ExternalLink,
  Copy,
  CheckCheck,
  X,
  Printer,
  TestTube,
} from "lucide-react";
import { useDialogFocus } from "../../../lib/dialogFocus";
import type { InvoiceDetail } from "../types";
import styles from "../../../components/ui/VeylaSuccessModal.module.css";

export interface PaymentSuccessModalProps {
  isOpen: boolean;
  amount: string;
  method: string;
  reference?: string | null;
  invoice: InvoiceDetail;
  onPrintReceipt?: () => void;
  onProceedToSamples?: () => void;
  onClose: () => void;
}

export function PaymentSuccessModal({
  isOpen,
  amount,
  method,
  reference,
  invoice,
  onPrintReceipt,
  onProceedToSamples,
  onClose,
}: PaymentSuccessModalProps): JSX.Element | null {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const [copied, setCopied] = useState(false);
  const panelRef = useDialogFocus<HTMLDivElement>(isOpen, onClose);

  if (!isOpen) return null;

  const receiptRef =
    reference ||
    `REC-${invoice.invoice_number || invoice.id.slice(0, 8).toUpperCase()}`;

  const handleCopyRef = async () => {
    try {
      await navigator.clipboard.writeText(receiptRef);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const isRtl = i18n.language === "ur";

  const nowFormatted = new Date().toLocaleString(isRtl ? "ur-PK" : "en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Karachi",
  });

  const totalNum = parseFloat(invoice.total || "0") || 0;
  const currentNetPaid = parseFloat(invoice.net_paid || "0") || 0;
  const amountNum = parseFloat(amount || "0") || 0;
  const effectivePaid =
    invoice.status === "paid"
      ? totalNum
      : currentNetPaid >= amountNum
        ? currentNetPaid
        : currentNetPaid + amountNum;
  const remaining = Math.max(0, totalNum - effectivePaid);
  const isFullySettled = invoice.status === "paid" || remaining <= 0;

  return (
    <div className={styles.modalBackdrop}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="payment-success-title"
        className={styles.modalPanel}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          data-testid="close-payment-modal-btn"
          aria-label={t("billing:payment_success_modal.close_dialog")}
          className={styles.closeButton}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Hero Area */}
        <div className={styles.heroArea}>
          <div className={styles.iconRing}>
            <Check className="w-7 h-7 stroke-[3]" />
          </div>
          <h2 id="payment-success-title" className={styles.title}>
            {t("billing:payment_success_modal.title")}
          </h2>
          <p className={styles.subtitle}>
            {t("billing:payment_success_modal.subtitle")}
          </p>
        </div>

        {/* Receipt Ref Barcode Pill */}
        <div className={styles.codePill}>
          <div className={styles.codeInfo}>
            <span className={styles.codeLabel}>
              {t("billing:payment_success_modal.receipt_ref")}
            </span>
            <span className={styles.codeValue} dir="ltr">
              {receiptRef}
            </span>
          </div>
          <button
            type="button"
            onClick={handleCopyRef}
            data-testid="copy-payment-ref-btn"
            className={styles.copyButton}
          >
            {copied ? (
              <>
                <CheckCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">
                  {t("billing:payment_success_modal.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t("billing:payment_success_modal.copy")}</span>
              </>
            )}
          </button>
        </div>

        {/* Payment Details Card */}
        <div className={styles.detailsCard}>
          <div className={styles.detailsGrid}>
            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:payment_success_modal.amount_received")}
              </span>
              <span
                className={`${styles.detailValue} text-emerald-600 font-bold`}
                dir="ltr"
              >
                PKR {amount}
              </span>
              <span className="text-xs uppercase tracking-wider text-slate-500">
                {method}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:payment_success_modal.patient")}
              </span>
              <span className={styles.detailValue}>
                {invoice.patient_name || "—"}
              </span>
              {invoice.patient_mrn && (
                <span className={`${styles.detailSub} font-mono`} dir="ltr">
                  {invoice.patient_mrn}
                </span>
              )}
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:payment_success_modal.remaining_balance")}
              </span>
              <span
                className={`${styles.detailValue} ${
                  isFullySettled ? "text-emerald-600" : "text-amber-600"
                }`}
                dir="ltr"
              >
                {isFullySettled
                  ? t("billing:payment_success_modal.settled")
                  : `PKR ${remaining.toFixed(2)}`}
              </span>
              <span className={styles.detailSub}>
                {t("billing:payment_success_modal.invoice_total")}: PKR{" "}
                {invoice.total}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:payment_success_modal.payment_time")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                {nowFormatted}
              </span>
              <span className={styles.detailSub}>
                {t("billing:payment_success_modal.pkt")}
              </span>
            </div>
          </div>
        </div>

        {/* Action Buttons Area */}
        <div className={styles.actionsArea}>
          {onPrintReceipt && (
            <button
              type="button"
              data-testid="print-receipt-btn"
              onClick={onPrintReceipt}
              className={styles.primaryAction}
            >
              <Printer className="w-4 h-4" />
              <span>{t("billing:payment_success_modal.print_receipt")}</span>
            </button>
          )}

          {onProceedToSamples && (
            <button
              type="button"
              data-testid="proceed-to-samples-btn"
              onClick={onProceedToSamples}
              className={styles.secondaryAction}
            >
              <TestTube className="w-4 h-4" />
              <span>{t("billing:payment_success_modal.collect_specimen")}</span>
            </button>
          )}

          <div className={styles.tertiaryRow}>
            <button
              type="button"
              data-testid="view-invoice-btn"
              onClick={onClose}
              className={styles.ghostAction}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>{t("billing:payment_success_modal.view_invoice")}</span>
            </button>

            <button
              type="button"
              data-testid="done-payment-btn"
              onClick={onClose}
              className={styles.ghostAction}
            >
              <Check className="w-3.5 h-3.5" />
              <span>{t("billing:payment_success_modal.done")}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PaymentSuccessModal;
