import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  FileText,
  Search,
  Plus,
  X,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
} from "lucide-react";
import { catalogService } from "../catalog/catalogService";
import type { DiagnosticPanel, DiagnosticTest } from "../catalog/types";
import { patientService } from "../patients/patientService";
import type { PatientSummary } from "../patients/types";
import { billingService } from "./billingService";
import { formatMoney } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { InvoiceDetail, InvoiceItemInput } from "./types";

export interface NewInvoiceScreenProps {
  initialPatientId?: string;
  onSuccess?: (invoice: InvoiceDetail) => void;
  onCancel?: () => void;
  onRegisterPatient?: () => void;
}

interface SelectedLineItem {
  key: string;
  testId?: string;
  panelId?: string;
  code: string;
  name: string;
  price: number;
  quantity: number;
}

export function NewInvoiceScreen({
  initialPatientId,
  onSuccess,
  onCancel,
  onRegisterPatient,
}: NewInvoiceScreenProps): JSX.Element {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const lang: "en" | "ur" = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const patientInputId = useId();
  const searchInputId = useId();
  const panelSelectId = useId();
  const discountAmountId = useId();
  const discountReasonId = useId();

  // Patient Selection
  const [patientQuery, setPatientQuery] = useState("");
  const [patientResults, setPatientResults] = useState<PatientSummary[]>([]);
  const [isSearchingPatient, setIsSearchingPatient] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(
    null,
  );
  const [showPatientDropdown, setShowPatientDropdown] = useState(false);

  // Catalog
  const [availableTests, setAvailableTests] = useState<DiagnosticTest[]>([]);
  const [availablePanels, setAvailablePanels] = useState<DiagnosticPanel[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);

  // Panel-only tests cannot be billed standalone; they are excluded from the
  // individual-test picker and surfaced as an explanatory note instead.
  const selectableTests = availableTests.filter((test) => !test.is_panel_only);
  const panelOnlyTests = availableTests.filter((test) => test.is_panel_only);

  // Line items
  const [items, setItems] = useState<SelectedLineItem[]>([]);
  const [selectedTestToAdd, setSelectedTestToAdd] = useState<string>("");

  // Discount
  const [discountAmount, setDiscountAmount] = useState<string>("0");
  const [discountReason, setDiscountReason] = useState<string>("");

  // Submission & Feedback
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Load initial catalog
  useEffect(() => {
    let active = true;
    async function loadCatalog() {
      try {
        setCatalogLoading(true);
        const [tests, panels] = await Promise.all([
          catalogService.listTests({ isActive: true }).catch(() => []),
          catalogService.listPanels().catch(() => []),
        ]);
        if (active) {
          setAvailableTests(tests);
          setAvailablePanels(panels);
        }
      } catch (err) {
        if (active) {
          setErrorMessage(messageForError(err, t));
        }
      } finally {
        if (active) setCatalogLoading(false);
      }
    }
    loadCatalog();
    return () => {
      active = false;
    };
  }, [t]);

  // Pre-load patient if initialPatientId passed
  useEffect(() => {
    if (!initialPatientId) return;
    let active = true;
    async function loadInitial() {
      try {
        const patients = await patientService.listPatients();
        const found = patients.find((p) => p.id === initialPatientId);
        if (active && found) {
          setSelectedPatient(found);
        }
      } catch {
        // Ignore pre-fetch error
      }
    }
    loadInitial();
    return () => {
      active = false;
    };
  }, [initialPatientId]);

  // Debounced Patient Search
  useEffect(() => {
    if (!patientQuery.trim()) {
      setPatientResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setIsSearchingPatient(true);
      try {
        const results = await patientService.listPatients({ q: patientQuery });
        setPatientResults(results);
        setShowPatientDropdown(true);
      } catch {
        setPatientResults([]);
      } finally {
        setIsSearchingPatient(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [patientQuery]);

  // Add individual test
  const handleAddTest = (testId: string) => {
    if (!testId) return;
    const test = availableTests.find((candidate) => candidate.id === testId);
    if (!test) return;

    if (test.is_panel_only) {
      const panel = test.panel_codes?.length
        ? test.panel_codes.join(", ")
        : t("billing:new.a_panel");
      setErrorMessage(t("billing:new.error_panel_only_test", { panel }));
      return;
    }
    if (!test.price) {
      setErrorMessage(t("billing:new.error_no_price", { name: test.name }));
      return;
    }

    const price = parseFloat(test.price);
    const newItem: SelectedLineItem = {
      key: `test-${test.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      testId: test.id,
      code: test.code,
      name: test.name,
      price,
      quantity: 1,
    };
    setItems((prev) => [...prev, newItem]);
    setSelectedTestToAdd("");
    setErrorMessage(null);
  };

  // Add panel
  const handleAddPanel = (panelId: string) => {
    if (!panelId) return;
    const panel = availablePanels.find((p) => p.id === panelId);
    if (!panel) return;

    if (!panel.price) {
      setErrorMessage(t("billing:new.error_no_price", { name: panel.name }));
      return;
    }

    const price = parseFloat(panel.price);
    const newItem: SelectedLineItem = {
      key: `panel-${panel.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      panelId: panel.id,
      code: panel.code,
      name: `${panel.name} ${t("billing:new.package_suffix")}`,
      price,
      quantity: 1,
    };
    setItems((prev) => [...prev, newItem]);
  };

  // Remove item
  const handleRemoveItem = (key: string) => {
    setItems((prev) => prev.filter((item) => item.key !== key));
  };

  // Calculation
  const subtotal = items.reduce(
    (sum, item) => sum + item.price * item.quantity,
    0,
  );
  const discountVal = parseFloat(discountAmount) || 0;
  const netTotal = Math.max(0, subtotal - discountVal);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!selectedPatient) {
      setErrorMessage(t("billing:new.error_patient_required"));
      return;
    }
    if (items.length === 0) {
      setErrorMessage(t("billing:new.error_items_required"));
      return;
    }
    if (discountVal > 0 && !discountReason.trim()) {
      setErrorMessage(t("billing:new.error_discount_reason"));
      return;
    }
    if (discountVal > subtotal) {
      setErrorMessage(t("billing:new.error_discount_exceeds"));
      return;
    }

    try {
      setSubmitting(true);
      const invoiceItems: InvoiceItemInput[] = items.map((item) => ({
        test_id: item.testId || null,
        panel_id: item.panelId || null,
        qty: item.quantity,
      }));

      const created = await billingService.createInvoice({
        patient_id: selectedPatient.id,
        branch_id: selectedPatient.branch_id,
        items: invoiceItems,
        discount_amount: discountVal > 0 ? discountVal.toFixed(2) : "0.00",
        discount_reason: discountVal > 0 ? discountReason.trim() : null,
      });

      if (onSuccess) {
        onSuccess(created);
      }
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-4 py-6">
      {/* Breadcrumb & Page Header */}
      <div className="mb-6 flex flex-col gap-1">
        <nav
          aria-label={t("billing:new.breadcrumb_aria")}
          className="flex items-center gap-1.5 text-slate-500 text-xs"
        >
          <button
            type="button"
            onClick={onCancel}
            className="hover:text-slate-900 transition-colors cursor-pointer"
          >
            {t("billing:shared.invoices")}
          </button>
          <span className="text-slate-400">/</span>
          <span className="text-slate-900 font-semibold">
            {t("billing:new.breadcrumb_new")}
          </span>
        </nav>
        <div className="flex items-center justify-between mt-1">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("billing:new.title")}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {t("billing:new.subtitle")}
            </p>
          </div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-slate-100 text-slate-700 font-mono text-xs border border-slate-200">
            <FileText className="w-3.5 h-3.5 text-teal-700 shrink-0" />
            <span>{t("billing:new.draft", { id: "INV-NEW" })}</span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
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

      {/* Main Card */}
      <div className="bg-white rounded-xl p-8 border border-slate-200 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 1. PATIENT SECTION */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor={patientInputId}
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
              >
                {t("billing:new.patient_label")}{" "}
                <span className="text-red-600">*</span>
              </label>
              {onRegisterPatient && !selectedPatient && (
                <button
                  type="button"
                  onClick={onRegisterPatient}
                  className="text-xs text-teal-700 font-semibold hover:underline"
                >
                  + {t("billing:new.register_patient")}
                </button>
              )}
            </div>

            {selectedPatient ? (
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-teal-100 text-teal-800 font-bold flex items-center justify-center text-sm">
                    {selectedPatient.name?.substring(0, 2).toUpperCase() ||
                      t("billing:new.patient_initials")}
                  </div>
                  <div>
                    <div className="font-semibold text-slate-900 text-sm">
                      {selectedPatient.name} ·{" "}
                      <span className="font-mono text-xs text-slate-500">
                        <bdi dir="ltr">{selectedPatient.mrn}</bdi>
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {selectedPatient.phone
                        ? t("billing:new.patient_meta", {
                            sex:
                              selectedPatient.sex || t("common:labels.unknown"),
                            phone: selectedPatient.phone,
                          })
                        : t("billing:new.patient_meta_no_phone", {
                            sex:
                              selectedPatient.sex || t("common:labels.unknown"),
                          })}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedPatient(null);
                    setPatientQuery("");
                  }}
                  className="text-xs text-teal-700 font-semibold hover:underline px-3 py-1.5 rounded-lg border border-teal-200 bg-white"
                >
                  {t("billing:new.change_patient")}
                </button>
              </div>
            ) : (
              <div className="relative">
                <div className="relative flex items-center">
                  <Search className="w-4 h-4 text-slate-400 absolute start-3 pointer-events-none" />
                  <input
                    id={patientInputId}
                    type="text"
                    value={patientQuery}
                    onChange={(e) => setPatientQuery(e.target.value)}
                    onFocus={() => {
                      if (patientResults.length > 0)
                        setShowPatientDropdown(true);
                    }}
                    placeholder={t("billing:new.patient_search_placeholder")}
                    className="w-full ps-9 pe-24 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-600 bg-white placeholder:text-slate-400"
                  />
                  {isSearchingPatient && (
                    <span className="absolute end-3 text-xs text-slate-400 animate-pulse">
                      {t("billing:new.searching")}
                    </span>
                  )}
                </div>

                {/* Search Dropdown Results */}
                {showPatientDropdown && patientResults.length > 0 && (
                  <div className="absolute z-20 start-0 end-0 mt-1 max-h-56 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg">
                    {patientResults.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          setSelectedPatient(p);
                          setShowPatientDropdown(false);
                          setPatientQuery("");
                        }}
                        className="w-full text-start px-4 py-2.5 hover:bg-slate-50 border-b border-slate-100 last:border-b-0 flex items-center justify-between"
                      >
                        <div>
                          <span className="font-semibold text-slate-900 text-sm">
                            {p.name}
                          </span>
                          <span className="text-xs text-slate-500 ms-2 font-mono">
                            {p.mrn}
                          </span>
                          <div className="text-xs text-slate-400 mt-0.5">
                            {t("billing:new.patient_meta", {
                              sex: p.sex,
                              phone: p.phone || t("billing:new.not_available"),
                            })}
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-400 rtl:rotate-180" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="h-px bg-slate-200" />

          {/* 2. TESTS & PANELS SECTION */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label
                htmlFor={searchInputId}
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
              >
                {t("billing:new.tests_label")}{" "}
                <span className="text-red-600">*</span>
              </label>
              <span className="text-xs text-slate-500 font-medium">
                {items.length}{" "}
                {items.length === 1
                  ? t("billing:new.items_added_one")
                  : t("billing:new.items_added_other")}
              </span>
            </div>

            {/* Selected Rows */}
            {items.length === 0 ? (
              <div className="py-6 border-2 border-dashed border-slate-200 rounded-lg text-center text-slate-500 text-xs">
                {t("billing:new.items_empty")}
              </div>
            ) : (
              <div className="space-y-2" data-testid="selected-items-list">
                {items.map((item) => (
                  <div
                    key={item.key}
                    className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-200"
                  >
                    <div className="flex-1">
                      <div className="font-semibold text-sm text-slate-900">
                        {item.name}
                      </div>
                      <div className="text-xs font-mono text-slate-500">
                        {t("billing:new.code_label")}{" "}
                        <bdi dir="ltr">{item.code}</bdi>
                      </div>
                    </div>
                    <div className="font-mono font-semibold text-sm text-slate-900">
                      {formatMoney(item.price.toFixed(2), lang)}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveItem(item.key)}
                      title={t("billing:new.remove_item", { name: item.name })}
                      aria-label={t("billing:new.remove_item", {
                        name: item.name,
                      })}
                      className="w-8 h-8 flex items-center justify-center rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add Test from Catalog */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
              <div className="min-w-0">
                <label
                  htmlFor={searchInputId}
                  className="block text-xs font-semibold text-slate-700 mb-1.5"
                >
                  {t("billing:new.add_test_label")}
                </label>
                <div className="flex items-center gap-2 min-w-0">
                  <div className="flex-1 min-w-0">
                    <select
                      id={searchInputId}
                      value={selectedTestToAdd}
                      onChange={(e) => setSelectedTestToAdd(e.target.value)}
                      disabled={catalogLoading}
                      className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600 truncate block"
                    >
                      <option value="">
                        {t("billing:new.select_test_placeholder")}
                      </option>
                      {selectableTests.map((test) => (
                        <option key={test.id} value={test.id}>
                          {test.name} ({test.code}) -{" "}
                          {test.price
                            ? formatMoney(
                                parseFloat(test.price).toFixed(2),
                                lang,
                              )
                            : t("billing:new.price_not_configured")}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleAddTest(selectedTestToAdd)}
                    disabled={!selectedTestToAdd}
                    className="px-4 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0 whitespace-nowrap cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>{t("common:actions.add")}</span>
                  </button>
                </div>
                {panelOnlyTests.length > 0 && (
                  <p className="text-[11px] text-slate-500 mt-1.5">
                    {t("billing:new.panel_only_prefix")}{" "}
                    {panelOnlyTests
                      .map(
                        (test) =>
                          `${test.name}${
                            test.panel_codes?.length
                              ? ` (${test.panel_codes.join(", ")})`
                              : ""
                          }`,
                      )
                      .join("; ")}
                    . {t("billing:new.panel_only_suffix")}
                  </p>
                )}
              </div>

              {/* Add Panel */}
              <div className="min-w-0">
                <label
                  htmlFor={panelSelectId}
                  className="block text-xs font-semibold text-slate-700 mb-1.5"
                >
                  {t("billing:new.add_panel_label")}
                </label>
                <select
                  id={panelSelectId}
                  onChange={(e) => {
                    if (e.target.value) {
                      handleAddPanel(e.target.value);
                      e.target.value = "";
                    }
                  }}
                  disabled={catalogLoading}
                  className="w-full min-w-0 truncate text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600"
                >
                  <option value="">
                    {t("billing:new.select_panel_placeholder")}
                  </option>
                  {availablePanels.map((panel) => (
                    <option key={panel.id} value={panel.id}>
                      {panel.name} ({panel.code}) -{" "}
                      {panel.price
                        ? formatMoney(parseFloat(panel.price).toFixed(2), lang)
                        : t("billing:new.price_not_configured")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="h-px bg-slate-200" />

          {/* 3. DISCOUNTS SECTION */}
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor={discountAmountId}
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1"
                >
                  {t("billing:new.discount_amount_label")}
                </label>
                <input
                  id={discountAmountId}
                  type="number"
                  min="0"
                  step="0.01"
                  value={discountAmount}
                  onChange={(e) => setDiscountAmount(e.target.value)}
                  className="w-full text-sm font-mono border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-600"
                  placeholder={t("billing:new.amount_placeholder")}
                />
              </div>

              <div>
                <label
                  htmlFor={discountReasonId}
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1"
                >
                  {t("billing:new.discount_reason_label")}{" "}
                  {discountVal > 0 && <span className="text-red-600">*</span>}
                </label>
                <input
                  id={discountReasonId}
                  type="text"
                  value={discountReason}
                  onChange={(e) => setDiscountReason(e.target.value)}
                  placeholder={t("billing:new.discount_reason_placeholder")}
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-600"
                />
              </div>
            </div>
          </div>

          {/* 4. TOTALS SUMMARY BOX */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">
                {t("billing:new.subtotal")}
              </span>
              <span
                className="font-mono font-medium text-slate-900"
                data-testid="invoice-subtotal"
              >
                {formatMoney(subtotal.toFixed(2), lang)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">
                {t("billing:new.discount")}
              </span>
              <span className="font-mono font-medium text-slate-900">
                - {formatMoney(discountVal.toFixed(2), lang)}
              </span>
            </div>
            <div className="h-px bg-slate-200 my-1" />
            <div className="flex items-baseline justify-between pt-1">
              <span className="text-base font-bold text-slate-900">
                {t("common:labels.total")}
              </span>
              <span
                className="text-2xl font-bold font-mono text-slate-900"
                data-testid="invoice-total"
              >
                {formatMoney(netTotal.toFixed(2), lang)}
              </span>
            </div>
          </div>

          {/* 5. FOOTER CONTROLS */}
          <div className="pt-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="bg-teal-700 hover:bg-teal-800 text-white font-medium text-sm px-6 py-2.5 rounded-lg shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-teal-600 disabled:opacity-50 flex items-center gap-2 cursor-pointer"
            >
              {submitting ? (
                <>
                  <span className="inline-block animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                  <span>{t("billing:new.creating")}</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{t("billing:new.create")}</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 font-medium text-sm px-5 py-2.5 rounded-lg transition-colors cursor-pointer"
            >
              {t("common:actions.cancel")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
