import { useTranslation } from "react-i18next";
import { Code128Barcode } from "./Code128Barcode";
import type { SampleLabelData } from "../types";
import styles from "./LabelPrintSheet.module.css";

export interface LabelPrintSheetProps {
  labelData: SampleLabelData;
  /** Real tenant organisation name resolved from settings / session. */
  tenantName?: string;
  className?: string;
}

export function LabelPrintSheet({
  labelData,
  tenantName,
  className,
}: LabelPrintSheetProps): JSX.Element {
  const { t } = useTranslation("samples");
  const isCode128 =
    (labelData.barcode.symbology || "").toLowerCase() === "code128";
  const resolvedTenant = tenantName?.trim() || "LabFlow";

  return (
    <div
      className={[styles.sheetContainer, className].filter(Boolean).join(" ")}
      data-print-root
    >
      <article className={styles.labelCard}>
        {/* Tenant Header (Prominent) */}
        <header className={styles.tenantHeader}>
          <div className={styles.tenantName}>{resolvedTenant}</div>
          {labelData.branch_name && (
            <div className={styles.tenantBranch}>{labelData.branch_name}</div>
          )}
        </header>

        {/* Patient Demographics */}
        <section className={styles.patientSection}>
          <div className={styles.patientName}>{labelData.patient_name}</div>
          <div className={styles.patientMeta}>
            <span>{t("samples:label_print.mrn")}</span>
            <span className={styles.mrnBadge}>
              <bdi dir="ltr">{labelData.mrn}</bdi>
            </span>
            {labelData.date_of_birth && (
              <span>
                · {t("samples:label_print.dob")}{" "}
                <bdi dir="ltr">{labelData.date_of_birth}</bdi>
              </span>
            )}
          </div>
        </section>

        {/* Barcode & Accession */}
        <section className={styles.barcodeSection}>
          {isCode128 ? (
            <Code128Barcode
              value={labelData.barcode.payload}
              height={52}
              barWidth={2}
              ariaLabel={t("samples:label_print.barcode_aria", {
                value: labelData.barcode.payload,
              })}
            />
          ) : (
            <div className="p-2 text-xs text-red-600 bg-red-50 rounded">
              {t("samples:label_print.unsupported", {
                symbology: labelData.barcode.symbology,
              })}
            </div>
          )}
          <div className={styles.accessionNumber}>
            <bdi dir="ltr">{labelData.accession_id}</bdi>
          </div>
        </section>

        {/* Tests Chips */}
        {labelData.tests && labelData.tests.length > 0 && (
          <section className={styles.testsSection}>
            {labelData.tests.map((test, idx) => (
              <span key={idx} className={styles.testChip}>
                {test}
              </span>
            ))}
          </section>
        )}

        {/* Collection Metadata */}
        <footer className={styles.collectionMeta}>
          <span>
            {t("samples:label_print.collected")}{" "}
            <bdi dir="ltr">{labelData.collected_at}</bdi>
          </span>
          {labelData.collected_by && (
            <span>
              {t("samples:label_print.by")}{" "}
              <bdi dir="ltr">{labelData.collected_by}</bdi>
            </span>
          )}
        </footer>

        {/* Tiny Software Credit */}
        <div className={styles.footerCredit}>
          {t("samples:label_print.software_credit")}
        </div>
      </article>
    </div>
  );
}

export default LabelPrintSheet;
