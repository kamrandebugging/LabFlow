import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Loader2,
  ArrowLeft,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { useDialogFocus } from "../../lib/dialogFocus";
import { FadeValue } from "../../components/ui/FadeValue";
import styles from "./PatientForm.module.css";
import { DuplicatePatientError, patientService } from "./patientService";
import { partnersService } from "../partners/partnersService";
import type { ReferralPartner } from "../partners/types";
import { VeylaDrawer as PatientRegisterDrawer } from "./VeylaDrawer";
import { calculatePatientAge } from "./patientAge";
import { PatientRegistrationSuccessModal } from "./components/PatientRegistrationSuccessModal";
import type {
  PatientCandidate,
  PatientCreateInput,
  PatientSummary,
} from "./types";

interface RegisterPatientScreenProps {
  branchId?: string;
  onSuccess?: (patient: PatientSummary) => void;
  onCancel?: () => void;
  onCreateInvoice?: (patientId: string) => void;
  onViewProfile?: (patientId: string) => void;
  service?: typeof patientService;
  /**
   * "page" renders the standalone registration route. "drawer" renders the
   * form inside the Veyla side panel, without the page chrome.
   */
  variant?: "page" | "drawer";
}

const FORM_ID = "patientRegistrationForm";

/**
 * Live phone normalisation. Mirrors the backend `normalize_phone` helper:
 * spaces, dashes, brackets and a leading plus are dropped, and a Pakistani
 * international prefix (0092 / 92) becomes the local 03xx form. The value
 * submitted to the API is unchanged.
 */
function normalisePhoneInput(value: string): string {
  const cleaned = value.replace(/[\s\-()+]/g, "");
  if (cleaned.startsWith("0092") && cleaned.length === 14) {
    return "0" + cleaned.slice(4);
  }
  if (cleaned.startsWith("92") && cleaned.length === 12) {
    return "0" + cleaned.slice(2);
  }
  return cleaned;
}

export const RegisterPatientScreen: React.FC<RegisterPatientScreenProps> = ({
  branchId = "00000000-0000-0000-0000-000000000001",
  onSuccess,
  onCancel,
  onCreateInvoice,
  onViewProfile,
  service = patientService,
  variant = "page",
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [sex, setSex] = useState<"M" | "F">("M");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [consentReports, setConsentReports] = useState(false);
  // Referral link: walk-in by default, otherwise the existing partner master.
  const [partners, setPartners] = useState<ReferralPartner[]>([]);
  const [referralPartnerId, setReferralPartnerId] = useState<string>("");

  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<
    PatientCandidate[] | null
  >(null);

  // Per-field validation state, surfaced on blur and re-checked on change.
  const [touched, setTouched] = useState({ name: false, phone: false });
  const [showSummary, setShowSummary] = useState(false);

  // Inline success state (drawer variant only).
  const [savedPatient, setSavedPatient] = useState<PatientSummary | null>(null);

  const alertRef = useRef<HTMLDivElement | null>(null);
  const summaryRef = useRef<HTMLDivElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);
  const phoneInputRef = useRef<HTMLInputElement | null>(null);
  const successRef = useRef<HTMLDivElement | null>(null);

  const duplicatePanelRef = useDialogFocus<HTMLDivElement>(
    duplicateCandidates !== null,
    () => setDuplicateCandidates(null),
  );

  // Keep the shared alert ref and the dialog panel ref pointing at the same
  // node so the existing "move focus to the alert" behaviour also covers the
  // duplicate-patient dialog.
  const setDuplicatePanel = (node: HTMLDivElement | null) => {
    (
      duplicatePanelRef as unknown as MutableRefObject<HTMLDivElement | null>
    ).current = node;
    alertRef.current = node;
  };

  // Move keyboard focus to a freshly rendered alert so a failed submit is
  // announced and visible instead of leaving focus on the submit button.
  useEffect(() => {
    if (formError || (duplicateCandidates?.length ?? 0) > 0) {
      alertRef.current?.focus();
    }
  }, [formError, duplicateCandidates]);

  // Move focus to the error summary once a submit has been rejected.
  useEffect(() => {
    if (showSummary) summaryRef.current?.focus();
  }, [showSummary]);

  // Announce the inline success state.
  useEffect(() => {
    if (savedPatient) successRef.current?.focus();
  }, [savedPatient]);

  // Referral partners for the "Referred by" picker (Walk-in when empty).
  useEffect(() => {
    let active = true;
    partnersService
      .getPartners()
      .then((rows) => {
        if (active) setPartners(rows.filter((p) => p.is_active));
      })
      .catch(() => {
        // Degrade to Walk-in only; the server still validates the id.
      });
    return () => {
      active = false;
    };
  }, []);

  const nameError = useMemo(() => {
    const trimmed = name.trim();
    if (trimmed.length < 2 || trimmed.length > 120) {
      return t("patients:register.validation.name");
    }
    return null;
  }, [name, t]);

  const phoneError = useMemo(() => {
    if (!/^\d{10,15}$/.test(normalisePhoneInput(phone))) {
      return t("patients:validation.phone");
    }
    return null;
  }, [phone, t]);

  const visibleErrors = useMemo(() => {
    const next: { name?: string; phone?: string } = {};
    if (touched.name && nameError) next.name = nameError;
    if (touched.phone && phoneError) next.phone = phoneError;
    return next;
  }, [touched, nameError, phoneError]);

  const summaryItems = useMemo(() => {
    const items: Array<{ id: string; message: string }> = [];
    if (nameError) items.push({ id: "fullName", message: nameError });
    if (phoneError) items.push({ id: "phoneNumber", message: phoneError });
    return items;
  }, [nameError, phoneError]);

  const focusField = (id: string) => {
    if (id === "fullName") nameInputRef.current?.focus();
    if (id === "phoneNumber") phoneInputRef.current?.focus();
  };

  const resetForm = () => {
    setName("");
    setPhone("");
    setSex("M");
    setDateOfBirth("");
    setWhatsappNumber("");
    setConsentReports(false);
    setTouched({ name: false, phone: false });
    setShowSummary(false);
    setFormError(null);
    setSavedPatient(null);
  };

  const handleSubmit = async (confirmDuplicate = false) => {
    setFormError(null);
    setShowSummary(false);

    // Validation — the same rules as before, now surfaced per field.
    const trimmedName = name.trim();
    const cleanPhone = normalisePhoneInput(phone);
    if (
      trimmedName.length < 2 ||
      trimmedName.length > 120 ||
      !/^\d{10,15}$/.test(cleanPhone)
    ) {
      setTouched({ name: true, phone: true });
      setShowSummary(true);
      return;
    }

    setIsLoading(true);
    try {
      const payload: PatientCreateInput = {
        name: trimmedName,
        phone: cleanPhone,
        sex,
        date_of_birth: dateOfBirth || null,
        branch_id: branchId,
        referral_partner_id: referralPartnerId || null,
        whatsapp_number: whatsappNumber
          ? normalisePhoneInput(whatsappNumber)
          : undefined,
        consent_reports: consentReports,
        confirm_duplicate: confirmDuplicate,
      };

      const result = await service.createPatient(payload);
      setDuplicateCandidates(null);
      setSavedPatient(result);
      onSuccess?.(result);
    } catch (err: unknown) {
      if (err instanceof DuplicatePatientError) {
        setDuplicateCandidates(err.candidates);
      } else {
        setFormError(
          err && typeof err === "object" && ("code" in err || "status" in err)
            ? messageForError(err, t)
            : t("patients:register.errors.failed"),
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  const age = calculatePatientAge(dateOfBirth || null, null);

  /* ------------------------------------------------------------- fields -- */

  const errorSummary =
    showSummary && summaryItems.length > 0 ? (
      <div
        ref={summaryRef}
        role="alert"
        tabIndex={-1}
        aria-labelledby="patient-register-error-summary"
        className={styles.errorSummary}
      >
        <p
          id="patient-register-error-summary"
          className={styles.errorSummaryTitle}
        >
          {t("common:errors.validation")}
        </p>
        <ul className={styles.errorSummaryList}>
          {summaryItems.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => focusField(item.id)}
                className={styles.errorSummaryLink}
              >
                {item.message}
              </button>
            </li>
          ))}
        </ul>
      </div>
    ) : null;

  const generalAlert = formError ? (
    <div role="alert" ref={alertRef} tabIndex={-1} className={styles.alert}>
      <AlertCircle className={styles.alertIcon} aria-hidden="true" />
      <span>{formError}</span>
    </div>
  ) : null;

  const successPanel = savedPatient ? (
    <div
      ref={successRef}
      tabIndex={-1}
      role="status"
      className={styles.success}
    >
      <p className={styles.successTitle}>{t("patients:details.registered")}</p>
      <p className={styles.successText}>
        {t("patients:mrn")}:{" "}
        <span className={styles.successMrn} dir="ltr">
          {savedPatient.mrn}
        </span>
      </p>
      <button type="button" onClick={resetForm} className={styles.chipButton}>
        {t("patients:list.new_patient")}
      </button>
    </div>
  ) : null;

  const demographicsColumn = (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>{t("patients:demographics")}</h2>
      </div>

      {/* Full Name */}
      <div className={styles.field}>
        <label htmlFor="fullName" className={styles.label}>
          {t("patients:field_full_name")}{" "}
          <span className={styles.required}>*</span>
        </label>
        <input
          id="fullName"
          name="fullName"
          type="text"
          required
          ref={nameInputRef}
          readOnly={isLoading}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => setTouched((prev) => ({ ...prev, name: true }))}
          placeholder={t("patients:register.full_name_placeholder")}
          aria-invalid={visibleErrors.name ? true : undefined}
          aria-describedby={visibleErrors.name ? "fullName-error" : undefined}
          className={styles.input}
        />
        {visibleErrors.name ? (
          <p id="fullName-error" className={styles.fieldError}>
            <AlertCircle className={styles.fieldErrorIcon} aria-hidden="true" />
            <span>{visibleErrors.name}</span>
          </p>
        ) : null}
      </div>

      {/* Phone & Sex */}
      <div className={styles.field}>
        <div className={styles.labelRow}>
          <label htmlFor="phoneNumber" className={styles.label}>
            {t("common:labels.phone")}{" "}
            <span className={styles.required}>*</span>
          </label>
          <span className={styles.hint}>+92</span>
        </div>
        <input
          id="phoneNumber"
          name="phoneNumber"
          type="tel"
          dir="ltr"
          required
          ref={phoneInputRef}
          readOnly={isLoading}
          value={phone}
          onChange={(e) => setPhone(normalisePhoneInput(e.target.value))}
          onBlur={() => setTouched((prev) => ({ ...prev, phone: true }))}
          placeholder={t("patients:register.phone_placeholder")}
          aria-invalid={visibleErrors.phone ? true : undefined}
          aria-describedby={
            visibleErrors.phone ? "phoneNumber-error" : undefined
          }
          className={styles.input}
        />
        {visibleErrors.phone ? (
          <p id="phoneNumber-error" className={styles.fieldError}>
            <AlertCircle className={styles.fieldErrorIcon} aria-hidden="true" />
            <span>{visibleErrors.phone}</span>
          </p>
        ) : (
          <p className={styles.hint}>{t("patients:register.phone_hint")}</p>
        )}
      </div>

      <div className={styles.field}>
        <span className={styles.label} id="sexLabel">
          {t("common:labels.sex")} <span className={styles.required}>*</span>
        </span>
        <div
          role="radiogroup"
          aria-labelledby="sexLabel"
          className={styles.segmented}
        >
          <label
            className={`${styles.segmentedOption} ${
              sex === "M" ? styles.segmentedOptionSelected : ""
            }`}
          >
            <input
              type="radio"
              name="sex"
              value="M"
              checked={sex === "M"}
              aria-checked={sex === "M"}
              readOnly={isLoading}
              onChange={() => {
                if (!isLoading) setSex("M");
              }}
              className={styles.segmentedInput}
            />
            <span className={styles.segmentedDot} aria-hidden="true" />
            <span>{t("patients:sex.male")}</span>
          </label>
          <label
            className={`${styles.segmentedOption} ${
              sex === "F" ? styles.segmentedOptionSelected : ""
            }`}
          >
            <input
              type="radio"
              name="sex"
              value="F"
              checked={sex === "F"}
              aria-checked={sex === "F"}
              readOnly={isLoading}
              onChange={() => {
                if (!isLoading) setSex("F");
              }}
              className={styles.segmentedInput}
            />
            <span className={styles.segmentedDot} aria-hidden="true" />
            <span>{t("patients:sex.female")}</span>
          </label>
        </div>
      </div>

      {/* Date of birth */}
      <div className={styles.field}>
        <label htmlFor="dateOfBirth" className={styles.label}>
          {t("common:labels.dob")}
        </label>
        <input
          id="dateOfBirth"
          name="dateOfBirth"
          type="date"
          readOnly={isLoading}
          value={dateOfBirth}
          onChange={(e) => setDateOfBirth(e.target.value)}
          className={`${styles.input} ${styles.inputDate}`}
        />
        <p className={styles.hint}>{t("patients:register.dob_hint")}</p>
      </div>

      {/* Referred by */}
      <div className={styles.field}>
        <label htmlFor="referralPartner" className={styles.label}>
          {t("patients:register.referred_by")}
        </label>
        <select
          id="referralPartner"
          value={referralPartnerId}
          onChange={(e) => setReferralPartnerId(e.target.value)}
          className={styles.input}
          disabled={isLoading}
        >
          <option value="">{t("patients:register.walk_in")}</option>
          {partners.map((partner) => (
            <option key={partner.id} value={partner.id}>
              {partner.name}
            </option>
          ))}
        </select>
      </div>
    </section>
  );

  const deliveryColumn = (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>
          {t("patients:register.section_delivery")}
        </h2>
      </div>

      {/* WhatsApp */}
      <div className={styles.field}>
        <div className={styles.labelRow}>
          <label htmlFor="whatsappNumber" className={styles.label}>
            {t("patients:register.whatsapp")}
          </label>
          <button
            type="button"
            onClick={() => setWhatsappNumber(phone)}
            disabled={!phone.trim() || isLoading}
            aria-disabled={!phone.trim() || isLoading}
            className={styles.chipButton}
          >
            Use primary phone
          </button>
        </div>
        <input
          id="whatsappNumber"
          name="whatsappNumber"
          type="tel"
          dir="ltr"
          readOnly={isLoading}
          value={whatsappNumber}
          onChange={(e) =>
            setWhatsappNumber(normalisePhoneInput(e.target.value))
          }
          placeholder={t("patients:register.whatsapp_placeholder")}
          className={styles.input}
        />
        <p className={styles.hint}>{t("patients:register.whatsapp_hint")}</p>
      </div>

      {/* Consent checkbox */}
      <div>
        <label className={styles.checkboxRow}>
          <input
            id="consentReports"
            name="consentReports"
            type="checkbox"
            checked={consentReports}
            readOnly={isLoading}
            onChange={(e) => {
              if (!isLoading) setConsentReports(e.target.checked);
            }}
            className={styles.checkbox}
          />
          <span className={styles.checkboxText}>
            {t("patients:register.consent")}
          </span>
        </label>
      </div>

      {/* Live preview */}
      <div className={styles.preview}>
        <p className={styles.previewTitle}>
          {t("patients:details.consent_title")}
        </p>
        <dl className={styles.previewRows}>
          <div className={styles.previewRow}>
            <dt className={styles.previewLabel}>
              {t("patients:field_full_name")}
            </dt>
            <dd className={styles.previewValue}>
              <FadeValue value={name.trim() || "—"} />
            </dd>
          </div>
          <div className={styles.previewRow}>
            <dt className={styles.previewLabel}>{t("common:labels.age")}</dt>
            <dd className={styles.previewValue}>
              <FadeValue
                value={
                  age !== null
                    ? t("patients:list.age_years", { age })
                    : t("common:labels.not_recorded")
                }
              />
            </dd>
          </div>
          <div className={styles.previewRow}>
            <dt className={styles.previewLabel}>{t("common:labels.phone")}</dt>
            <dd className={`${styles.previewValue} ${styles.previewValueMono}`}>
              <FadeValue value={phone || "—"} />
            </dd>
          </div>
          <div className={styles.previewRow}>
            <dt className={styles.previewLabel}>{t("patients:mrn")}</dt>
            <dd className={`${styles.previewValue} ${styles.previewValueMono}`}>
              <FadeValue value={savedPatient?.mrn || "—"} />
            </dd>
          </div>
          <div className={`${styles.previewRow} ${styles.previewRowWide}`}>
            <dt className={styles.previewLabel}>
              {t("patients:details.digital_delivery")}
            </dt>
            <dd className={styles.previewValue}>
              <span
                className={`${styles.previewChip} ${
                  consentReports ? "" : styles.previewChipOff
                }`}
              >
                {consentReports ? (
                  <ShieldCheck
                    className={styles.previewChipIcon}
                    aria-hidden="true"
                  />
                ) : (
                  <ShieldX
                    className={styles.previewChipIcon}
                    aria-hidden="true"
                  />
                )}
                {consentReports
                  ? t("patients:details.consent_granted")
                  : t("patients:details.consent_none")}
              </span>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );

  const footerActions = (
    <>
      <button
        type="button"
        onClick={onCancel}
        disabled={isLoading}
        className={styles.cancelButton}
      >
        {t("common:actions.cancel")}
      </button>
      <button
        type="submit"
        form={variant === "drawer" ? FORM_ID : undefined}
        disabled={isLoading}
        className={styles.primaryButton}
      >
        {isLoading ? (
          <Loader2 className={`${styles.buttonIcon} ${styles.spin}`} />
        ) : (
          <Check className={styles.buttonIcon} aria-hidden="true" />
        )}
        <span>
          {isLoading
            ? t("patients:register.registering")
            : t("patients:register.title")}
        </span>
      </button>
    </>
  );

  const formColumns = (
    <div className={styles.formColumns}>
      {demographicsColumn}
      {deliveryColumn}
    </div>
  );

  const duplicateDialog =
    duplicateCandidates && duplicateCandidates.length > 0
      ? createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="duplicate-patient-title"
            className={`${styles.drawerScrim} veyla-modal-scrim`}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setDuplicateCandidates(null);
              }
            }}
          >
            <div
              ref={setDuplicatePanel}
              tabIndex={-1}
              data-testid="duplicate-warning-banner"
              className={`${styles.card} veyla-modal`}
            >
              <div className={styles.alertHead}>
                <AlertTriangle
                  className={styles.alertIcon}
                  aria-hidden="true"
                />
                <h2 id="duplicate-patient-title" className={styles.modalTitle}>
                  {t("patients:register.duplicate.title")}
                </h2>
              </div>
              <p className={styles.alertBody}>
                {t("patients:register.duplicate.body")}
              </p>

              <div className={styles.candidateList}>
                {duplicateCandidates.map((c) => (
                  <div key={c.id} className={styles.candidateRow}>
                    <div>
                      <span className={styles.candidateName}>{c.name}</span>
                      <span className={styles.candidateMeta}>
                        (
                        {c.sex === "M"
                          ? t("patients:sex.male")
                          : t("patients:sex.female")}
                        )
                      </span>
                      {c.year_of_birth && (
                        <span className={styles.candidateMeta}>
                          ·{" "}
                          {t("patients:register.duplicate.yob", {
                            year: c.year_of_birth,
                          })}
                        </span>
                      )}
                    </div>
                    <span dir="ltr" className={styles.candidateMrn}>
                      {c.mrn}
                    </span>
                  </div>
                ))}
              </div>

              <div className={styles.alertActions}>
                <button
                  type="button"
                  onClick={() => setDuplicateCandidates(null)}
                  className={styles.cancelButton}
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="button"
                  onClick={() => handleSubmit(true)}
                  disabled={isLoading}
                  className={styles.warnButton}
                >
                  {isLoading && (
                    <Loader2
                      className={`${styles.buttonIcon} ${styles.spin}`}
                    />
                  )}
                  <span>{t("patients:register.duplicate.confirm")}</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )
      : null;

  /* -------------------------------------------------------------- drawer -- */

  if (variant === "drawer") {
    return (
      <>
        <PatientRegisterDrawer
          open
          onClose={() => onCancel?.()}
          title={t("patients:register.title")}
          subtitle={t("patients:register.iso_badge")}
          suspendFocusTrap={duplicateCandidates !== null}
          footer={footerActions}
        >
          {errorSummary}
          {generalAlert}
          {successPanel}
          {savedPatient ? null : (
            <form
              id={FORM_ID}
              aria-busy={isLoading}
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                handleSubmit(false);
              }}
              onKeyDown={(e) => {
                // IME guard: an Enter that ends an in-progress composition
                // must not submit the form (Urdu keyboard).
                if (
                  e.nativeEvent.isComposing ||
                  e.nativeEvent.keyCode === 229
                ) {
                  e.preventDefault();
                }
              }}
              className={styles.form}
            >
              {formColumns}
            </form>
          )}
        </PatientRegisterDrawer>

        {duplicateDialog}

        {savedPatient && (
          <PatientRegistrationSuccessModal
            isOpen={Boolean(savedPatient)}
            patient={savedPatient}
            onCreateInvoice={(patientId) => {
              if (onCreateInvoice) {
                onCreateInvoice(patientId);
              } else if (typeof window !== "undefined") {
                window.location.assign(
                  `/invoices?createForPatientId=${patientId}`,
                );
              }
            }}
            onViewProfile={(patientId) => {
              if (onViewProfile) {
                onViewProfile(patientId);
              } else if (typeof window !== "undefined") {
                window.location.assign(`/patients/${patientId}`);
              }
            }}
            onRegisterAnother={() => {
              resetForm();
              setSavedPatient(null);
            }}
            onClose={() => {
              setSavedPatient(null);
              onCancel?.();
            }}
          />
        )}
      </>
    );
  }

  /* --------------------------------------------------------------- page --- */

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Breadcrumbs & Header */}
        <div>
          <nav
            aria-label={t("patients:breadcrumb_aria")}
            style={{ marginBottom: "2px" }}
          >
            <ol className={styles.breadcrumb}>
              <li>
                <button
                  type="button"
                  onClick={onCancel}
                  className={styles.breadcrumbLink}
                >
                  <ArrowLeft className={styles.crumbIcon} aria-hidden="true" />
                  <span>{t("common:nav.patients")}</span>
                </button>
              </li>
              <li className={styles.crumbSep}>/</li>
              <li className={styles.crumbCurrent}>
                {t("patients:register.breadcrumb_new")}
              </li>
            </ol>
          </nav>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{t("patients:register.title")}</h1>
            <span className={styles.isoBadge}>
              {t("patients:register.iso_badge")}
            </span>
          </div>
        </div>

        {errorSummary}
        {generalAlert}
        {successPanel}

        {/* Registration Form Card */}
        <div className={styles.card}>
          <form
            id={FORM_ID}
            aria-busy={isLoading}
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit(false);
            }}
            onKeyDown={(e) => {
              // IME guard: an Enter that ends an in-progress composition
              // must not submit the form (Urdu keyboard).
              if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) {
                e.preventDefault();
              }
            }}
            className={styles.form}
          >
            {formColumns}
            <div className={styles.footer}>{footerActions}</div>
          </form>
        </div>
      </div>

      {duplicateDialog}

      {savedPatient && (
        <PatientRegistrationSuccessModal
          isOpen={Boolean(savedPatient)}
          patient={savedPatient}
          onCreateInvoice={(patientId) => {
            if (onCreateInvoice) {
              onCreateInvoice(patientId);
            } else if (typeof window !== "undefined") {
              window.location.assign(
                `/invoices?createForPatientId=${patientId}`,
              );
            }
          }}
          onViewProfile={(patientId) => {
            if (onViewProfile) {
              onViewProfile(patientId);
            } else if (typeof window !== "undefined") {
              window.location.assign(`/patients/${patientId}`);
            }
          }}
          onRegisterAnother={() => {
            resetForm();
            setSavedPatient(null);
          }}
          onClose={() => {
            setSavedPatient(null);
            onCancel?.();
          }}
        />
      )}
    </div>
  );
};
export default RegisterPatientScreen;
