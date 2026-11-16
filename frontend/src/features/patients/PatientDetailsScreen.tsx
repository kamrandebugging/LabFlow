import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  Edit,
  History,
  Phone,
  ShieldCheck,
  ShieldX,
  User,
  Trash2,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { useDialogFocus } from "../../lib/dialogFocus";
import styles from "./PatientRecord.module.css";
import { patientService } from "./patientService";
import { VeylaDrawer } from "./VeylaDrawer";
import { PatientHistoryScreen } from "./PatientHistoryScreen";
import type { PatientDetail } from "./types";

interface PatientDetailsScreenProps {
  patientId: string;
  onBack?: () => void;
  onEdit?: (patientId: string) => void;
  onViewHistory?: (patientId: string) => void;
  onNewVisit?: (patientId: string) => void;
  /** Front-desk roles only; bench/clinical roles get a read-only record. */
  canManage?: boolean;
  /** DELETE /patients/{id} is ADMIN (Owner/Manager) only. */
  canDelete?: boolean;
  service?: typeof patientService;
  /** Element focus returns to when the drawer closes (drawer variant). */
  triggerRef?: React.RefObject<HTMLElement>;
  /** Which drawer tab is showing. Drawer variant only. */
  tab?: "overview" | "history";
  onTabChange?: (tab: "overview" | "history") => void;
  /**
   * "page" is the standalone record route. "drawer" renders the same record
   * inside the shared Veyla side drawer over the patient list.
   */
  variant?: "page" | "drawer";
}

export const PatientDetailsScreen: React.FC<PatientDetailsScreenProps> = ({
  patientId,
  onBack,
  onEdit,
  onViewHistory,
  onNewVisit,
  canManage = false,
  canDelete = false,
  service = patientService,
  variant = "page",
  triggerRef,
  tab = "overview",
  onTabChange,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement>(null);
  const deletePanelRef = useDialogFocus<HTMLDivElement>(
    showDeleteModal,
    () => setShowDeleteModal(false),
    deleteTriggerRef,
  );

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    service
      .getPatient(patientId)
      .then((data) => {
        if (isMounted) setPatient(data);
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err && typeof err === "object" && ("code" in err || "status" in err)
              ? messageForError(err, t)
              : t("patients:details.errors.load"),
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service, t]);

  const handleConfirmDelete = async () => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await service.deletePatient(patientId);
      setShowDeleteModal(false);
      onBack?.();
    } catch (err: unknown) {
      setShowDeleteModal(false);
      setDeleteError(
        err && typeof err === "object" && ("code" in err || "status" in err)
          ? messageForError(err, t)
          : t("patients:details.errors.delete"),
      );
    } finally {
      setIsDeleting(false);
    }
  };

  /* ------------------------------------------------------------ loading --- */

  const loadingBlock = (
    <div className={styles.loading}>
      <RefreshCw className={`${styles.statusIcon} ${styles.spin}`} />
      <span>{t("patients:details.loading")}</span>
    </div>
  );

  const errorBlock = (
    <div className={styles.errorState}>
      <span className={styles.errorIcon}>
        <AlertCircle className={styles.statusIcon} />
      </span>
      <h2 className={styles.errorTitle}>
        {t("patients:details.unavailable_title")}
      </h2>
      <p className={styles.errorText}>{error || t("patients:not_found")}</p>
      <button type="button" onClick={onBack} className={styles.primaryButton}>
        {t("patients:return_to_patients")}
      </button>
    </div>
  );

  /* ------------------------------------------------------------- content -- */

  const primaryPhone =
    patient?.phone ||
    patient?.contacts?.find((c) => c.kind === "phone")?.value ||
    "—";
  const whatsappContact = patient?.contacts?.find(
    (c) => c.kind === "whatsapp",
  )?.value;
  const hasDigitalConsent = patient?.consents?.some((c) => !c.revoked_at);

  // Identity block: identical wording and values in both variants.
  const identity = patient ? (
    <div className={styles.nameRow}>
      <h1 className={styles.title}>{patient.name}</h1>
      <span className={styles.activeBadge}>
        <ShieldCheck
          className={`${styles.statusIcon} ${styles.pulse}`}
          aria-hidden="true"
        />
        {t("patients:details.active")}
      </span>
      <span className={styles.branchPill}>
        {patient.branch_name || t("patients:main_branch")}
      </span>
      <p className={styles.metaLine}>
        {t("patients:mrn")}:{" "}
        <strong className={styles.metaStrong}>
          <bdi dir="ltr">{patient.mrn}</bdi>
        </strong>{" "}
        · {t("patients:details.registered")}{" "}
        <bdi dir="ltr">{formatDate(patient.created_at)}</bdi>
      </p>
    </div>
  ) : null;

  // Actions: same handlers, same order in both variants.
  const actions = patient ? (
    <div className={styles.actions}>
      {canManage && onEdit ? (
        <button
          type="button"
          onClick={() => onEdit(patient.id)}
          className={styles.secondaryButton}
        >
          <Edit className={styles.buttonIcon} aria-hidden="true" />
          <span>{t("patients:edit_demographics")}</span>
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => onViewHistory?.(patient.id)}
        className={styles.secondaryButton}
      >
        <History className={styles.buttonIcon} aria-hidden="true" />
        <span>{t("patients:details.audit_history")}</span>
      </button>
      <button
        type="button"
        onClick={() => onNewVisit?.(patient.id)}
        className={styles.primaryButton}
      >
        <span>{t("patients:details.new_accession")}</span>
      </button>
      {canDelete ? (
        <span className={styles.dangerSeparator}>
          <button
            type="button"
            ref={deleteTriggerRef}
            onClick={() => setShowDeleteModal(true)}
            disabled={isDeleting}
            title={t("patients:details.delete_patient_aria")}
            aria-label={t("patients:details.delete_patient_aria")}
            className={styles.dangerButton}
          >
            <Trash2 className={styles.buttonIcon} aria-hidden="true" />
          </button>
        </span>
      ) : null}
    </div>
  ) : null;

  const cards = patient ? (
    <div className={styles.grid}>
      {/* Core Identity Card */}
      <div className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            <User className={styles.cardIcon} aria-hidden="true" />
            <span>{t("patients:demographics")}</span>
          </h2>
        </div>

        <div className={styles.fieldGrid}>
          <div className={styles.field}>
            <span className={styles.fieldLabel}>
              {t("patients:details.field_full_name")}
            </span>
            <span className={styles.fieldValue}>{patient.name}</span>
          </div>
          <div className={styles.field}>
            <span className={styles.fieldLabel}>
              {t("patients:details.field_sex")}
            </span>
            <span className={styles.fieldValue}>
              {patient.sex === "M"
                ? t("patients:sex.male")
                : patient.sex === "F"
                  ? t("patients:sex.female")
                  : t("patients:sex.other")}
            </span>
          </div>
          {patient.date_of_birth ? (
            <div className={styles.field}>
              <span className={styles.fieldLabel}>
                {t("patients:details.field_dob")}
              </span>
              <span className={styles.fieldValue}>
                <bdi dir="ltr">{formatDate(patient.date_of_birth)}</bdi>
              </span>
            </div>
          ) : null}
          {primaryPhone !== "—" ? (
            <div className={styles.field}>
              <span className={styles.fieldLabel}>
                {t("patients:details.field_phone")}
              </span>
              <span className={styles.monoValue}>
                <Phone className={styles.inlineIcon} aria-hidden="true" />
                <bdi dir="ltr">{primaryPhone}</bdi>
              </span>
            </div>
          ) : null}
        </div>
      </div>

      {/* Digital Consent & Comms Card */}
      <div className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            <ShieldCheck className={styles.cardIcon} aria-hidden="true" />
            <span>{t("patients:details.consent_title")}</span>
          </h2>
        </div>

        <div className={styles.field}>
          <span className={styles.fieldLabel}>
            {t("patients:details.digital_delivery")}
          </span>
          <span
            className={hasDigitalConsent ? styles.consentOn : styles.consentOff}
          >
            {hasDigitalConsent ? (
              <ShieldCheck className={styles.statusIcon} aria-hidden="true" />
            ) : (
              <ShieldX className={styles.statusIcon} aria-hidden="true" />
            )}
            {hasDigitalConsent
              ? t("patients:details.consent_granted")
              : t("patients:details.consent_none")}
          </span>
        </div>
        {whatsappContact && (
          <div className={styles.field}>
            <span className={styles.fieldLabel}>
              {t("patients:details.whatsapp_channel")}
            </span>
            <span className={styles.monoValue}>
              <bdi dir="ltr">{whatsappContact}</bdi>
            </span>
          </div>
        )}
      </div>
    </div>
  ) : null;

  /* Delete confirmation modal — same markup in both variants. */
  const deleteModal =
    showDeleteModal && patient
      ? createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-patient-title"
            className={`${styles.scrim} veyla-modal-scrim`}
          >
            <div
              ref={deletePanelRef}
              tabIndex={-1}
              className={`${styles.modal} veyla-modal`}
            >
              <h2 id="delete-patient-title" className={styles.modalTitle}>
                Delete Patient Record?
              </h2>
              <p className={styles.modalText}>
                {t("patients:details.confirm_delete")}
              </p>
              <dl className={styles.modalIdentity}>
                <div className={styles.modalIdentityRow}>
                  <dt className={styles.modalIdentityLabel}>
                    {t("patients:details.field_full_name")}
                  </dt>
                  <dd className={styles.modalIdentityValue}>{patient.name}</dd>
                </div>
                <div className={styles.modalIdentityRow}>
                  <dt className={styles.modalIdentityLabel}>
                    {t("patients:mrn")}
                  </dt>
                  <dd className={styles.modalIdentityValue} dir="ltr">
                    {patient.mrn}
                  </dd>
                </div>
              </dl>
              <div className={styles.modalActions}>
                <button
                  type="button"
                  onClick={() => setShowDeleteModal(false)}
                  disabled={isDeleting}
                  className={styles.secondaryButton}
                >
                  Keep patient
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDelete}
                  disabled={isDeleting}
                  className={styles.modalDanger}
                >
                  Confirm Delete
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
        <VeylaDrawer
          open
          onClose={() => onBack?.()}
          title={patient?.name ?? t("patients:details.loading")}
          header={identity}
          footer={<div className={styles.drawerFooterActions}>{actions}</div>}
          triggerRef={triggerRef}
        >
          <div className={styles.drawerShell}>
            {isLoading || error || !patient ? (
              isLoading ? (
                loadingBlock
              ) : (
                errorBlock
              )
            ) : (
              <>
                <div
                  className={styles.drawerTabs}
                  role="tablist"
                  aria-label={t("patients:details.tab_overview")}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === "overview"}
                    onClick={() => onTabChange?.("overview")}
                    className={`${styles.drawerTab} ${
                      tab === "overview" ? styles.drawerTabActive : ""
                    }`}
                  >
                    {t("patients:details.tab_overview")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === "history"}
                    onClick={() => onTabChange?.("history")}
                    className={`${styles.drawerTab} ${
                      tab === "history" ? styles.drawerTabActive : ""
                    }`}
                  >
                    {t("patients:details.tab_history")}
                  </button>
                </div>

                {tab === "history" ? (
                  <PatientHistoryScreen
                    variant="drawer"
                    patientId={patientId}
                    service={service}
                  />
                ) : (
                  cards
                )}
              </>
            )}
            {deleteError && (
              <div role="alert" className={styles.alert}>
                <AlertCircle className={styles.statusIcon} aria-hidden="true" />
                <span>{deleteError}</span>
              </div>
            )}
          </div>
        </VeylaDrawer>
        {deleteModal}
      </>
    );
  }

  /* ---------------------------------------------------------------- page -- */

  if (isLoading) {
    return loadingBlock;
  }

  if (error || !patient) {
    return errorBlock;
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* 1. Header & Actions */}
        <div className={styles.header}>
          <div>
            <nav aria-label={t("patients:breadcrumb_aria")}>
              <ol className={styles.breadcrumb}>
                <li>
                  <button
                    type="button"
                    onClick={onBack}
                    className={styles.breadcrumbLink}
                  >
                    <ArrowLeft className={styles.crumbIcon} />
                    <span>{t("common:nav.patients")}</span>
                  </button>
                </li>
                <li className={styles.crumbSep}>/</li>
                <li dir="ltr" className={styles.crumbMrn}>
                  {patient.mrn}
                </li>
              </ol>
            </nav>
            {identity}
          </div>

          {/* Action Buttons */}
          {actions}
        </div>

        {/* 2. Demographics & Record Grid */}
        {cards}

        {/* Delete failure (replaces the old blocking alert) */}
        {deleteError && (
          <div role="alert" className={styles.alert}>
            <AlertCircle className={styles.statusIcon} aria-hidden="true" />
            <span>{deleteError}</span>
          </div>
        )}
      </div>

      {deleteModal}
    </div>
  );
};
export default PatientDetailsScreen;
