import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Printer,
  Plus,
  ExternalLink,
  Copy,
  CheckCheck,
  X,
  FileText,
} from "lucide-react";
import { useDialogFocus } from "../../../lib/dialogFocus";
import type { SampleCreatedResponse, SampleCollectionDraft } from "../types";
import styles from "./SampleCollectionSuccessModal.module.css";

export interface SampleCollectionSuccessModalProps {
  isOpen: boolean;
  sample: SampleCreatedResponse;
  draft: SampleCollectionDraft;
  collectorName?: string;
  onPrintLabel: (sampleId: string) => void;
  onViewDetails: (sampleId: string) => void;
  onCollectAnother: () => void;
  onClose: () => void;
}

export function SampleCollectionSuccessModal({
  isOpen,
  sample,
  draft,
  collectorName,
  onPrintLabel,
  onViewDetails,
  onCollectAnother,
  onClose,
}: SampleCollectionSuccessModalProps): JSX.Element | null {
  const { t, i18n } = useTranslation(["samples", "common"]);
  const [copied, setCopied] = useState(false);
  const panelRef = useDialogFocus<HTMLDivElement>(isOpen, onClose);

  if (!isOpen) return null;

  const handleCopyAccession = async () => {
    try {
      await navigator.clipboard.writeText(sample.accession_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const isRtl = i18n.language === "ur";

  const formattedCollectedAt = sample.collected_at
    ? new Date(sample.collected_at).toLocaleString(isRtl ? "ur-PK" : "en-GB", {
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

  const collectorDisplay =
    sample.collected_by ||
    collectorName ||
    draft.collected_by ||
    t("samples:success_modal.collected_by");

  return (
    <div className={styles.modalBackdrop}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="collection-success-title"
        className={styles.modalPanel}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          data-testid="close-modal-btn"
          aria-label={t("samples:success_modal.close_dialog")}
          className={styles.closeButton}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Hero Area */}
        <div className={styles.heroArea}>
          <div className={styles.iconRing}>
            <Check className="w-7 h-7 stroke-[3]" />
          </div>
          <h2 id="collection-success-title" className={styles.title}>
            {t("samples:success_modal.title")}
          </h2>
          <p className={styles.subtitle}>
            {t("samples:success_modal.subtitle")}
          </p>
        </div>

        {/* Accession ID Barcode Bar */}
        <div className={styles.accessionPill}>
          <div className={styles.accessionInfo}>
            <span className={styles.accessionLabel}>
              {t("samples:success_modal.accession_barcode")}
            </span>
            <span className={styles.accessionCode} dir="ltr">
              {sample.accession_id}
            </span>
          </div>
          <button
            type="button"
            onClick={handleCopyAccession}
            data-testid="copy-accession-btn"
            className={styles.copyButton}
          >
            {copied ? (
              <>
                <CheckCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">
                  {t("samples:success_modal.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t("samples:success_modal.copy")}</span>
              </>
            )}
          </button>
        </div>

        {/* Specimen & Patient Details Card */}
        <div className={styles.detailsCard}>
          <div className={styles.detailsGrid}>
            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.patient")}
              </span>
              <span className={styles.detailValue}>
                {draft.patient_name || "—"}
              </span>
              <span className={`${styles.detailSub} font-mono`} dir="ltr">
                {draft.patient_mrn}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.collected_by")}
              </span>
              <span className={styles.detailValue} title={collectorDisplay}>
                {collectorDisplay}
              </span>
              <span className={styles.detailSub}>
                {draft.branch_name || t("samples:list.table.branch")}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.collection_time")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                {formattedCollectedAt}
              </span>
              <span className={styles.detailSub}>
                {t("samples:success_modal.pkt")}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.invoice")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                #{draft.invoice_number || draft.invoice_id?.slice(0, 8)}
              </span>
              <span className={styles.detailSub}>
                {t("samples:success_modal.status")}: {sample.status}
              </span>
            </div>
          </div>

          {/* Assigned Diagnostic Tests */}
          {draft.test_labels && draft.test_labels.length > 0 && (
            <div className={styles.sectionDivider}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.tests_assigned", {
                  count: draft.test_labels.length,
                })}
              </span>
              <div className={styles.tagRow}>
                {draft.test_labels.map((lbl, idx) => (
                  <span key={idx} className={styles.testTag}>
                    {lbl}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Phlebotomy Tubes */}
          {draft.tubes_required && draft.tubes_required.length > 0 && (
            <div className={styles.sectionDivider}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.tubes_collected", {
                  count: draft.tubes_required.reduce(
                    (acc, t) => acc + (t.count || 1),
                    0,
                  ),
                })}
              </span>
              <div className={styles.tagRow}>
                {draft.tubes_required.map((tube, idx) => (
                  <span key={idx} className={styles.tubePill}>
                    <span
                      className="w-2.5 h-2.5 rounded-full border border-slate-300 shrink-0"
                      style={{ backgroundColor: tube.color }}
                    />
                    <span>
                      {tube.count}x {tube.type}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Notes if present */}
          {draft.notes && draft.notes.trim() && (
            <div className={styles.sectionDivider}>
              <span className={styles.detailLabel}>
                {t("samples:success_modal.notes")}
              </span>
              <p className="text-xs italic text-[var(--color-text)] mt-0.5">
                {draft.notes}
              </p>
            </div>
          )}
        </div>

        {/* Action Buttons Area */}
        <div className={styles.actionsArea}>
          <button
            type="button"
            data-testid="print-barcode-label-btn"
            onClick={() => onPrintLabel(sample.id)}
            className={styles.primaryAction}
          >
            <Printer className="w-4 h-4" />
            <span>{t("samples:success_modal.print_barcode_label")}</span>
          </button>

          <button
            type="button"
            data-testid="collect-another-sample-btn"
            onClick={onCollectAnother}
            className={styles.secondaryAction}
          >
            <Plus className="w-4 h-4" />
            <span>{t("samples:success_modal.collect_another_sample")}</span>
          </button>

          <div className={styles.tertiaryRow}>
            <button
              type="button"
              data-testid="view-sample-details-btn"
              onClick={() => onViewDetails(sample.id)}
              className={styles.ghostAction}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>{t("samples:success_modal.view_sample_details")}</span>
            </button>

            <button
              type="button"
              data-testid="back-to-samples-list-btn"
              onClick={onClose}
              className={styles.ghostAction}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>{t("samples:success_modal.back_to_samples_list")}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SampleCollectionSuccessModal;
