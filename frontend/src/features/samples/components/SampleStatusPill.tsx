import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation(["samples", "common"]);
  const normalized = status.toLowerCase();

  let styleKey = styles.collected;

  switch (normalized) {
    case "ready":
      styleKey = styles.ready;
      break;
    case "in_process":
      styleKey = styles.in_process;
      break;
    case "received":
      styleKey = styles.received;
      break;
    case "collected":
      styleKey = styles.collected;
      break;
    case "rejected":
      styleKey = styles.rejected;
      break;
    case "cancelled":
      styleKey = styles.cancelled;
      break;
    case "awaiting_collection":
      styleKey = styles.awaiting_collection;
      break;
    case "worst":
      styleKey = styles.worst;
      break;
    default:
      styleKey = styles.collected;
      break;
  }

  const translatedLabel =
    normalized === "ready"
      ? t("samples:status.ready_reported")
      : normalized === "awaiting_collection"
        ? t("samples:status.awaiting_collection")
        : t(`common:status.sample.${normalized}`, {
            defaultValue: status,
          });

  const displayText = label || translatedLabel;

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
