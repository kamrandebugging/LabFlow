import { Code128Barcode } from "./Code128Barcode";
import type { SampleLabelData } from "../types";
import styles from "./LabelPrintSheet.module.css";

export interface LabelPrintSheetProps {
  labelData: SampleLabelData;
  tenantName?: string;
  className?: string;
}

export function LabelPrintSheet({
  labelData,
  tenantName = "City Diagnostic Laboratory",
  className,
}: LabelPrintSheetProps): JSX.Element {
  const isCode128 =
    (labelData.barcode.symbology || "").toLowerCase() === "code128";

  return (
    <div
      className={[styles.sheetContainer, className].filter(Boolean).join(" ")}
    >
      <article className={styles.labelCard}>
        {/* Tenant Header (Prominent) */}
        <header className={styles.tenantHeader}>
          <div className={styles.tenantName}>{tenantName}</div>
          {labelData.branch_name && (
            <div className={styles.tenantBranch}>{labelData.branch_name}</div>
          )}
        </header>

        {/* Patient Demographics */}
        <section className={styles.patientSection}>
          <div className={styles.patientName}>{labelData.patient_name}</div>
          <div className={styles.patientMeta}>
            <span>MRN:</span>
            <span className={styles.mrnBadge}>{labelData.mrn}</span>
            {labelData.date_of_birth && (
              <span>· DOB: {labelData.date_of_birth}</span>
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
            />
          ) : (
            <div className="p-2 text-xs text-red-600 bg-red-50 rounded">
              Unsupported barcode symbology: {labelData.barcode.symbology}
            </div>
          )}
          <div className={styles.accessionNumber}>{labelData.accession_id}</div>
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
          <span>Collected: {labelData.collected_at}</span>
          {labelData.collected_by && <span>By: {labelData.collected_by}</span>}
        </footer>

        {/* Tiny Software Credit */}
        <div className={styles.footerCredit}>Software by LabFlow</div>
      </article>
    </div>
  );
}

export default LabelPrintSheet;
