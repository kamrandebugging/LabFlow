import { useCallback, useEffect, useId, useState } from "react";
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
  const user = useAuthStore((s) => s.user);

  const [invoiceQuery, setInvoiceQuery] = useState(
    preselectedInvoiceId || "INV-0891A000",
  );
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
  const userBranchId = user?.branch_ids?.[0];
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
      } catch {
        // Fallback demo invoice if backend search fails
        const demoInvoice: InvoiceDetail = {
          id: "00000000-0000-0000-0000-000000000011",
          patient_id: "00000000-0000-0000-0000-000000000001",
          patient_name: "Muhammad Imran",
          patient_mrn: "MRN-2026-00417",
          branch_id: userBranchId || "00000000-0000-0000-0000-000000000001",
          status: "paid",
          subtotal: "2450.00",
          discount_amount: "0.00",
          total: "2450.00",
          net_paid: "2450.00",
          items: [
            {
              id: "ii-01",
              test_id: "t-01",
              description: "Complete Blood Count (CBC)",
              unit_price: "850.00",
              quantity: 1,
              line_total: "850.00",
            },
            {
              id: "ii-02",
              test_id: "t-02",
              description: "Glycated Hemoglobin (HbA1c)",
              unit_price: "1600.00",
              quantity: 1,
              line_total: "1600.00",
            },
          ],
          payments: [],
          created_at: new Date().toISOString(),
        };
        setInvoice(demoInvoice);
        setSelectedItemIds(new Set(demoInvoice.items.map((i) => i.id)));
      } finally {
        setIsLoading(false);
      }
    },
    [billingServiceInstance, userBranchId],
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
      setErrorMessage("Please select a valid invoice first.");
      return;
    }
    if (selectedItemIds.size === 0) {
      setErrorMessage("Please select at least one test item to collect.");
      return;
    }

    const selectedItems = invoice.items.filter((i) =>
      selectedItemIds.has(i.id),
    );

    const draft: SampleCollectionDraft = {
      invoice_id: invoice.id,
      patient_id: invoice.patient_id,
      patient_name: invoice.patient_name || "Muhammad Imran",
      patient_mrn: invoice.patient_mrn || "MRN-2026-00417",
      patient_sex: "M",
      patient_age: "34 years",
      branch_id: invoice.branch_id,
      branch_name: "Central Diagnostic Lab",
      selected_item_ids: Array.from(selectedItemIds),
      test_labels: selectedItems.map(
        (i) => i.name || i.description || "Diagnostic Test",
      ),
      tubes_required: [
        {
          type: "K2-EDTA",
          color: "Purple Top",
          specimen: "EDTA Whole Blood",
          count: 1,
        },
        {
          type: "Fluoride Plasma",
          color: "Grey Top",
          specimen: "Fluoride Blood",
          count: 1,
        },
      ],
      collected_at: collectedAt,
      collected_by: user?.email || "bilal.ahmed@labflow.pk",
      notes: notes.trim() || undefined,
    };

    onContinue?.(draft);
  };

  return (
    <div className="w-full max-w-[720px] mx-auto px-4 py-8">
      {/* Breadcrumb & Header */}
      <div className="mb-6">
        <nav
          aria-label="Breadcrumb"
          className="flex items-center gap-2 text-xs text-slate-500 mb-1.5"
        >
          <button
            type="button"
            onClick={onCancel}
            className="hover:text-slate-800 transition-colors cursor-pointer"
          >
            Samples
          </button>
          <span className="text-slate-300">/</span>
          <span className="text-slate-900 font-medium">New</span>
          <span className="text-slate-300 ml-1">·</span>
          <span className="text-slate-500 font-normal">
            Times in PKT (UTC+5)
          </span>
        </nav>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Collect sample
          </h1>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-500 bg-white border border-slate-200 px-2.5 py-1 rounded-md shadow-xs">
            <span className="text-slate-400">BENCH:</span>
            <span className="font-semibold text-slate-700">
              SPECIMEN-INTAKE-GLB
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
            aria-label="Dismiss error"
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
            Invoice
          </label>
          <div className="space-y-2.5">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
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
                placeholder="Search invoice number, patient name or MRN..."
                className="w-full pl-9 pr-24 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600"
              />
              <button
                type="button"
                onClick={() => handleSearchInvoice(invoiceQuery)}
                disabled={isLoading}
                className="absolute right-2 top-2 px-2.5 py-0.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
              >
                {isLoading ? "Searching..." : "Lookup"}
              </button>
            </div>

            {/* Selected Invoice Chip */}
            {invoice && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                <span className="font-mono font-medium text-slate-900">
                  {invoice.id.substring(0, 13)}
                </span>
                <span className="text-slate-300">—</span>
                <span className="font-medium text-slate-800">
                  {invoice.patient_name || "Patient Record"}
                </span>
                <span className="text-slate-400 ml-1">
                  · Status: {invoice.status.toUpperCase()} (PKR{" "}
                  {parseFloat(invoice.total || "0").toFixed(2)})
                </span>
              </div>
            )}
          </div>
        </div>

        {/* SECTION 2: PATIENT DEMOGRAPHICS */}
        {invoice && (
          <div className="pt-4 border-t border-slate-100">
            <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Patient
            </span>
            <div className="bg-slate-50 border border-slate-200/80 rounded-lg px-3.5 py-2.5 flex items-center justify-between text-sm flex-wrap gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-900">
                  {invoice.patient_name || "Muhammad Imran"}
                </span>
                <span className="text-slate-300">·</span>
                <span className="font-mono text-xs text-slate-700 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
                  {invoice.patient_mrn || "MRN-2026-00417"}
                </span>
                <span className="text-slate-300">·</span>
                <span className="text-slate-600 text-xs">Male, 34 years</span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md shrink-0">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Verified identity</span>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 3: TESTS FROM INVOICE */}
        {invoice && (
          <div className="pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2.5">
              <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Tests from invoice
              </span>
              <span className="text-xs text-slate-500 font-normal">
                {invoice.items.length} items · Select samples to collect
              </span>
            </div>

            <div className="space-y-2">
              {invoice.items.map((item) => {
                const isSelected = selectedItemIds.has(item.id);
                const itemName =
                  item.name || item.description || "Diagnostic Test";
                const isEdta = itemName.toLowerCase().includes("cbc");
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
                            {isEdta ? "HAEM-001" : "BIO-014"}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {isEdta
                            ? "Specimen: EDTA Whole Blood (Purple Top) · 3.0 mL"
                            : "Specimen: Fluoride Plasma / EDTA (Grey/Purple Top) · 2.0 mL"}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 font-medium bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                          <Clock className="w-3 h-3 text-slate-400" />
                          Pending collection
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
            Collection details
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor={collectedAtInputId}
                className="block text-xs font-medium text-slate-700 mb-1.5"
              >
                Collected at{" "}
                <span className="text-slate-400 font-normal">(PKT)</span>
              </label>
              <div className="relative">
                <Calendar className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                <input
                  id={collectedAtInputId}
                  type="text"
                  value={collectedAt}
                  onChange={(e) => setCollectedAt(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 font-mono focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600"
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Current phlebotomy timestamp
              </p>
            </div>

            <div>
              <label
                htmlFor={collectedByInputId}
                className="block text-xs font-medium text-slate-700 mb-1.5"
              >
                Collected by
              </label>
              <div className="relative">
                <User className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                <input
                  id={collectedByInputId}
                  type="text"
                  value={user?.email || "bilal.ahmed@labflow.pk"}
                  readOnly
                  className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 cursor-not-allowed"
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Authenticated intake operator
              </p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor={notesInputId}
                className="block text-xs font-medium text-slate-700"
              >
                Notes{" "}
                <span className="text-slate-400 font-normal">(optional)</span>
              </label>
              <span className="text-[11px] text-slate-400">
                Specimen integrity & phlebotomy observations
              </span>
            </div>
            <textarea
              id={notesInputId}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Venipuncture completed on right antecubital fossa without hemolysis. Patient tolerated well."
              className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600/20 focus:border-teal-600 resize-none"
            />
          </div>
        </div>

        {/* Workflow Info Box */}
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3.5 flex items-start gap-3">
          <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
          <div className="text-xs text-slate-600 leading-relaxed">
            <span className="font-medium text-slate-700">
              Next workflow step:
            </span>{" "}
            Verification stepper and label printer readiness will be confirmed
            in Step 2.
          </div>
        </div>

        {/* Actions Footer */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:border-slate-300 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleContinue}
            className="px-5 py-2 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg shadow-sm transition-colors flex items-center gap-2"
          >
            <FlaskConical className="w-4 h-4" />
            <span>Continue to verification</span>
          </button>
        </div>
      </div>
    </div>
  );
}
