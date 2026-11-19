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
  if (selectedCount <= 0) return null;

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className={[styles.bulkBarContainer, className].filter(Boolean).join(" ")}
    >
      <span className={styles.countText}>
        {selectedCount} {selectedCount === 1 ? "sample" : "samples"} selected
      </span>
      <button
        type="button"
        onClick={onClear}
        className={styles.clearButton}
      >
        Clear
      </button>
      {onPrintLabels && (
        <button
          type="button"
          onClick={onPrintLabels}
          disabled={selectedCount === 0}
          className={styles.actionButton}
        >
          Print labels ({selectedCount})
        </button>
      )}
    </div>
  );
}

export default SampleBulkBar;
