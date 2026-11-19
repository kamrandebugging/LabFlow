import type { SampleEventItem } from "../types";
import styles from "./SampleTimeline.module.css";

export interface SampleTimelineProps {
  events?: SampleEventItem[];
  className?: string;
}

function formatPktTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    return `${d.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "Asia/Karachi",
    })} ${d.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZone: "Asia/Karachi",
    })} PKT`;
  } catch {
    return isoString;
  }
}

function getDotClass(event: string): string {
  const ev = event.toUpperCase();
  if (ev === "COLLECTED" || ev === "RECEIVED") return styles.mintDot || "";
  if (ev === "IN_PROCESS") return styles.amberDot || "";
  if (ev === "REJECTED") return styles.redDot || "";
  if (ev === "READY") return styles.greenDot || "";
  if (ev.startsWith("TRANSFER")) return styles.blueDot || "";
  if (ev === "CANCELLED") return styles.greyDot || "";
  return styles.greyDot || "";
}

export function SampleTimeline({
  events,
  className,
}: SampleTimelineProps): JSX.Element {
  if (!events || events.length === 0) {
    return (
      <div className={[styles.emptyState, className].filter(Boolean).join(" ")}>
        No custody events yet
      </div>
    );
  }

  return (
    <div className={[styles.timeline, className].filter(Boolean).join(" ")}>
      {events.map((ev, index) => {
        const dotClass = getDotClass(ev.event);
        const payload = ev.payload;

        return (
          <div key={ev.id || index} className={styles.timelineItem}>
            <div className={styles.spine} aria-hidden="true" />
            <div
              className={[styles.dot, dotClass].join(" ")}
              aria-hidden="true"
            />
            <div className={styles.content}>
              <div className={styles.eventHeader}>
                <span className={styles.eventName}>{ev.event}</span>
                <span className={styles.timestamp}>
                  {formatPktTimestamp(ev.timestamp)}
                </span>
              </div>
              <div className={styles.meta}>
                {ev.actor && <span>by {ev.actor}</span>}
                {ev.branch && <span>at {ev.branch.name}</span>}
              </div>
              {payload && (
                <div className={styles.payloadBox}>
                  {payload.rejection_code && (
                    <div>
                      <strong>Reason:</strong> {payload.rejection_code}
                    </div>
                  )}
                  {payload.from_branch && payload.to_branch && (
                    <div>
                      <strong>Route:</strong> {payload.from_branch.name} →{" "}
                      {payload.to_branch.name}
                    </div>
                  )}
                  {payload.note && (
                    <div>
                      <strong>Note:</strong> {payload.note}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default SampleTimeline;
