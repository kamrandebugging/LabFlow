import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { motionDurationMs, prefersReducedMotion } from "../../lib/motion";
import styles from "./ChecksWaffle.module.css";

export interface WaffleDay {
  /** ISO day key, e.g. 2026-11-16 */
  date: string;
  /** Axis label, e.g. "Mon 16" */
  label: string;
  /** Real samples collected that day. Never fabricated. */
  total: number;
  /** Ready + Collected */
  ready: number;
  /** In Process + Received */
  review: number;
  /** Rejected */
  declined: number;
}

export interface ChecksWaffleProps {
  days: WaffleDay[];
  unitLabel?: string;
  /**
   * Kept for compatibility with the dashboard's status table; the waffle uses
   * the four Veyla groups, not the six LabFlow statuses.
   */
  statusConfig?: Record<string, { label: string; color: string }>;
  onActiveDayChange?: (day: WaffleDay | null) => void;
}

/**
 * Veyla waffle: one column per day, one square tile per sample.
 *
 * - Stack is built bottom-up: Declined (near-black), Review (grey), Passed
 *   (teal), then Capacity (well grey) filling the rest of the column.
 * - Columns run oldest -> newest, left -> right.
 * - Bucket is 1 tile = 1 sample while the busiest day is under 50 samples.
 *   Above that the bucket rises so a column stays at most ~40 tiles tall; the
 *   legend always prints the bucket actually used, so they cannot disagree.
 */
export function ChecksWaffle({
  days,
  unitLabel = "sample",
  onActiveDayChange,
}: ChecksWaffleProps): JSX.Element {
  const { t } = useTranslation(["dashboard", "common"]);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [renderedDays, setRenderedDays] = useState(days);
  const [leaving, setLeaving] = useState(false);
  const [entering, setEntering] = useState(false);

  const maxTotal = useMemo(
    () => Math.max(0, ...days.map((d) => d.total)),
    [days],
  );
  // Veyla keeps the column height fixed: derive the bucket from the busiest
  // day so the grid never grows past TARGET_ROWS tiles.
  const TARGET_ROWS = 12;
  const bucket = Math.max(1, Math.ceil(maxTotal / TARGET_ROWS));
  const rows = Math.min(
    40,
    Math.max(
      1,
      Math.ceil(Math.max(0, ...renderedDays.map((d) => d.total)) / bucket),
    ),
  );

  const activeDay = renderedDays.find((d) => d.date === activeDate) ?? null;

  const setActive = useCallback(
    (day: WaffleDay | null) => {
      setActiveDate(day?.date ?? null);
      onActiveDayChange?.(day);
    },
    [onActiveDayChange],
  );

  const signature = days.map((d) => `${d.date}:${d.total}`).join("|");
  const lastSignature = useRef(signature);

  useEffect(() => {
    if (signature === lastSignature.current) return;
    lastSignature.current = signature;

    if (prefersReducedMotion()) {
      setRenderedDays(days);
      setLeaving(false);
      setEntering(false);
      setActive(null);
      return;
    }

    setLeaving(true);
    setEntering(false);
    setActive(null);
    const swap = window.setTimeout(
      () => {
        setRenderedDays(days);
        setLeaving(false);
        setEntering(true);
      },
      motionDurationMs("--motion-fast", 150),
    );

    return () => window.clearTimeout(swap);
  }, [days, signature, setActive]);

  useEffect(() => {
    if (!entering) return;
    const settle = window.setTimeout(
      () => setEntering(false),
      motionDurationMs("--motion-base", 200) +
        Math.min(renderedDays.length, 10) * 15 +
        40,
    );
    return () => window.clearTimeout(settle);
  }, [entering, renderedDays.length]);

  return (
    <div className={styles.wrap}>
      <div className={styles.legend}>
        <span className={styles.legendBucket}>
          {`1 tile = ${bucket} ${unitLabel}${bucket > 1 ? "s" : ""}`}
        </span>
        <div className={styles.legendGroups}>
          <span className={styles.legendItem}>
            <i className={`${styles.swatch} ${styles.passed}`} />
            {t("dashboard:waffle.passed", "Passed")}
          </span>
          <span className={styles.legendItem}>
            <i className={`${styles.swatch} ${styles.review}`} />
            {t("dashboard:waffle.review", "Review")}
          </span>
          <span className={styles.legendItem}>
            <i className={`${styles.swatch} ${styles.declined}`} />
            {t("dashboard:waffle.declined", "Declined")}
          </span>
          <span className={styles.legendItem}>
            <i className={`${styles.swatch} ${styles.capacity}`} />
            {t("dashboard:waffle.capacity", "Capacity")}
          </span>
        </div>
      </div>

      <div className={styles.scroller} onMouseLeave={() => setActive(null)}>
        <div
          className={`${styles.grid} ${leaving ? styles.gridOut : ""}`}
          style={{ ["--waffle-rows" as string]: rows }}
        >
          {renderedDays.map((day, index) => {
            const filled = Math.min(rows, Math.ceil(day.total / bucket));
            const declinedTiles = Math.min(
              filled,
              Math.round(day.declined / bucket),
            );
            const reviewTiles = Math.min(
              filled - declinedTiles,
              Math.round(day.review / bucket),
            );
            const passedTiles = Math.max(
              0,
              filled - declinedTiles - reviewTiles,
            );
            const isActive = activeDate === day.date;

            const slots: Array<"declined" | "review" | "passed" | "capacity"> =
              [];
            for (let i = 0; i < declinedTiles; i++) slots.push("declined");
            for (let i = 0; i < reviewTiles; i++) slots.push("review");
            for (let i = 0; i < passedTiles; i++) slots.push("passed");
            while (slots.length < rows) slots.push("capacity");

            return (
              <div
                key={day.date}
                className={`${styles.col} ${entering ? styles.colIn : ""}`}
                style={
                  entering
                    ? { animationDelay: `${Math.min(index, 12) * 15}ms` }
                    : undefined
                }
                tabIndex={0}
                role="button"
                aria-label={`${day.label}: ${day.total} ${unitLabel}${day.total === 1 ? "" : "s"}`}
                onMouseEnter={() => setActive(day)}
                onFocus={() => setActive(day)}
                onBlur={() => setActive(null)}
                data-active={isActive ? "true" : undefined}
              >
                {activeDay?.date === day.date ? (
                  <div className={styles.tooltip} role="tooltip">
                    <strong>
                      {day.total} {unitLabel}
                      {day.total === 1 ? "" : "s"}
                    </strong>
                    <span>{day.label}</span>
                    <span>
                      {day.total > 0
                        ? `${Math.round((day.ready / day.total) * 100)}% ${t(
                            "dashboard:waffle.ready",
                            "ready",
                          )}`
                        : t("dashboard:waffle.empty", "no samples")}
                    </span>
                  </div>
                ) : null}

                <div className={styles.stack}>
                  {slots.map((kind, i) => (
                    <span
                      key={i}
                      className={`${styles.tile} ${styles[kind]}`}
                    />
                  ))}
                </div>

                <span className={styles.dayLabel}>{day.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default ChecksWaffle;
