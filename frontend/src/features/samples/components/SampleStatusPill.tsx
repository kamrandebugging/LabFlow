import type { SampleStatus } from "../types";
import styles from "./SampleStatusPill.module.css";

export interface SampleStatusPillProps {
  status: SampleStatus | "awaiting_collection" | "worst" | string;
  label?: string;
  className?: string;
}

export function SampleStatusPill({
  status,
  label,
  className,
}: SampleStatusPillProps): JSX.Element {
  const normalized = status.toLowerCase();

  let styleKey = styles.collected;
  let defaultLabel = "Collected";

  switch (normalized) {
    case "ready":
      styleKey = styles.ready;
      defaultLabel = "Ready / Reported";
      break;
    case "in_process":
      styleKey = styles.in_process;
      defaultLabel = "In Process";
      break;
    case "received":
      styleKey = styles.received;
      defaultLabel = "Received";
      break;
    case "collected":
      styleKey = styles.collected;
      defaultLabel = "Collected";
      break;
    case "rejected":
      styleKey = styles.rejected;
      defaultLabel = "Rejected";
      break;
    case "cancelled":
      styleKey = styles.cancelled;
      defaultLabel = "Cancelled";
      break;
    case "awaiting_collection":
      styleKey = styles.awaiting_collection;
      defaultLabel = "Awaiting Collection";
      break;
    case "worst":
      styleKey = styles.worst;
      defaultLabel = "Immediate";
      break;
    default:
      styleKey = styles.collected;
      defaultLabel = status;
      break;
  }

  const displayText = label || defaultLabel;

  return (
    <span
      className={[styles.pill, styleKey, className].filter(Boolean).join(" ")}
    >
      <span className={styles.dot} aria-hidden="true" />
      <span>{displayText}</span>
    </span>
  );
}

export default SampleStatusPill;
