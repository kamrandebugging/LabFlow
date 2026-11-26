import React, { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import {
  ArrowLeft,
  AlertCircle,
  RefreshCw,
  Activity,
  ShieldCheck,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate, formatMoney, statusLabel } from "../../lib/format";
import styles from "./PatientRecord.module.css";
import { patientService } from "./patientService";
import type { PatientDetail, PatientVisit } from "./types";

interface PatientHistoryScreenProps {
  patientId: string;
  onBack?: () => void;
  service?: typeof patientService;
  /**
   * "page" is the standalone history route. "drawer" renders only the audit
   * notice and the timeline, for the record drawer's History tab.
   */
  variant?: "page" | "drawer";
}

export const PatientHistoryScreen: React.FC<PatientHistoryScreenProps> = ({
  patientId,
  onBack,
  service = patientService,
  variant = "page",
}) => {
  const { t, i18n } = useTranslation(["patients", "common"]);
  const lang = i18n.language === "ur" ? "ur" : "en";
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [visits, setVisits] = useState<PatientVisit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    Promise.all([
      service.getPatient(patientId),
      service.getPatientHistory(patientId),
    ])
      .then(([patientData, historyData]) => {
        if (!isMounted) return;
        setPatient(patientData);
        setVisits(historyData?.visits ?? []);
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err && typeof err === "object" && ("code" in err || "status" in err)
              ? messageForError(err, t)
              : t("patients:history.errors.load"),
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service, t]);

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <RefreshCw className={`${styles.statusIcon} ${styles.spin}`} />
        <span>{t("patients:history.loading")}</span>
      </div>
    );
  }

  if (error || !patient) {
    return (
      <div className={styles.errorState}>
        <span className={styles.errorIcon}>
          <AlertCircle className={styles.statusIcon} />
        </span>
        <h2 className={styles.errorTitle}>
          {t("patients:history.unavailable_title")}
        </h2>
        <p className={styles.errorText}>{error || t("patients:not_found")}</p>
        <button type="button" onClick={onBack} className={styles.primaryButton}>
          {t("patients:return_to_patients")}
        </button>
      </div>
    );
  }

  // Legacy page variant only. The record drawer intentionally omits this
  // banner: the drawer header already carries the identity and MRN.
  const notice = (
    <div className={styles.notice}>
      <Activity className={styles.noticeIcon} aria-hidden="true" />
      <div className={styles.noticeText}>
        <span className={styles.noticeLabel}>
          {t("patients:history.ledger_scope_label")}
        </span>{" "}
        <Trans
          i18nKey="patients:history.ledger_scope_body"
          values={{ mrn: patient.mrn }}
          components={{
            strong: <strong dir="ltr" className={styles.inlineMono} />,
          }}
        />
      </div>
    </div>
  );

  const timeline = (
    <div className={styles.timeline}>
      {/* Registration event */}
      <div className={styles.event}>
        <div className={styles.eventHead}>
          <div className={styles.eventTitleRow}>
            <span className={styles.dot} aria-hidden="true" />
            <span className={styles.eventTitle}>
              {t("patients:history.event_registration")}
            </span>
          </div>
          <span className={styles.eventDate}>
            <bdi dir="ltr">{formatDate(patient.created_at)}</bdi>
          </span>
        </div>

        <div className={styles.eventGrid}>
          <div className={styles.field}>
            <span className={styles.eventLabel}>
              {t("patients:history.system_mrn")}
            </span>
            <span className={styles.monoValue}>
              <bdi dir="ltr">{patient.mrn}</bdi>
            </span>
          </div>
          <div className={styles.field}>
            <span className={styles.eventLabel}>
              {t("patients:history.home_branch")}
            </span>
            <span className={styles.eventValue}>
              {patient.branch_name || t("patients:main_branch")}
            </span>
          </div>
        </div>
      </div>

      {/* Chronological visit episodes (invoices, samples, reports) */}
      {visits.length === 0 ? (
        <div className={styles.event}>
          <div className={styles.note}>{t("patients:history.no_visits")}</div>
        </div>
      ) : (
        visits.map((visit) => (
          <div key={visit.invoice_id} className={styles.event}>
            <div className={styles.eventHead}>
              <div className={styles.eventTitleRow}>
                <span className={styles.dot} aria-hidden="true" />
                <span className={styles.eventTitle}>
                  {t("patients:history.invoice_label")}{" "}
                  <bdi dir="ltr" className={styles.inlineMono}>
                    {visit.invoice_number}
                  </bdi>{" "}
                  ·{" "}
                  {statusLabel("invoice", visit.status, (key) =>
                    t(`common:${key}`),
                  )}
                  {visit.total !== null
                    ? ` · ${formatMoney(visit.total, lang)}`
                    : ""}
                </span>
              </div>
              <span className={styles.eventDate}>
                <bdi dir="ltr">{formatDate(visit.created_at)}</bdi>
              </span>
            </div>

            <div className={styles.eventGrid}>
              <div className={styles.field}>
                <span className={styles.eventLabel}>
                  {t("patients:history.home_branch")}
                </span>
                <span className={styles.eventValue}>{visit.branch_name}</span>
              </div>
              <div className={styles.field}>
                <span className={styles.eventLabel}>
                  {t("patients:history.samples_label")}
                </span>
                <span className={styles.eventValue}>
                  {visit.samples.length === 0
                    ? "—"
                    : visit.samples
                        .map(
                          (s) =>
                            `${s.accession_id} (${statusLabel("sample", s.status, (key) => t(`common:${key}`))})`,
                        )
                        .join(", ")}
                </span>
              </div>
              <div className={styles.field}>
                <span className={styles.eventLabel}>
                  {t("patients:history.reports_label")}
                </span>
                <span className={styles.eventValue}>
                  {visit.reports.length === 0
                    ? "—"
                    : visit.reports
                        .map(
                          (r) =>
                            `${statusLabel("report", r.status, (key) => t(`common:${key}`))} v${r.current_version}`,
                        )
                        .join(", ")}
                </span>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );

  /* -------------------------------------------------------------- drawer -- */

  if (variant === "drawer") {
    return timeline;
  }

  /* ---------------------------------------------------------------- page -- */

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* 1. Header */}
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
              <li className={styles.crumbSep}>/</li>
              <li className={styles.crumbCurrent}>
                {t("patients:history.breadcrumb")}
              </li>
            </ol>
          </nav>
          <div className={styles.nameRow}>
            <div>
              <h1 className={styles.title}>
                {t("patients:history.title")}{" "}
                <bdi dir="ltr">{patient.name}</bdi>
              </h1>
              <p className={styles.metaLine}>
                <span>
                  {patient.sex === "M"
                    ? t("patients:sex.male")
                    : t("patients:sex.female")}
                </span>
                <span className={styles.crumbSep}> • </span>
                <span>
                  {patient.phone ? (
                    <bdi dir="ltr">{patient.phone}</bdi>
                  ) : (
                    t("patients:history.no_phone")
                  )}
                </span>
                <span className={styles.crumbSep}> • </span>
                <span>{patient.branch_name || t("patients:main_branch")}</span>
              </p>
            </div>
            <span className={styles.auditBadge}>
              <ShieldCheck className={styles.statusIcon} aria-hidden="true" />
              {t("patients:history.audit_active")}
            </span>
          </div>
        </div>

        {notice}
        {timeline}
      </div>
    </div>
  );
};
export default PatientHistoryScreen;
