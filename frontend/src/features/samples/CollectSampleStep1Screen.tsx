import { useCallback, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ArrowRight, Search, X, AlertCircle } from "lucide-react";
import { messageForError } from "../../lib/errors";
import { billingService } from "../billing/billingService";
import type { InvoiceDetail } from "../billing/types";
import type { SampleCollectionDraft } from "./types";
import { CollectWizardStepper } from "./components";
import styles from "./CollectSampleStep1Screen.module.css";

export interface CollectSampleStep1ScreenProps {
  preselectedInvoiceId?: string;
  initialDraft?: SampleCollectionDraft;
  onCancel?: () => void;
  onContinue?: (draft: SampleCollectionDraft) => void;
  billingServiceInstance?: typeof billingService;
}

export function CollectSampleStep1Screen({
  preselectedInvoiceId,
  initialDraft,
  onCancel,
  onContinue,
  billingServiceInstance = billingService,
}: CollectSampleStep1ScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const searchInputId = useId();

  const [invoiceQuery, setInvoiceQuery] = useState(
    initialDraft?.invoice_number ||
      initialDraft?.invoice_id ||
      preselectedInvoiceId ||
      "",
  );
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(
    initialDraft ? new Set(initialDraft.selected_item_ids) : new Set(),
  );
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSearchInvoice = useCallback(
    async (idOrNumber: string) => {
      const q = idOrNumber.trim();
      if (!q) return;

      try {
        setIsLoading(true);
        setErrorMessage(null);
        const data = await billingServiceInstance.getInvoice(q);
        setInvoice(data);
        if (!initialDraft || initialDraft.invoice_id !== data.id) {
          // Auto-select all items by default for a newly loaded invoice
          setSelectedItemIds(new Set(data.items.map((i) => i.id)));
        }
      } catch (err) {
        setInvoice(null);
        setSelectedItemIds(new Set());
        const candidate = err as { status?: number; code?: string };
        if (candidate?.status === 404 || candidate?.code === "not_found") {
          setErrorMessage(
            t("samples:collect_page.invoice_not_found", { query: q }),
          );
        } else {
          setErrorMessage(messageForError(err, t));
        }
      } finally {
        setIsLoading(false);
      }
    },
    [billingServiceInstance, initialDraft, t],
  );

  useEffect(() => {
    if (invoiceQuery.trim()) {
      handleSearchInvoice(invoiceQuery);
    }
  }, [handleSearchInvoice, invoiceQuery]);

  const toggleItem = (itemId: string) => {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const canContinue = Boolean(invoice && selectedItemIds.size > 0);

  let validationReason = "";
  if (!invoice) {
    validationReason = t("samples:collect_page.validation_select_invoice");
  } else if (selectedItemIds.size === 0) {
    validationReason = t("samples:collect_page.validation_select_item");
  }

  const handleContinue = () => {
    if (!invoice || selectedItemIds.size === 0) return;

    const selectedItems = invoice.items.filter((i) =>
      selectedItemIds.has(i.id),
    );

    const draft: SampleCollectionDraft = {
      invoice_id: invoice.id,
      invoice_number: invoice.invoice_number,
      patient_id: invoice.patient_id,
      patient_name: invoice.patient_name || "—",
      patient_mrn: invoice.patient_mrn || "—",
      patient_sex: invoice.patient_sex || "",
      patient_age: invoice.patient_age || "",
      branch_id: invoice.branch_id,
      branch_name: invoice.branch_name || "",
      selected_item_ids: Array.from(selectedItemIds),
      test_labels: selectedItems.map(
        (i) =>
          i.name || i.description || t("samples:collect_page.diagnostic_test"),
      ),
      tubes_required: initialDraft?.tubes_required || [],
      collected_at: initialDraft?.collected_at || "",
      collected_by: initialDraft?.collected_by || "",
      notes: initialDraft?.notes || "",
    };

    onContinue?.(draft);
  };

  return (
    <div className={styles.pageContainer}>
      {/* 1. Page Header */}
      <header className={styles.headerArea}>
        <h1 className={styles.title}>{t("samples:collect_page.title")}</h1>
        <p className={styles.subtitle}>{t("samples:collect_page.subtitle")}</p>
      </header>

      {/* 2. Stepper */}
      <CollectWizardStepper currentStep={1} />

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

      {/* 3. Main Form Card */}
      <div className={styles.mainCard}>
        {/* Invoice Search Input */}
        <div>
          <h2 className={styles.sectionTitle}>
            {t("samples:collect_page.locate_invoice")}
          </h2>
          <div className={styles.searchBox}>
            <Search className={styles.searchIcon} />
            <input
              id={searchInputId}
              type="text"
              placeholder={t("samples:collect_page.invoice_placeholder")}
              value={invoiceQuery}
              onChange={(e) => setInvoiceQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
        </div>

        {/* Live Patient & Invoice Preview Card */}
        {invoice && (
          <div className={styles.livePreviewCard}>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.patient")}
              </span>
              <span className={styles.previewMetaValue}>
                {invoice.patient_name || "—"}
              </span>
            </div>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.mrn")}
              </span>
              <span className={styles.previewMetaValue}>
                <bdi dir="ltr">{invoice.patient_mrn || "—"}</bdi>
              </span>
            </div>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.age_sex")}
              </span>
              <span className={styles.previewMetaValue}>
                {invoice.patient_age
                  ? t("samples:collect_page.age_years", {
                      n: invoice.patient_age,
                    })
                  : "—"}{" "}
                {invoice.patient_sex ? `· ${invoice.patient_sex}` : ""}
              </span>
            </div>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.invoice_number")}
              </span>
              <span className={styles.previewMetaValue}>
                <bdi dir="ltr">{invoice.invoice_number}</bdi>
              </span>
            </div>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.branch")}
              </span>
              <span className={styles.previewMetaValue}>
                {invoice.branch_name || t("samples:collect_page.central_lab")}
              </span>
            </div>
            <div className={styles.previewMetaItem}>
              <span className={styles.previewMetaLabel}>
                {t("samples:collect_page.accession_id")}
              </span>
              <span className="text-xs text-slate-500 italic">
                {t("samples:collect_page.assigned_after_collect")}
              </span>
            </div>
          </div>
        )}

        {/* Ordered Items Selection List */}
        {invoice && (
          <div>
            <h2 className={styles.sectionTitle}>
              {t("samples:collect_page.select_tests")}
            </h2>
            <div className={styles.itemsList}>
              {invoice.items.map((item) => {
                const isSelected = selectedItemIds.has(item.id);
                return (
                  <label key={item.id} className={styles.itemRow}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleItem(item.id)}
                      className="w-4 h-4 rounded border-slate-300 text-teal-600 cursor-pointer"
                    />
                    <div className={styles.itemInfo}>
                      <span className={styles.itemName}>
                        {item.name ||
                          item.description ||
                          t("samples:collect_page.diagnostic_test")}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 4. Sticky Footer Controls */}
      <footer className={styles.stickyFooter}>
        <div className={styles.footerLeft}>
          <button
            type="button"
            onClick={onCancel}
            className={styles.outlinePill}
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            <span>{t("samples:collect_page.cancel")}</span>
          </button>
          {!canContinue && (
            <span className={styles.validationHint}>{validationReason}</span>
          )}
        </div>
        <div className={styles.footerRight}>
          <button
            type="button"
            disabled={!canContinue || isLoading}
            onClick={handleContinue}
            className={styles.primaryBlackPill}
          >
            <span>{t("samples:collect_page.continue")}</span>
            <ArrowRight className="w-4 h-4 rtl:rotate-180" />
          </button>
        </div>
      </footer>
    </div>
  );
}

export default CollectSampleStep1Screen;
