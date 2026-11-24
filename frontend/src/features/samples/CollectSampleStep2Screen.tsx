import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, AlertCircle, X, Clock } from "lucide-react";
import { messageForError } from "../../lib/errors";
import { useAuthStore } from "../auth/authStore";
import { sampleService } from "./sampleService";
import type { SampleCollectionDraft, SampleCreatedResponse } from "./types";
import {
  CollectWizardStepper,
  SampleCollectionSuccessModal,
} from "./components";
import styles from "./CollectSampleStep2Screen.module.css";

export interface CollectSampleStep2ScreenProps {
  draft: SampleCollectionDraft;
  onBack?: () => void;
  onConfirmed?: (sample: SampleCreatedResponse) => void;
  onPrintLabel?: (sampleId: string) => void;
  onViewDetails?: (sampleId: string) => void;
  onCollectAnother?: () => void;
  onClose?: () => void;
  service?: typeof sampleService;
}

export function CollectSampleStep2Screen({
  draft,
  onBack,
  onConfirmed,
  onPrintLabel,
  onViewDetails,
  onCollectAnother,
  onClose,
  service = sampleService,
}: CollectSampleStep2ScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const user = useAuthStore((s) => s.user);
  const [notes, setNotes] = useState<string>(draft.notes || "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [collectedSample, setCollectedSample] =
    useState<SampleCreatedResponse | null>(null);

  const handleCommitCollection = async () => {
    if (isSubmitting) return;

    try {
      setIsSubmitting(true);
      setErrorMessage(null);

      const trimmedNotes = notes.trim();
      const res = await service.collectSample({
        invoice_id: draft.invoice_id,
        invoice_item_ids: draft.selected_item_ids,
        notes: trimmedNotes.length > 0 ? trimmedNotes : undefined,
      });

      setCollectedSample(res);
      setIsSubmitting(false);
      onConfirmed?.(res);
    } catch (err) {
      setErrorMessage(messageForError(err, t));
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header */}
      <header className={styles.headerArea}>
        <h1 className={styles.title}>{t("samples:collect_page.title")}</h1>
        <p className={styles.subtitle}>
          {t("samples:collect_page.verify_subtitle")}
        </p>
      </header>

      {/* 2. Stepper */}
      <CollectWizardStepper currentStep={2} />

      {/* Error alert */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 3. Main Card */}
      <div className={styles.mainCard}>
        {/* Invoice Summary Strip */}
        <div className={styles.summaryStrip}>
          <div className={styles.summaryMeta}>
            <span className="font-semibold text-slate-900">
              {draft.patient_name}
            </span>
            <span className={styles.mrnTag}>
              <bdi dir="ltr">{draft.patient_mrn}</bdi>
            </span>
            <span>
              · <bdi dir="ltr">{draft.invoice_number || draft.invoice_id}</bdi>
            </span>
            {draft.branch_name && <span>· {draft.branch_name}</span>}
          </div>
        </div>

        {/* Selected Tests to Collect */}
        <div>
          <h2 className={styles.sectionTitle}>
            {t("samples:collect_page.selected_tests", {
              n: draft.selected_item_ids.length,
            })}
          </h2>
          <div className="space-y-2">
            {(draft.test_labels || []).map((label, idx) => (
              <div key={idx} className={styles.testItemCard}>
                <span className={styles.testItemName}>{label}</span>
                <span className={styles.readyBadge}>
                  {t("samples:collect_page.ready_to_collect")}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Phlebotomy Tubes Required */}
        {draft.tubes_required && draft.tubes_required.length > 0 && (
          <div>
            <h2 className={styles.sectionTitle}>
              {t("samples:collect_page.tubes_required", {
                n: draft.tubes_required.reduce(
                  (acc, tube) => acc + (tube.count || 1),
                  0,
                ),
              })}
            </h2>
            <div className="space-y-2">
              {draft.tubes_required.map((tube, idx) => (
                <div key={idx} className={styles.testItemCard}>
                  <div className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full border border-slate-300 shrink-0"
                      style={{ backgroundColor: tube.color }}
                    />
                    <span className={styles.testItemName}>{tube.type}</span>
                    <span className="text-xs text-slate-500">
                      ({tube.specimen})
                    </span>
                  </div>
                  <span className={styles.tubeCountBadge}>
                    {tube.count === 1
                      ? t("samples:collect_page.tube_one", { n: tube.count })
                      : t("samples:collect_page.tube_many", {
                          n: tube.count,
                        })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Read-Only Automatic Inputs (D6) */}
        <div className={styles.automaticBox}>
          <div className={styles.automaticLabel}>
            {t("samples:collect_page.custody_details")}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>{t("samples:collect_page.custody_auto")}</span>
          </div>
        </div>

        {/* Collection Notes (Optional, max 500) */}
        <div>
          <label htmlFor="collection-notes" className={styles.sectionTitle}>
            {t("samples:collect_page.notes_label")}
          </label>
          <textarea
            id="collection-notes"
            rows={3}
            maxLength={500}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isSubmitting}
            placeholder={t("samples:collect_page.notes_placeholder")}
            className={styles.notesTextarea}
          />
          <div className={styles.charCount}>
            <span>
              {t("samples:collect_page.char_count", { count: notes.length })}
            </span>
          </div>
        </div>
      </div>

      {/* 4. Sticky Footer */}
      <footer className={styles.stickyFooter}>
        <button
          type="button"
          onClick={onBack}
          disabled={isSubmitting}
          className={styles.outlinePill}
        >
          <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
          <span>{t("samples:collect_page.back_to_step1")}</span>
        </button>

        <button
          type="button"
          onClick={handleCommitCollection}
          disabled={isSubmitting}
          className={styles.primaryBlackPill}
        >
          <Check className="w-4 h-4 stroke-[2.5]" />
          <span>
            {isSubmitting
              ? t("samples:collect_page.collecting")
              : t("samples:collect_page.collect")}
          </span>
        </button>
      </footer>

      {/* Veyla Success Modal */}
      {collectedSample && (
        <SampleCollectionSuccessModal
          isOpen={Boolean(collectedSample)}
          sample={collectedSample}
          draft={draft}
          collectorName={user?.name || user?.email}
          onPrintLabel={(sampleId) => {
            if (onPrintLabel) onPrintLabel(sampleId);
          }}
          onViewDetails={(sampleId) => {
            if (onViewDetails) onViewDetails(sampleId);
          }}
          onCollectAnother={() => {
            if (onCollectAnother) onCollectAnother();
            else setCollectedSample(null);
          }}
          onClose={() => {
            if (onClose) onClose();
            else setCollectedSample(null);
          }}
        />
      )}
    </div>
  );
}

export default CollectSampleStep2Screen;
