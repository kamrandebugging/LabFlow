import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Loader2,
  ArrowLeft,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import styles from "./PatientForm.module.css";
import { DuplicatePatientError, patientService } from "./patientService";
import type {
  PatientCandidate,
  PatientCreateInput,
  PatientSummary,
} from "./types";

interface RegisterPatientScreenProps {
  branchId?: string;
  onSuccess?: (patient: PatientSummary) => void;
  onCancel?: () => void;
  service?: typeof patientService;
}

export const RegisterPatientScreen: React.FC<RegisterPatientScreenProps> = ({
  branchId = "00000000-0000-0000-0000-000000000001",
  onSuccess,
  onCancel,
  service = patientService,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [sex, setSex] = useState<"M" | "F">("M");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [consentReports, setConsentReports] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<
    PatientCandidate[] | null
  >(null);

  const handleSubmit = async (confirmDuplicate = false) => {
    setFormError(null);

    // Validation
    const trimmedName = name.trim();
    if (trimmedName.length < 2 || trimmedName.length > 120) {
      setFormError(t("patients:register.validation.name"));
      return;
    }

    const cleanPhone = phone.replace(/[\s\-()+]/g, "");
    if (!/^\d{10,15}$/.test(cleanPhone)) {
      setFormError(t("patients:validation.phone"));
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
        whatsapp_number: whatsappNumber
          ? whatsappNumber.replace(/[\s\-()+]/g, "")
          : undefined,
        consent_reports: consentReports,
        confirm_duplicate: confirmDuplicate,
      };

      const result = await service.createPatient(payload);
      setDuplicateCandidates(null);
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
                  <ArrowLeft className={styles.crumbIcon} />
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

        {/* Duplicate Warning Modal / Banner */}
        {duplicateCandidates && duplicateCandidates.length > 0 && (
          <div
            role="alert"
            data-testid="duplicate-warning-banner"
            className={styles.alertWarning}
          >
            <div className={styles.alertHead}>
              <AlertTriangle className={styles.alertIcon} />
              <span>{t("patients:register.duplicate.title")}</span>
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
                  <Loader2 className={`${styles.buttonIcon} ${styles.spin}`} />
                )}
                <span>{t("patients:register.duplicate.confirm")}</span>
              </button>
            </div>
          </div>
        )}

        {/* General Error Alert */}
        {formError && (
          <div role="alert" className={styles.alert}>
            <AlertCircle className={styles.alertIcon} />
            <span>{formError}</span>
          </div>
        )}

        {/* Registration Form Card */}
        <div className={styles.card}>
          <form
            id="patientRegistrationForm"
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit(false);
            }}
            className={styles.form}
          >
            {/* SECTION 1: Identity */}
            <div className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>
                  {t("patients:demographics")}
                </h2>
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
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("patients:register.full_name_placeholder")}
                  className={styles.input}
                />
              </div>

              {/* Phone & Sex */}
              <div className={styles.grid2}>
                <div className={styles.field}>
                  <label htmlFor="phoneNumber" className={styles.label}>
                    {t("common:labels.phone")}{" "}
                    <span className={styles.required}>*</span>
                  </label>
                  <input
                    id="phoneNumber"
                    name="phoneNumber"
                    type="tel"
                    dir="ltr"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder={t("patients:register.phone_placeholder")}
                    className={styles.input}
                  />
                  <p className={styles.hint}>
                    {t("patients:register.phone_hint")}
                  </p>
                </div>

                <div className={styles.field}>
                  <span className={styles.label}>
                    {t("common:labels.sex")}{" "}
                    <span className={styles.required}>*</span>
                  </span>
                  <div
                    role="radiogroup"
                    aria-label={t("common:labels.sex")}
                    className={styles.radioTrack}
                  >
                    <label
                      className={`${styles.radioOption} ${
                        sex === "M" ? styles.radioOptionSelected : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="sex"
                        value="M"
                        checked={sex === "M"}
                        onChange={() => setSex("M")}
                        className={styles.radioInput}
                      />
                      <span className={styles.radioDot} aria-hidden="true" />
                      <span>{t("patients:sex.male")}</span>
                    </label>
                    <label
                      className={`${styles.radioOption} ${
                        sex === "F" ? styles.radioOptionSelected : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="sex"
                        value="F"
                        checked={sex === "F"}
                        onChange={() => setSex("F")}
                        className={styles.radioInput}
                      />
                      <span className={styles.radioDot} aria-hidden="true" />
                      <span>{t("patients:sex.female")}</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Date of Birth */}
              <div className={styles.field}>
                <label htmlFor="dateOfBirth" className={styles.label}>
                  {t("common:labels.dob")}
                </label>
                <input
                  id="dateOfBirth"
                  name="dateOfBirth"
                  type="date"
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  className={`${styles.input} ${styles.inputDate}`}
                />
                <p className={styles.hint}>{t("patients:register.dob_hint")}</p>
              </div>
            </div>

            {/* SECTION 2: Contact & consent */}
            <div className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>
                  {t("patients:register.section_delivery")}
                </h2>
              </div>

              {/* WhatsApp */}
              <div className={styles.field}>
                <label htmlFor="whatsappNumber" className={styles.label}>
                  {t("patients:register.whatsapp")}
                </label>
                <input
                  id="whatsappNumber"
                  name="whatsappNumber"
                  type="tel"
                  dir="ltr"
                  value={whatsappNumber}
                  onChange={(e) => setWhatsappNumber(e.target.value)}
                  placeholder={t("patients:register.whatsapp_placeholder")}
                  className={styles.input}
                />
                <p className={styles.hint}>
                  {t("patients:register.whatsapp_hint")}
                </p>
              </div>

              {/* Consent checkbox */}
              <div>
                <label className={styles.checkboxRow}>
                  <input
                    id="consentReports"
                    name="consentReports"
                    type="checkbox"
                    checked={consentReports}
                    onChange={(e) => setConsentReports(e.target.checked)}
                    className={styles.checkbox}
                  />
                  <span className={styles.checkboxText}>
                    {t("patients:register.consent")}
                  </span>
                </label>
              </div>
            </div>

            {/* Footer Actions */}
            <div className={styles.footer}>
              <button
                type="button"
                onClick={onCancel}
                className={styles.cancelButton}
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className={styles.primaryButton}
              >
                {isLoading ? (
                  <Loader2 className={`${styles.buttonIcon} ${styles.spin}`} />
                ) : (
                  <Check className={styles.buttonIcon} />
                )}
                <span>
                  {isLoading
                    ? t("patients:register.registering")
                    : t("patients:register.title")}
                </span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
export default RegisterPatientScreen;
