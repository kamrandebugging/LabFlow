import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, Loader2, AlertCircle } from "lucide-react";
import { messageForError } from "../../lib/errors";
import styles from "./PatientForm.module.css";
import { patientService } from "./patientService";
import type { PatientDetail, PatientUpdateInput } from "./types";

interface PatientEditScreenProps {
  patientId: string;
  onBack?: () => void;
  onSuccess?: () => void;
  onCancel?: () => void;
  service?: typeof patientService;
}

export const PatientEditScreen: React.FC<PatientEditScreenProps> = ({
  patientId,
  onSuccess,
  onCancel,
  service = patientService,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [sex, setSex] = useState<"M" | "F">("M");
  const [dateOfBirth, setDateOfBirth] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    service
      .getPatient(patientId)
      .then((data) => {
        if (!isMounted) return;
        setPatient(data);
        setName(data.name || "");
        setPhone(data.phone || "");
        setSex(data.sex === "F" ? "F" : "M");
        setDateOfBirth(
          data.date_of_birth ? data.date_of_birth.slice(0, 10) : "",
        );
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err && typeof err === "object" && ("code" in err || "status" in err)
              ? messageForError(err, t)
              : t("patients:edit.errors.load"),
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedName = name.trim();
    if (trimmedName.length < 2 || trimmedName.length > 120) {
      setError(t("patients:edit.validation.name"));
      return;
    }

    const cleanPhone = phone.replace(/[\s\-()+]/g, "");
    if (!/^\d{10,15}$/.test(cleanPhone)) {
      setError(t("patients:validation.phone"));
      return;
    }

    setIsSaving(true);
    try {
      const payload: PatientUpdateInput = {
        name: trimmedName,
        phone: cleanPhone,
        sex,
        date_of_birth: dateOfBirth || null,
      };

      await service.updatePatient(patientId, payload, patient?.version);
      onSuccess?.();
    } catch (err: unknown) {
      setError(
        err && typeof err === "object" && ("code" in err || "status" in err)
          ? messageForError(err, t)
          : t("patients:edit.errors.save"),
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <Loader2 className={`${styles.recordIcon} ${styles.spin}`} />
        <span className={styles.loadingText}>{t("patients:edit.loading")}</span>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Header */}
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
                  <span>{t("patients:edit.breadcrumb_record")}</span>
                </button>
              </li>
              <li className={styles.crumbSep}>/</li>
              <li className={styles.crumbCurrent}>
                {t("patients:edit_demographics")}
              </li>
            </ol>
          </nav>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{t("patients:edit.title")}</h1>
            {patient?.mrn && (
              <span dir="ltr" className={styles.mrnBadge}>
                {patient.mrn}
              </span>
            )}
          </div>
        </div>

        {/* Error alert */}
        {error && (
          <div role="alert" className={styles.alert}>
            <AlertCircle className={styles.alertIcon} />
            <span className={styles.alertText}>
              <span className={styles.alertHeadText}>
                {t("patients:edit.save_failed")}
              </span>
              <span className={styles.alertDetail}>{error}</span>
            </span>
          </div>
        )}

        {/* Form Card */}
        <div className={styles.card}>
          <form onSubmit={handleSubmit} className={styles.form}>
            <div className={styles.section}>
              <div className={styles.field}>
                <label htmlFor="editFullName" className={styles.label}>
                  {t("patients:field_full_name")}{" "}
                  <span className={styles.required}>*</span>
                </label>
                <input
                  id="editFullName"
                  name="name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className={styles.input}
                />
              </div>

              <div className={styles.grid2}>
                <div className={styles.field}>
                  <label htmlFor="editPhone" className={styles.label}>
                    {t("patients:edit.field_phone")}{" "}
                    <span className={styles.required}>*</span>
                  </label>
                  <input
                    id="editPhone"
                    name="phone"
                    type="tel"
                    dir="ltr"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className={styles.input}
                  />
                </div>

                <div className={styles.field}>
                  <span className={styles.label}>
                    {t("patients:edit.field_sex")}{" "}
                    <span className={styles.required}>*</span>
                  </span>
                  <div
                    role="radiogroup"
                    aria-label={t("patients:edit.field_sex")}
                    className={styles.radioTrack}
                  >
                    <label
                      className={`${styles.radioOption} ${
                        sex === "M" ? styles.radioOptionSelected : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name="editSex"
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
                        name="editSex"
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

              <div className={styles.field}>
                <label htmlFor="editDob" className={styles.label}>
                  {t("common:labels.dob")}
                </label>
                <input
                  id="editDob"
                  name="dateOfBirth"
                  type="date"
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  className={`${styles.input} ${styles.inputDate}`}
                />
              </div>
            </div>

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
                disabled={isSaving}
                className={styles.primaryButton}
              >
                {isSaving ? (
                  <Loader2 className={`${styles.buttonIcon} ${styles.spin}`} />
                ) : (
                  <Check className={styles.buttonIcon} />
                )}
                <span>
                  {isSaving
                    ? t("common:actions.saving")
                    : t("patients:edit.save")}
                </span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
export default PatientEditScreen;
