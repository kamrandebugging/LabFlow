/**
 * A value that cross-fades when its text changes (150ms, tokens only).
 *
 * The inner node is keyed by the rendered value, so a change remounts it and
 * replays the opacity animation without touching the surrounding layout.
 * Used by the dashboard KPIs and the patient live-preview card.
 */
import type { ReactNode } from "react";

import styles from "./FadeValue.module.css";

export interface FadeValueProps {
  value: ReactNode;
  className?: string;
}

export function FadeValue({ value, className }: FadeValueProps): JSX.Element {
  const key =
    typeof value === "string" || typeof value === "number"
      ? String(value)
      : undefined;

  return (
    <span
      key={key}
      className={[styles.fadeValue, className].filter(Boolean).join(" ")}
    >
      {value}
    </span>
  );
}

export default FadeValue;
