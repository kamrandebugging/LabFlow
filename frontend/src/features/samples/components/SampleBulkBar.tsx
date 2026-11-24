import { useTranslation } from "react-i18next";
import styles from "./SampleBulkBar.module.css";

export interface SampleBulkBarProps {
  selectedCount: number;
  onClear: () => void;
  onPrintLabels?: () => void;
  className?: string;
}

export function SampleBulkBar({
  selectedCount,
  onClear,
  onPrintLabels,
  className,
}: SampleBulkBarProps): JSX.Element | null {
  const { t } = useTranslation("samples");

  if (selectedCount <= 0) return null;

  return (
    <div
      role="region"
      aria-label={t("samples:bulk.aria")}
      className={[styles.bulkBarContainer, className].filter(Boolean).join(" ")}
    >
      <span className={styles.countText}>
        {selectedCount === 1
          ? t("samples:bulk.selected_one", { n: selectedCount })
          : t("samples:bulk.selected_many", { n: selectedCount })}
      </span>
      <button type="button" onClick={onClear} className={styles.clearButton}>
        {t("samples:bulk.clear")}
      </button>
      {onPrintLabels && (
        <button
          type="button"
          onClick={onPrintLabels}
          disabled={selectedCount === 0}
          className={styles.actionButton}
        >
          {t("samples:bulk.print", { n: selectedCount })}
        </button>
      )}
    </div>
  );
}

export default SampleBulkBar;
