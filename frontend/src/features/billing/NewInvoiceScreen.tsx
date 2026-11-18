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
import { partnersService } from "../partners/partnersService";
import type { ReferralPartner } from "../partners/types";
import { billingService } from "./billingService";
import { SearchSelect } from "./SearchSelect";
import { formatMoney } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import styles from "./NewInvoiceScreen.module.css";
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

  // Referral: the patient's partner carries onto the invoice and can be changed.
  const [partners, setPartners] = useState<ReferralPartner[]>([]);
  const [referralPartnerId, setReferralPartnerId] = useState<string>("");

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

  // Referral partners: the patient's partner carries onto the invoice, and
  // the operator can change it before the invoice is created.
  useEffect(() => {
    let active = true;
    partnersService
      .getPartners()
      .then((rows) => {
        if (active) setPartners(rows.filter((p) => p.is_active));
      })
      .catch(() => {
        // The picker degrades to Walk-in only; the server still validates.
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setReferralPartnerId(selectedPatient?.referral_partner_id ?? "");
  }, [selectedPatient]);

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
    const partnerName = partners.find((p) => p.id === referralPartnerId)?.name;
    if (
      partnerName &&
      discountVal > 0 &&
      !discountReason.toLowerCase().includes(partnerName.trim().toLowerCase())
    ) {
      setErrorMessage(
        t("billing:new.error_referral_reason", { name: partnerName }),
      );
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
        referral_partner_id: referralPartnerId || null,
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
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Breadcrumb & Page Header */}
        <div>
          <nav aria-label={t("billing:new.breadcrumb_aria")}>
            <div className={styles.breadcrumb}>
              <button
                type="button"
                onClick={onCancel}
                className={styles.crumbBtn}
              >
                {t("billing:shared.invoices")}
              </button>
              <span className={styles.crumbSep}>/</span>
              <span className={styles.crumbCurrent}>
                {t("billing:new.breadcrumb_new")}
              </span>
            </div>
          </nav>
          <div className={styles.titleRow}>
            <div>
              <h1 className={styles.title}>{t("billing:new.title")}</h1>
              <p className={styles.subtitle}>{t("billing:new.subtitle")}</p>
            </div>
            <div className={styles.draftPill}>
              <FileText className={styles.draftIcon} aria-hidden="true" />
              <span>{t("billing:new.draft", { id: "INV-NEW" })}</span>
            </div>
          </div>
        </div>

        {/* Error Banner */}
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

        {/* Main Card */}
        <div className={styles.card}>
          <form onSubmit={handleSubmit} className={styles.form}>
            {/* 1. PATIENT SECTION */}
            <div className={styles.section}>
              <div className={styles.labelRow}>
                <label htmlFor={patientInputId} className={styles.label}>
                  {t("billing:new.patient_label")}{" "}
                  <span className={styles.required}>*</span>
                </label>
                {onRegisterPatient && !selectedPatient && (
                  <button
                    type="button"
                    onClick={onRegisterPatient}
                    className={styles.linkButton}
                  >
                    + {t("billing:new.register_patient")}
                  </button>
                )}
              </div>

              {selectedPatient ? (
                <div className={styles.patientSelected}>
                  <div className={styles.patientIdentity}>
                    <div className={styles.avatar} aria-hidden="true">
                      {selectedPatient.name?.substring(0, 2).toUpperCase() ||
                        t("billing:new.patient_initials")}
                    </div>
                    <div>
                      <div className={styles.patientName}>
                        {selectedPatient.name} ·{" "}
                        <span className={styles.patientMrn}>
                          <bdi dir="ltr">{selectedPatient.mrn}</bdi>
                        </span>
                      </div>
                      <div className={styles.patientMeta}>
                        {selectedPatient.phone
                          ? t("billing:new.patient_meta", {
                              sex:
                                selectedPatient.sex ||
                                t("common:labels.unknown"),
                              phone: selectedPatient.phone,
                            })
                          : t("billing:new.patient_meta_no_phone", {
                              sex:
                                selectedPatient.sex ||
                                t("common:labels.unknown"),
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
                    className={styles.cancelButton}
                  >
                    {t("billing:new.change_patient")}
                  </button>
                </div>
              ) : (
                <div className={styles.searchWrap}>
                  <div className={styles.searchField}>
                    <Search className={styles.searchIcon} aria-hidden="true" />
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
                      className={styles.searchInput}
                    />
                    {isSearchingPatient && (
                      <span
                        className={`${styles.searching} ${styles.pulseText}`}
                      >
                        {t("billing:new.searching")}
                      </span>
                    )}
                  </div>

                  {/* Search Dropdown Results */}
                  {showPatientDropdown &&
                    !isSearchingPatient &&
                    (patientResults.length > 0 ||
                      patientQuery.trim().length >= 2) && (
                      <div className={styles.dropdown}>
                        {patientResults.length > 0 ? (
                          patientResults.map((p) => (
                            <button
                              key={p.id}
                              type="button"
                              onClick={() => {
                                setSelectedPatient(p);
                                setShowPatientDropdown(false);
                                setPatientQuery("");
                              }}
                              className={styles.dropdownItem}
                            >
                              <div>
                                <span className={styles.dropdownName}>
                                  {p.name}
                                </span>
                                <span className={styles.dropdownMrn} dir="ltr">
                                  {p.mrn}
                                </span>
                                <div className={styles.dropdownMeta}>
                                  {t("billing:new.patient_meta", {
                                    sex: p.sex,
                                    phone:
                                      p.phone || t("billing:new.not_available"),
                                  })}
                                </div>
                              </div>
                              <ArrowRight
                                className={styles.dropdownArrow}
                                aria-hidden="true"
                              />
                            </button>
                          ))
                        ) : (
                          // Zero results: one non-selectable status row so the
                          // user can tell "no match" from "still searching".
                          <div className={styles.dropdownStatus} role="status">
                            <span>
                              No patients found for '{patientQuery.trim()}'.
                            </span>
                            {onRegisterPatient && (
                              <button
                                type="button"
                                onClick={onRegisterPatient}
                                className={styles.dropdownStatusAction}
                              >
                                + Register new patient
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                </div>
              )}
            </div>

            <div className={styles.divider} />

            {/* 2. TESTS & PANELS SECTION */}
            <div className={styles.section}>
              <div className={styles.labelRow}>
                <label htmlFor={searchInputId} className={styles.label}>
                  {t("billing:new.tests_label")}{" "}
                  <span className={styles.required}>*</span>
                </label>
                <span className={styles.countPill}>
                  {items.length}{" "}
                  {items.length === 1
                    ? t("billing:new.items_added_one")
                    : t("billing:new.items_added_other")}
                </span>
              </div>

              {/* Selected Rows */}
              {items.length === 0 ? (
                <div className={styles.emptyPanel}>
                  {t("billing:new.items_empty")}
                </div>
              ) : (
                <div
                  className={styles.itemsList}
                  data-testid="selected-items-list"
                >
                  {items.map((item) => (
                    <div key={item.key} className={styles.itemRow}>
                      <div className={styles.itemBody}>
                        <div className={styles.itemName}>{item.name}</div>
                        <div className={styles.itemCode}>
                          {t("billing:new.code_label")}{" "}
                          <bdi dir="ltr">{item.code}</bdi>
                        </div>
                      </div>
                      <div className={styles.itemPrice} dir="ltr">
                        {formatMoney(item.price.toFixed(2), lang)}
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveItem(item.key)}
                        title={t("billing:new.remove_item", {
                          name: item.name,
                        })}
                        aria-label={t("billing:new.remove_item", {
                          name: item.name,
                        })}
                        className={styles.removeButton}
                      >
                        <X className={styles.icon} aria-hidden="true" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add Test from Catalog */}
              <div className={styles.grid2}>
                <div className={styles.field}>
                  <label htmlFor={searchInputId} className={styles.fieldLabel}>
                    {t("billing:new.add_test_label")}
                  </label>
                  <div className={styles.addRow}>
                    <SearchSelect
                      inputId={searchInputId}
                      ariaLabel={t("billing:new.select_test_placeholder")}
                      placeholder={t("billing:new.select_test_placeholder")}
                      disabled={catalogLoading}
                      className={styles.select}
                      inputClassName={styles.select}
                      options={selectableTests.map((test) => ({
                        id: test.id,
                        label: `${test.name} (${test.code})`,
                        meta: test.price
                          ? formatMoney(parseFloat(test.price).toFixed(2), lang)
                          : "",
                      }))}
                      onSelect={(id) => setSelectedTestToAdd(id)}
                    />
                    <button
                      type="button"
                      onClick={() => handleAddTest(selectedTestToAdd)}
                      disabled={!selectedTestToAdd}
                      className={styles.addButton}
                    >
                      <Plus className={styles.icon} aria-hidden="true" />
                      <span>{t("common:actions.add")}</span>
                    </button>
                  </div>
                  {panelOnlyTests.length > 0 && (
                    <p className={styles.hint}>
                      {t("billing:new.panel_only_suffix")}
                    </p>
                  )}
                </div>

                {/* Add Panel */}
                <div className={styles.field}>
                  <label htmlFor={panelSelectId} className={styles.fieldLabel}>
                    {t("billing:new.add_panel_label")}
                  </label>
                  <SearchSelect
                    inputId={panelSelectId}
                    ariaLabel={t("billing:new.select_panel_placeholder")}
                    placeholder={t("billing:new.select_panel_placeholder")}
                    disabled={catalogLoading}
                    className={styles.select}
                    inputClassName={styles.select}
                    options={availablePanels.map((panel) => ({
                      id: panel.id,
                      label: `${panel.name} (${panel.code})`,
                      meta: panel.price
                        ? formatMoney(parseFloat(panel.price).toFixed(2), lang)
                        : "",
                    }))}
                    onSelect={(id) => handleAddPanel(id)}
                  />
                </div>
              </div>
            </div>

            <div className={styles.divider} />

            {/* 3. DISCOUNTS SECTION */}
            <div className={styles.section}>
              <div className={styles.field} style={{ marginBottom: 12 }}>
                <label htmlFor="referralPartner" className={styles.label}>
                  {t("billing:new.referred_by")}
                </label>
                <select
                  id="referralPartner"
                  value={referralPartnerId}
                  onChange={(e) => setReferralPartnerId(e.target.value)}
                  className={styles.input}
                >
                  <option value="">{t("billing:new.walk_in")}</option>
                  {partners.map((partner) => (
                    <option key={partner.id} value={partner.id}>
                      {partner.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className={styles.grid2}>
                <div className={styles.field}>
                  <label htmlFor={discountAmountId} className={styles.label}>
                    {t("billing:new.discount_amount_label")}
                  </label>
                  <div className={styles.inputWithPrefix}>
                    <span className={styles.inputPrefix} aria-hidden="true">
                      PKR
                    </span>
                    <input
                      id={discountAmountId}
                      type="number"
                      min="0"
                      step="0.01"
                      value={discountAmount}
                      onChange={(e) => setDiscountAmount(e.target.value)}
                      className={`${styles.input} ${styles.inputPrefixed}`}
                      placeholder={t("billing:new.amount_placeholder")}
                    />
                  </div>
                  <p className={styles.maxHelper}>
                    Max: {formatMoney(subtotal.toFixed(2), lang)}
                  </p>
                </div>

                <div className={styles.field}>
                  <label htmlFor={discountReasonId} className={styles.label}>
                    {t("billing:new.discount_reason_label")}{" "}
                    {discountVal > 0 && (
                      <span className={styles.required}>*</span>
                    )}
                  </label>
                  <input
                    id={discountReasonId}
                    type="text"
                    value={discountReason}
                    onChange={(e) => setDiscountReason(e.target.value)}
                    placeholder={t("billing:new.discount_reason_placeholder")}
                    className={styles.input}
                  />
                </div>
              </div>
            </div>

            {/* 4. TOTALS SUMMARY BOX */}
            <div className={styles.totals}>
              <div className={styles.totalRow}>
                <span>{t("billing:new.subtotal")}</span>
                <span
                  className={styles.totalValue}
                  data-testid="invoice-subtotal"
                  dir="ltr"
                >
                  {formatMoney(subtotal.toFixed(2), lang)}
                </span>
              </div>
              <div className={styles.totalRow}>
                <span>{t("billing:new.discount")}</span>
                <span className={styles.totalValue} dir="ltr">
                  - {formatMoney(discountVal.toFixed(2), lang)}
                </span>
              </div>
              <div className={styles.grandRow}>
                <span className={styles.grandLabel}>
                  {t("common:labels.total")}
                </span>
                <span
                  className={styles.grandValue}
                  data-testid="invoice-total"
                  dir="ltr"
                >
                  {formatMoney(netTotal.toFixed(2), lang)}
                </span>
              </div>
            </div>

            {/* 5. FOOTER CONTROLS — secondary first, primary on the inline-end. */}
            <div className={styles.footer}>
              <button
                type="button"
                onClick={onCancel}
                disabled={submitting}
                className={styles.cancelButton}
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="submit"
                disabled={submitting}
                className={styles.primaryButton}
              >
                {submitting ? (
                  <>
                    <span className={styles.spinner} aria-hidden="true" />
                    <span>{t("billing:new.creating")}</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2
                      className={styles.buttonIcon}
                      aria-hidden="true"
                    />
                    <span>{t("billing:new.create")}</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
