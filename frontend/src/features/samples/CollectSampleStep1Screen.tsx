import { useCallback, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Calendar,
  CheckCircle2,
  Clock,
  FlaskConical,
  Info,
  Search,
  User,
  X,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatMoney } from "../../lib/format";
import { useAuthStore } from "../auth/authStore";
import { billingService } from "../billing/billingService";
import type { InvoiceDetail } from "../billing/types";
import type { SampleCollectionDraft } from "./types";

export interface CollectSampleStep1ScreenProps {
  preselectedInvoiceId?: string;
  onCancel?: () => void;
  onContinue?: (draft: SampleCollectionDraft) => void;
  billingServiceInstance?: typeof billingService;
}

export function CollectSampleStep1Screen({
  preselectedInvoiceId,
  onCancel,
  onContinue,
  billingServiceInstance = billingService,
}: CollectSampleStep1ScreenProps): JSX.Element {
  const { t, i18n } = useTranslation(["samples", "common"]);
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const user = useAuthStore((s) => s.user);

  const [invoiceQuery, setInvoiceQuery] = useState(preselectedInvoiceId || "");
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(
    new Set(),
  );
  const [collectedAt, setCollectedAt] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const searchInputId = useId();
  const collectedAtInputId = useId();
  const collectedByInputId = useId();
  const notesInputId = useId();

  // Initialize current PKT time (YYYY-MM-DD HH:mm)
  useEffect(() => {
    const now = new Date();
    const formatted = `${now.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "Asia/Karachi",
    })} ${now.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Karachi",
    })}`;
    setCollectedAt(formatted);
  }, []);

  // Fetch invoice helper
  const handleSearchInvoice = useCallback(
    async (idOrNumber: string) => {
      const q = idOrNumber.trim();
      if (!q) return;

      try {
        setIsLoading(true);
        setErrorMessage(null);
        const data = await billingServiceInstance.getInvoice(q);
        setInvoice(data);
        // Auto-select all items by default
        const allItemIds = new Set(data.items.map((i) => i.id));
        setSelectedItemIds(allItemIds);
      } catch (err) {
        setInvoice(null);
        setSelectedItemIds(new Set());
        setErrorMessage(messageForError(err, t));
      } finally {
        setIsLoading(false);
      }
    },
    [billingServiceInstance, t],
  );

  useEffect(() => {
    if (invoiceQuery) {
      handleSearchInvoice(invoiceQuery);
    }
  }, [handleSearchInvoice, invoiceQuery]); // Initial load

  const toggleItem = (itemId: string) => {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const handleContinue = () => {
    if (!invoice) {
      setErrorMessage(t("samples:errors.select_invoice"));
      return;
    }
    if (selectedItemIds.size === 0) {
      setErrorMessage(t("samples:errors.select_item"));
      return;
    }

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
        (i) => i.name || i.description || t("samples:collect.diagnostic_test"),
      ),
      tubes_required: [],
      collected_at: collectedAt,
      collected_by: user?.email || "",
      notes: notes.trim() || undefined,
    };

    onContinue?.(draft);
  };

  return (
    <div className="w-full max-w-[720px] mx-auto px-4 py-8">
      {/* Breadcrumb & Header */}
      <div className="mb-6">
        <nav
          aria-label={t("samples:breadcrumbs.aria")}
          className="flex items-center gap-2 text-xs text-slate-500 mb-1.5"
        >
          <button
            type="button"
            onClick={onCancel}
            className="hover:text-slate-800 transition-colors cursor-pointer"
          >
            {t("common:nav.samples")}
          </button>
          <span className="text-slate-300">/</span>
          <span className="text-slate-900 font-medium">
            {t("samples:breadcrumbs.new")}
          </span>
          <span className="text-slate-300 ms-1">·</span>
          <span className="text-slate-500 font-normal">
            {t("samples:time.pkt_in")}
          </span>
        </nav>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {t("samples:actions.collect_sample")}
          </h1>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-500 bg-white border border-slate-200 px-2.5 py-1 rounded-md shadow-xs">
            <span className="text-slate-400">
              {t("samples:collect.branch_label")}
            </span>
            <span className="font-semibold text-slate-700">
              {invoice?.branch_name || "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Error alert */}
      {errorMessage && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center justify-between"
        >
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            aria-label={t("samples:list.dismiss_error")}
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Form Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
        {/* SECTION 1: INVOICE PICKER */}
        <div>
          <label
            htmlFor={searchInputId}
            className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2"
          >
            {t("samples:collect.invoice")}
          </label>
          <div className="space-y-2.5">
            <div className="relative">
              <Search className="w-4 h-4 absolute start-3 top-2.5 text-slate-400" />
              <input
                id={searchInputId}
                type="text"
                value={invoiceQuery}
                onChange={(e) => setInvoiceQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleSearchInvoice(invoiceQuery);
                  }
                }}
                placeholder={t("samples:collect.invoice_search_placeholder")}
                className="w-full ps-9 pe-24 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600"
              />
              <button
                type="button"
                onClick={() => handleSearchInvoice(invoiceQuery)}
                disabled={isLoading}
                className="absolute end-2 top-2 px-2.5 py-0.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
              >
                {isLoading
                  ? t("samples:actions.searching")
                  : t("samples:actions.lookup")}
              </button>
            </div>

            {/* Selected Invoice Chip */}
            {invoice && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                <span
                  className="font-mono font-medium text-slate-900"
                  dir="ltr"
                >
                  {invoice.invoice_number || invoice.id}
                </span>
                <span className="text-slate-300">—</span>
                <span className="font-medium text-slate-800">
                  {invoice.patient_name || "—"}
                </span>
                <span className="text-slate-400 ms-1">
                  · {t("samples:collect.status_prefix")}{" "}
                  <bdi dir="ltr">{invoice.status.toUpperCase()}</bdi>{" "}
                  <bdi dir="ltr">
                    (
                    {formatMoney(
                      parseFloat(invoice.total || "0").toFixed(2),
                      lang,
                    )}
                    )
                  </bdi>
                </span>
              </div>
            )}
          </div>
        </div>

        {/* SECTION 2: PATIENT DEMOGRAPHICS */}
        {invoice && (
          <div className="pt-4 border-t border-slate-100">
            <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              {t("samples:collect.patient")}
            </span>
            <div className="bg-slate-50 border border-slate-200/80 rounded-lg px-3.5 py-2.5 flex items-center justify-between text-sm flex-wrap gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-900">
                  {invoice.patient_name || "—"}
                </span>
                <span className="text-slate-300">·</span>
                <span
                  className="font-mono text-xs text-slate-700 bg-white border border-slate-200 px-1.5 py-0.5 rounded"
                  dir="ltr"
                >
                  {invoice.patient_mrn || "—"}
                </span>
                {invoice.patient_sex && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span className="text-slate-600 text-xs">
                      {invoice.patient_sex}
                      {invoice.patient_age ? `, ${invoice.patient_age}` : ""}
                    </span>
                  </>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md shrink-0">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>{t("samples:collect.invoice_selected")}</span>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 3: TESTS FROM INVOICE */}
        {invoice && (
          <div className="pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2.5">
              <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                {t("samples:collect.tests_from_invoice")}
              </span>
              <span className="text-xs text-slate-500 font-normal">
                {t("samples:collect.items_hint", {
                  n: invoice.items.length,
                })}
              </span>
            </div>

            <div className="space-y-2">
              {invoice.items.map((item) => {
                const isSelected = selectedItemIds.has(item.id);
                const itemName =
                  item.name ||
                  item.description ||
                  t("samples:collect.diagnostic_test");
                return (
                  <label
                    key={item.id}
                    className={`flex items-start gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                      isSelected
                        ? "border-teal-300 bg-teal-50/20"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleItem(item.id)}
                      className="mt-1 w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-600 accent-teal-600 cursor-pointer"
                    />
                    <div className="flex-1 flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-900">
                            {itemName}
                          </span>
                          <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                            {item.panel_id
                              ? t("samples:collect.kinds.panel")
                              : item.test_id
                                ? t("samples:collect.kinds.test")
                                : t("samples:collect.kinds.item")}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {t("samples:collect.qty_each", {
                            qty: item.quantity,
                            price: formatMoney(
                              parseFloat(item.unit_price || "0").toFixed(2),
                              lang,
                            ),
                          })}
                        </p>
                      </div>
                      <div className="text-end">
                        <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 font-medium bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {t("samples:collect.pending_collection")}
                        </span>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* SECTION 4: COLLECTION DETAILS */}
        <div className="pt-4 border-t border-slate-100 space-y-4">
          <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
            {t("samples:collect.collection_details")}
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor={collectedAtInputId}
                className="block text-xs font-medium text-slate-700 mb-1.5"
              >
                {t("samples:collect.collected_at")}{" "}
                <span className="text-slate-400 font-normal">
                  {t("samples:time.pkt_paren")}
                </span>
              </label>
              <div className="relative">
                <Calendar className="w-4 h-4 absolute start-3 top-2.5 text-slate-400" />
                <input
                  id={collectedAtInputId}
                  type="text"
                  value={collectedAt}
                  onChange={(e) => setCollectedAt(e.target.value)}
                  className="w-full ps-9 pe-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 font-mono focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600"
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                {t("samples:collect.collected_at_hint")}
              </p>
            </div>

            <div>
              <label
                htmlFor={collectedByInputId}
                className="block text-xs font-medium text-slate-700 mb-1.5"
              >
                {t("samples:collect.collected_by")}
              </label>
              <div className="relative">
                <User className="w-4 h-4 absolute start-3 top-2.5 text-slate-400" />
                <input
                  id={collectedByInputId}
                  type="text"
                  value={user?.email || ""}
                  readOnly
                  className="w-full ps-9 pe-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 cursor-not-allowed"
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                {t("samples:collect.collected_by_hint")}
              </p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor={notesInputId}
                className="block text-xs font-medium text-slate-700"
              >
                {t("common:labels.notes")}{" "}
                <span className="text-slate-400 font-normal">
                  {t("samples:collect.optional_paren")}
                </span>
              </label>
              <span className="text-[11px] text-slate-400">
                {t("samples:collect.notes_hint")}
              </span>
            </div>
            <textarea
              id={notesInputId}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("samples:collect.notes_placeholder")}
              className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600 resize-none"
            />
          </div>
        </div>

        {/* Workflow Info Box */}
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3.5 flex items-start gap-3">
          <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
          <div className="text-xs text-slate-600 leading-relaxed">
            <span className="font-medium text-slate-700">
              {t("samples:collect.next_step_label")}
            </span>{" "}
            {t("samples:collect.next_step_body")}
          </div>
        </div>

        {/* Actions Footer */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:border-slate-300 transition-colors"
          >
            {t("common:actions.cancel")}
          </button>
          <button
            type="button"
            onClick={handleContinue}
            className="px-5 py-2 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg shadow-sm transition-colors flex items-center gap-2"
          >
            <FlaskConical className="w-4 h-4" />
            <span>{t("samples:actions.continue_to_verification")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
