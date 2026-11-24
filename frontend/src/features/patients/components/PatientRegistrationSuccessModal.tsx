import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Plus,
  ExternalLink,
  Copy,
  CheckCheck,
  X,
  FileText,
  Receipt,
} from "lucide-react";
import { useDialogFocus } from "../../../lib/dialogFocus";
import { calculatePatientAge } from "../patientAge";
import type { PatientSummary } from "../types";
import styles from "../../../components/ui/VeylaSuccessModal.module.css";

export interface PatientRegistrationSuccessModalProps {
  isOpen: boolean;
  patient: PatientSummary;
  onCreateInvoice?: (patientId: string) => void;
  onViewProfile?: (patientId: string) => void;
  onRegisterAnother?: () => void;
  onClose: () => void;
}

export function PatientRegistrationSuccessModal({
  isOpen,
  patient,
  onCreateInvoice,
  onViewProfile,
  onRegisterAnother,
  onClose,
}: PatientRegistrationSuccessModalProps): JSX.Element | null {
  const { t, i18n } = useTranslation(["patients", "common"]);
  const [copied, setCopied] = useState(false);
  const panelRef = useDialogFocus<HTMLDivElement>(isOpen, onClose);

  if (!isOpen) return null;

  const handleCopyMrn = async () => {
    try {
      await navigator.clipboard.writeText(patient.mrn);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const isRtl = i18n.language === "ur";

  const formattedCreatedAt = patient.created_at
    ? new Date(patient.created_at).toLocaleString(isRtl ? "ur-PK" : "en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Karachi",
      })
    : new Date().toLocaleString(isRtl ? "ur-PK" : "en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Karachi",
      });

  const age = calculatePatientAge(
    patient.date_of_birth || null,
    patient.year_of_birth || null,
  );

  const sexDisplay =
    patient.sex === "M"
      ? t("patients:sex.male")
      : patient.sex === "F"
        ? t("patients:sex.female")
        : t("patients:sex.other");

  return (
    <div className={styles.modalBackdrop}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="patient-success-title"
        className={styles.modalPanel}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          data-testid="close-patient-modal-btn"
          aria-label={t("patients:success_modal.close_dialog")}
          className={styles.closeButton}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Hero Area */}
        <div className={styles.heroArea}>
          <div className={styles.iconRing}>
            <Check className="w-7 h-7 stroke-[3]" />
          </div>
          <h2 id="patient-success-title" className={styles.title}>
            {t("patients:success_modal.title")}
          </h2>
          <p className={styles.subtitle}>
            {t("patients:success_modal.subtitle")}
          </p>
        </div>

        {/* MRN Barcode Pill */}
        <div className={styles.codePill}>
          <div className={styles.codeInfo}>
            <span className={styles.codeLabel}>
              {t("patients:success_modal.mrn_label")}
            </span>
            <span className={styles.codeValue} dir="ltr">
              {patient.mrn}
            </span>
          </div>
          <button
            type="button"
            onClick={handleCopyMrn}
            data-testid="copy-mrn-btn"
            className={styles.copyButton}
          >
            {copied ? (
              <>
                <CheckCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">
                  {t("patients:success_modal.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>{t("patients:success_modal.copy")}</span>
              </>
            )}
          </button>
        </div>

        {/* Patient Details Card */}
        <div className={styles.detailsCard}>
          <div className={styles.detailsGrid}>
            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("patients:success_modal.patient_name")}
              </span>
              <span className={styles.detailValue}>{patient.name}</span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("patients:success_modal.age_sex")}
              </span>
              <span className={styles.detailValue}>
                {age ? `${age} · ` : ""}
                {sexDisplay}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("patients:success_modal.primary_phone")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                {patient.phone || "—"}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("patients:success_modal.branch")}
              </span>
              <span className={styles.detailValue}>
                {patient.branch_name || "—"}
              </span>
            </div>

            <div className={styles.detailItem}>
              <span className={styles.detailLabel}>
                {t("patients:success_modal.registered_at")}
              </span>
              <span className={styles.detailValue} dir="ltr">
                {formattedCreatedAt}
              </span>
              <span className={styles.detailSub}>
                {t("patients:success_modal.pkt")}
              </span>
            </div>

            {patient.referral_partner_name && (
              <div className={styles.detailItem}>
                <span className={styles.detailLabel}>
                  {t("patients:success_modal.referral_partner")}
                </span>
                <span className={styles.detailValue}>
                  {patient.referral_partner_name}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons Area */}
        <div className={styles.actionsArea}>
          {onCreateInvoice && (
            <button
              type="button"
              data-testid="create-invoice-for-patient-btn"
              onClick={() => onCreateInvoice(patient.id)}
              className={styles.primaryAction}
            >
              <Receipt className="w-4 h-4" />
              <span>{t("patients:success_modal.create_invoice")}</span>
            </button>
          )}

          {onRegisterAnother && (
            <button
              type="button"
              data-testid="register-another-patient-btn"
              onClick={onRegisterAnother}
              className={styles.secondaryAction}
            >
              <Plus className="w-4 h-4" />
              <span>{t("patients:success_modal.register_another")}</span>
            </button>
          )}

          <div className={styles.tertiaryRow}>
            {onViewProfile && (
              <button
                type="button"
                data-testid="view-patient-profile-btn"
                onClick={() => onViewProfile(patient.id)}
                className={styles.ghostAction}
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>{t("patients:success_modal.view_profile")}</span>
              </button>
            )}

            <button
              type="button"
              data-testid="back-to-patients-list-btn"
              onClick={onClose}
              className={styles.ghostAction}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>{t("patients:success_modal.back_to_list")}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PatientRegistrationSuccessModal;
