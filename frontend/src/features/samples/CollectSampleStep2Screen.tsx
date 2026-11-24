import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, AlertCircle, X, Clock } from "lucide-react";
import { messageForError } from "../../lib/errors";
import { useAuthStore } from "../auth/authStore";
import { sampleService } from "./sampleService";
import type { SampleCollectionDraft, SampleCreatedResponse } from "./types";
import { CollectWizardStepper, SampleCollectionSuccessModal } from "./components";
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
        <h1 className={styles.title}>Collect sample</h1>
        <p className={styles.subtitle}>
          Verify tests and confirm specimen collection.
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
            <span className={styles.mrnTag}>{draft.patient_mrn}</span>
            <span>· Invoice #{draft.invoice_number || draft.invoice_id}</span>
            {draft.branch_name && <span>· {draft.branch_name}</span>}
          </div>
        </div>

        {/* Selected Tests to Collect */}
        <div>
          <h2 className={styles.sectionTitle}>
            Selected Tests ({draft.selected_item_ids.length})
          </h2>
          <div className="space-y-2">
            {(draft.test_labels || []).map((label, idx) => (
              <div key={idx} className={styles.testItemCard}>
                <span className={styles.testItemName}>{label}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-800 font-semibold border border-teal-200">
                  Ready to collect
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Phlebotomy Tubes Required */}
        {draft.tubes_required && draft.tubes_required.length > 0 && (
          <div>
            <h2 className={styles.sectionTitle}>
              Tubes Required (
              {draft.tubes_required.reduce((acc, t) => acc + (t.count || 1), 0)}
              )
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
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800">
                    {tube.count} {tube.count === 1 ? "tube" : "tubes"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Read-Only Automatic Inputs (D6) */}
        <div className={styles.automaticBox}>
          <div className={styles.automaticLabel}>Specimen Custody Details</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>
              Recorded automatically: server time on confirm / logged-in user
            </span>
          </div>
        </div>

        {/* Collection Notes (Optional, max 500) */}
        <div>
          <label htmlFor="collection-notes" className={styles.sectionTitle}>
            Collection Notes (Optional)
          </label>
          <textarea
            id="collection-notes"
            rows={3}
            maxLength={500}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isSubmitting}
            placeholder="Add relevant specimen notes (e.g. left arm draw, fasting confirmed)..."
            className={styles.notesTextarea}
          />
          <div className={styles.charCount}>
            <span>{notes.length} / 500 characters</span>
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
          <span>Back to Step 1</span>
        </button>

        <button
          type="button"
          onClick={handleCommitCollection}
          disabled={isSubmitting}
          className={styles.primaryBlackPill}
        >
          <Check className="w-4 h-4 stroke-[2.5]" />
          <span>
            {isSubmitting ? "Collecting specimen..." : "Collect sample"}
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
