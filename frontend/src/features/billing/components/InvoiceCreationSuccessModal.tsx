import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Plus,
  ExternalLink,
  Copy,
  CheckCheck,
  X,
  Printer,
  CreditCard,
  TestTube,
} from "lucide-react";
import { useDialogFocus } from "../../../lib/dialogFocus";
import type { InvoiceDetail } from "../types";
import styles from "../../../components/ui/VeylaSuccessModal.module.css";

export interface InvoiceCreationSuccessModalProps {
  isOpen: boolean;
  invoice: InvoiceDetail;
  onRecordPayment?: (invoiceId: string) => void;
  onCollectSpecimen?: (invoiceId: string) => void;
  onPrint?: (invoiceId: string) => void;
  onViewDetails?: (invoiceId: string) => void;
  onCreateAnother?: () => void;
  onClose: () => void;
}

export function InvoiceCreationSuccessModal({
  isOpen,
  invoice,
  onRecordPayment,
  onCollectSpecimen,
  onPrint,
  onViewDetails,
  onCreateAnother,
  onClose,
}: InvoiceCreationSuccessModalProps): JSX.Element | null {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const [copied, setCopied] = useState(false);
  const panelRef = useDialogFocus<HTMLDivElement>(isOpen, onClose);

  if (!isOpen) return null;

  const invoiceNum =
    invoice.invoice_number || `INV-${invoice.id.slice(0, 8).toUpperCase()}`;

  const handleCopyInvoiceNumber = async () => {
    try {
      await navigator.clipboard.writeText(invoiceNum);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const isRtl = i18n.language === "ur";

  const formattedCreatedAt = invoice.created_at
    ? new Date(invoice.created_at).toLocaleString(isRtl ? "ur-PK" : "en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Karachi",
      })
    : new Date().toLocaleString(isRtl ? "ur-PK" : "en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Karachi",
      });

  const isUnpaidOrPartial =
    invoice.status === "unpaid" || invoice.status === "partial";

  return (
    <div className={styles.modalBackdrop}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="invoice-success-title"
        className={styles.modalPanel}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          data-testid="close-invoice-modal-btn"
          aria-label={t("billing:invoice_success_modal.close_dialog")}
          className={styles.closeButton}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Hero Area */}
        <div className={styles.heroArea}>
          <div className={styles.iconRing}>
            <Check className="w-7 h-7 stroke-[3]" />
          </div>
          <h2 id="invoice-success-title" className={styles.title}>
            {t("billing:invoice_success_modal.title")}
          </h2>
          <p className={styles.subtitle}>
            {t("billing:invoice_success_modal.subtitle")}
          </p>
        </div>

        {/* Invoice Number Barcode Pill */}
        <div className={styles.codePill}>
          <div className={styles.codeInfo}>
            <span className={styles.codeLabel}>
              {t("billing:invoice_success_modal.invoice_number")}
            </span>
            <span className={styles.codeValue} dir="ltr">
              {invoiceNum}
            </span>
          </div>
          <button
            type="button"
            onClick={handleCopyInvoiceNumber}
            data-testid="copy-invoice-btn"
            className={styles.copyButton}
          >
            {copied ? (
              <>
                <CheckCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">
                  {t("billing:invoice_success_modal.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t("billing:invoice_success_modal.copy")}</span>
              </>
            )}
          </button>
        </div>

        {/* Invoice Details Card */}
        <div className={styles.detailsCard}>
          <div className={styles.detailsGrid}>
            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:invoice_success_modal.patient")}
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
                {t("billing:invoice_success_modal.total_amount")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                PKR {invoice.total}
              </span>
              <span className={styles.detailSub}>
                {t("billing:invoice_success_modal.status")}:{" "}
                <span className="capitalize font-semibold text-emerald-600">
                  {invoice.status}
                </span>
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:invoice_success_modal.balance_due")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                PKR{" "}
                {invoice.balance ??
                  (isUnpaidOrPartial ? invoice.total : "0.00")}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("billing:invoice_success_modal.created_at")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                {formattedCreatedAt}
              </span>
              <span className={styles.detailSub}>
                {t("billing:invoice_success_modal.pkt")}
              </span>
            </div>
          </div>

          {/* Test Line Items Tag Row */}
          {invoice.items && invoice.items.length > 0 && (
            <div className={styles.sectionDivider}>
              <span className={styles.detailLabel}>
                {t("billing:invoice_success_modal.tests_included", {
                  count: invoice.items.length,
                })}
              </span>
              <div className={styles.tagRow}>
                {invoice.items.map((it, idx) => {
                  const label =
                    it.name ||
                    it.description ||
                    (it as { test_name?: string }).test_name ||
                    (it as { panel_name?: string }).panel_name ||
                    `Item ${idx + 1}`;
                  return (
                    <span key={idx} className={styles.itemTag}>
                      {label}
                      {it.quantity > 1 ? ` × ${it.quantity}` : ""}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons Area */}
        <div className={styles.actionsArea}>
          {isUnpaidOrPartial && onRecordPayment ? (
            <button
              type="button"
              data-testid="record-payment-btn"
              onClick={() => onRecordPayment(invoice.id)}
              className={styles.primaryAction}
            >
              <CreditCard className="w-4 h-4" />
              <span>{t("billing:invoice_success_modal.record_payment")}</span>
            </button>
          ) : onCollectSpecimen ? (
            <button
              type="button"
              data-testid="collect-specimen-btn"
              onClick={() => onCollectSpecimen(invoice.id)}
              className={styles.primaryAction}
            >
              <TestTube className="w-4 h-4" />
              <span>{t("billing:invoice_success_modal.collect_specimen")}</span>
            </button>
          ) : null}

          {onPrint && (
            <button
              type="button"
              data-testid="print-invoice-btn"
              onClick={() => onPrint(invoice.id)}
              className={styles.secondaryAction}
            >
              <Printer className="w-4 h-4" />
              <span>{t("billing:invoice_success_modal.print_invoice")}</span>
            </button>
          )}

          <div className={styles.tertiaryRow}>
            {onViewDetails && (
              <button
                type="button"
                data-testid="view-invoice-details-btn"
                onClick={() => onViewDetails(invoice.id)}
                className={styles.ghostAction}
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>
                  {t("billing:invoice_success_modal.view_invoice_details")}
                </span>
              </button>
            )}

            {onCreateAnother && (
              <button
                type="button"
                data-testid="create-another-invoice-btn"
                onClick={onCreateAnother}
                className={styles.ghostAction}
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{t("billing:invoice_success_modal.create_another")}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default InvoiceCreationSuccessModal;
