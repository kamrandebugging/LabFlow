import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { FadeValue } from "../../components/ui/FadeValue";
import { motionDurationMs, prefersReducedMotion } from "../../lib/motion";
import { pktDateLabel } from "./dashboardService";
import styles from "./DashboardUI.module.css";

export interface DashboardHeaderProps {
  title: string;
  subtitle: ReactNode;
  badge?: string;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
}

/**
 * The dashboard date line: the PKT calendar date, the "times are PKT" notice
 * and an optional screen scope. The date is isolated LTR so RTL never
 * re-orders the day, month or year.
 */
export function DashboardDateLine({
  suffix,
}: {
  suffix?: string;
}): JSX.Element {
  const { t } = useTranslation("common");
  return (
    <>
      <bdi dir="ltr">{pktDateLabel()}</bdi>
      {` · ${t("dashboard.pkt_label")}`}
      {suffix ? ` · ${suffix}` : null}
    </>
  );
}

/**
 * Veyla Page Header:
 * Breadcrumb → Large bold title → One-line muted subtitle → Page actions.
 */
export function DashboardHeader({
  title,
  subtitle,
  badge,
  breadcrumb,
  actions,
}: DashboardHeaderProps): JSX.Element {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        {breadcrumb ? (
          <nav
            aria-label="Breadcrumb"
            className="text-xs font-medium text-[var(--color-text-muted)] mb-1"
          >
            {breadcrumb}
          </nav>
        ) : null}
        <div className="flex items-center gap-3">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-[var(--color-text)] tracking-tight font-sans">
            {title}
          </h1>
          {badge ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-[var(--veyla-well)] text-[var(--color-text)] border border-[var(--color-border)]">
              <span
                aria-hidden="true"
                className="w-2 h-2 rounded-full bg-[var(--color-success)]"
              />
              {badge}
            </span>
          ) : null}
        </div>
        <p className="text-sm text-[var(--color-text-muted)] font-normal">
          {subtitle}
        </p>
      </div>
      {actions ? (
        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          {actions}
        </div>
      ) : null}
    </div>
  );
}

export interface StatCardProps {
  testId?: string;
  label: string;
  value: string;
  hint?: ReactNode;
  icon?: string;
  tone?: "default" | "warning" | "danger" | "success" | "worst";
  /** Cross-fade the value when it changes (Veyla dashboard KPIs). */
  animateValue?: boolean;
  delta?: {
    value: string;
    positive?: boolean;
    label?: string;
  } | null;
}

const TONE_TEXT_CLASSES: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-[var(--color-text)]",
  warning: "text-[var(--color-warning)]",
  danger: "text-[var(--color-danger)]",
  success: "text-[var(--color-success)]",
  worst: "text-[var(--color-veyla-worst-bg)]",
};

/**
 * Veyla Stat Card:
 * 12-16px radius, soft ambient diffusion shadow, subtle border, Inter typography.
 * Only shows a delta when comparison data is honestly provided.
 */
export function StatCard({
  testId,
  label,
  value,
  hint,
  icon,
  tone = "default",
  animateValue = false,
  delta,
}: StatCardProps): JSX.Element {
  return (
    <div
      data-testid={testId}
      className="bg-[var(--veyla-card)] rounded-2xl border border-[var(--color-border)] shadow-[var(--shadow-veyla-card)] p-5 flex flex-col justify-between transition-shadow hover:shadow-[var(--shadow-veyla-hover)] min-w-0"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-text-muted)] truncate">
            {label}
          </p>
          <div className="flex items-baseline gap-2 mt-1.5 flex-wrap">
            <span
              className={`text-3xl font-extrabold tracking-tight font-mono ${TONE_TEXT_CLASSES[tone]}`}
            >
              {animateValue ? <FadeValue value={value} /> : value}
            </span>
            {delta ? (
              <span
                className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                  delta.positive
                    ? "bg-[#e6f4ea] text-[#0e6b3a] dark:bg-[rgba(82,183,136,0.16)] dark:text-[#7cd3a2]"
                    : "bg-[#fee2e2] text-[#b91c1c] dark:bg-[rgba(239,68,68,0.18)] dark:text-[#fca5a5]"
                }`}
              >
                <span>{delta.positive ? "↑" : "↓"}</span>
                <span>{delta.value}</span>
                {delta.label ? (
                  <span className="opacity-75 ms-0.5">{delta.label}</span>
                ) : null}
              </span>
            ) : null}
          </div>
        </div>
        {icon ? (
          <span
            aria-hidden="true"
            className="w-10 h-10 rounded-full bg-[var(--veyla-well)] text-[var(--color-text)] flex items-center justify-center shrink-0 border border-[var(--color-border)]"
          >
            <span className="material-symbols-outlined text-[20px]">
              {icon}
            </span>
          </span>
        ) : null}
      </div>
      {hint ? (
        <div className="text-xs text-[var(--color-text-muted)] mt-3 leading-relaxed pt-2 border-t border-[var(--color-card-border)]">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export interface PanelProps {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}

export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
  testId,
}: PanelProps): JSX.Element {
  return (
    <section
      data-testid={testId}
      className={`bg-[var(--veyla-card)] rounded-2xl border border-[var(--color-border)] shadow-[var(--shadow-veyla-card)] p-6 flex flex-col ${className}`}
    >
      <div className="flex items-start justify-between gap-3 mb-5">
        <div>
          <h2 className="text-base sm:text-lg font-bold text-[var(--color-text)] tracking-tight">
            {title}
          </h2>
          {subtitle ? (
            <p className="text-xs text-[var(--color-text-muted)] mt-1 font-normal">
              {subtitle}
            </p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="flex-1 min-w-0">{children}</div>
    </section>
  );
}

/**
 * Honest Empty State:
 * Soft gray surface, dashed hairline, clear honest message.
 */
export function EmptyState({
  message,
  badge,
}: {
  message: string;
  badge?: string;
}): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--veyla-well)] px-4 py-8 text-center"
    >
      {badge ? (
        <span className="inline-block px-2.5 py-0.5 mb-2 rounded-full text-[11px] font-semibold uppercase tracking-wider bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
          {badge}
        </span>
      ) : null}
      <p className="text-sm text-[var(--color-text-muted)] font-medium max-w-sm mx-auto">
        {message}
      </p>
    </div>
  );
}

export function DashboardLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <Link
      to={to}
      className="text-sm font-semibold text-[var(--color-brand)] hover:text-[var(--color-text)] inline-flex items-center gap-1.5 group transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] rounded-md px-1"
    >
      <span>{children}</span>
      <span
        aria-hidden="true"
        className="group-hover:translate-x-0.5 transition-transform rtl:-scale-x-100"
      >
        →
      </span>
    </Link>
  );
}

/**
 * Veyla Flat Skeleton Block:
 * Solid gray block, strictly NO shimmer.
 */
export function VeylaSkeleton({
  className = "h-20 w-full",
}: {
  className?: string;
}): JSX.Element {
  return <div aria-hidden="true" className={`veyla-skeleton ${className}`} />;
}

/* ============================================================
   Veyla Waffle Chart & Breakdown Panel
   Checks-per-day equivalent with real volume scaling,
   LabFlow status colors, hover tooltip, and RTL support.
   ============================================================ */

export interface WaffleDayData {
  date: string;
  label: string;
  total: number;
  breakdown: Record<string, number>;
}

export interface WaffleChartProps {
  days: WaffleDayData[];
  statusConfig: Record<
    string,
    { label: string; color: string; darkColor?: string }
  >;
  tileScale?: number;
  unitLabel?: string;
  /**
   * Called when the hovered/focused day changes so the side panel can
   * cross-fade its numbers in sync with the tooltip.
   */
  onActiveDayChange?: (day: WaffleDayData | null) => void;
}

export function WaffleChart({
  days,
  statusConfig,
  tileScale = 1,
  unitLabel = "sample",
  onActiveDayChange,
}: WaffleChartProps): JSX.Element {
  const [activeDay, setActiveDayState] = useState<WaffleDayData | null>(null);
  const [renderedDays, setRenderedDays] = useState(days);
  const [leaving, setLeaving] = useState(false);
  const [entering, setEntering] = useState(false);

  const setActiveDay = useCallback(
    (day: WaffleDayData | null) => {
      setActiveDayState(day);
      onActiveDayChange?.(day);
    },
    [onActiveDayChange],
  );

  // The dashboard has no 7d/14d/30d control yet; the only range-like change
  // it can receive is fresh daily data. Old tiles leave fully first, then the
  // new set fades in one tile at a time.
  const signature = days.map((day) => `${day.date}:${day.total}`).join("|");
  const lastSignature = useRef(signature);

  useEffect(() => {
    if (signature === lastSignature.current) return;
    lastSignature.current = signature;

    if (prefersReducedMotion()) {
      setRenderedDays(days);
      setLeaving(false);
      setEntering(false);
      setActiveDay(null);
      return;
    }

    setLeaving(true);
    setEntering(false);
    setActiveDay(null);
    const swap = window.setTimeout(
      () => {
        setRenderedDays(days);
        setLeaving(false);
        setEntering(true);
        setActiveDay(null);
      },
      motionDurationMs("--motion-fast", 150),
    );

    return () => window.clearTimeout(swap);
  }, [days, signature, setActiveDay]);

  const enteringCount = renderedDays.length;
  useEffect(() => {
    if (!entering) return;
    const settle = window.setTimeout(
      () => setEntering(false),
      motionDurationMs("--motion-base", 200) +
        Math.min(enteringCount, 10) * 15 +
        40,
    );
    return () => window.clearTimeout(settle);
  }, [entering, enteringCount]);

  return (
    <div className="flex flex-col gap-4">
      {/* Tile Legend */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--color-text-muted)]">
        <div className="flex items-center gap-1.5 font-medium">
          <span className="w-3 h-3 rounded-[3px] bg-[var(--veyla-black)] inline-block" />
          <span>
            1 tile = {tileScale} {unitLabel}
            {tileScale > 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {Object.entries(statusConfig).map(([key, cfg]) => (
            <div key={key} className="flex items-center gap-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full inline-block"
                style={{ backgroundColor: cfg.color }}
              />
              <span className="capitalize">{cfg.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Waffle Grid (Days as columns, RTL-safe tile order) */}
      <div
        className="overflow-x-auto pb-2 relative"
        onMouseLeave={() => setActiveDay(null)}
      >
        <div
          className={`grid grid-flow-col auto-cols-[minmax(28px,1fr)] gap-2 min-w-[320px] ${styles.waffleGrid} ${
            leaving ? styles.waffleGridOut : ""
          }`}
        >
          {renderedDays.map((day, index) => {
            const tilesCount = Math.max(1, Math.ceil(day.total / tileScale));
            const isHovered = activeDay?.date === day.date;
            return (
              <div
                key={day.date}
                className={`flex flex-col items-center gap-1 cursor-pointer group ${
                  entering ? styles.waffleDayIn : ""
                }`}
                style={
                  entering
                    ? { animationDelay: `${Math.min(index, 9) * 15}ms` }
                    : undefined
                }
                onMouseEnter={() => setActiveDay(day)}
                tabIndex={0}
                role="button"
                aria-label={`${day.label}: ${day.total} ${unitLabel}s`}
                onFocus={() => setActiveDay(day)}
                onBlur={() => setActiveDay(null)}
              >
                {/* Day column stacked tiles (up to 8 visual tiles max) */}
                <div
                  className={`w-full p-1.5 rounded-xl transition-colors flex flex-col-reverse gap-1 items-center ${
                    isHovered
                      ? "bg-[var(--veyla-teal)]/30 ring-2 ring-[var(--color-accent)]"
                      : "bg-[var(--veyla-well)] hover:bg-[var(--veyla-teal)]/15"
                  }`}
                  style={{ minHeight: "120px" }}
                >
                  {Array.from({ length: Math.min(8, tilesCount) }).map(
                    (_, idx) => {
                      const statusKeys = Object.keys(day.breakdown);
                      const statusKey =
                        statusKeys[idx % statusKeys.length] || "ready";
                      const color = statusConfig[statusKey]?.color || "#0e6b3a";
                      return (
                        <span
                          key={idx}
                          className="w-full h-2.5 rounded-[4px] transition-transform group-hover:scale-105"
                          style={{
                            backgroundColor:
                              day.total === 0 ? "rgba(18,16,17,0.08)" : color,
                          }}
                        />
                      );
                    },
                  )}
                </div>
                {/* Day Label */}
                <span className="text-[11px] font-mono font-medium text-[var(--color-text-muted)] truncate max-w-full">
                  {day.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* Hover Tooltip */}
        {activeDay ? (
          <div
            role="tooltip"
            className="absolute top-0 end-0 z-20 bg-[var(--veyla-card)] text-[var(--color-text)] border border-[var(--color-border)] shadow-[var(--shadow-veyla-dropdown)] rounded-xl p-3 text-xs pointer-events-none"
          >
            <p className="font-bold text-sm mb-1">{activeDay.label}</p>
            <p className="text-[var(--color-text-muted)] mb-2 font-mono">
              Total: {activeDay.total} {unitLabel}
              {activeDay.total === 1 ? "" : "s"}
            </p>
            <div className="space-y-1">
              {Object.entries(activeDay.breakdown).map(([status, cnt]) => (
                <div
                  key={status}
                  className="flex items-center justify-between gap-4 font-mono"
                >
                  <span className="capitalize text-[var(--color-text-muted)]">
                    {statusConfig[status]?.label || status}:
                  </span>
                  <span className="font-semibold">{cnt}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ============================================================
   Veyla Review Queue Ring & Progress Component
   ============================================================ */

export function ReviewQueueRing({
  pending,
  total,
  size = 110,
  strokeWidth = 10,
}: {
  pending: number;
  total: number;
  size?: number;
  strokeWidth?: number;
}): JSX.Element {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const validTotal = Math.max(total, pending, 1);
  const ratio = Math.min(1, Math.max(0, (validTotal - pending) / validTotal));
  const strokeDashoffset = circumference - ratio * circumference;

  return (
    <div className="relative inline-flex items-center justify-center shrink-0">
      <svg
        width={size}
        height={size}
        className="transform -rotate-90 rtl:rotate-90"
        aria-hidden="true"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-[var(--veyla-well)]"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="text-[var(--color-brand)]"
          fill="none"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-xl sm:text-2xl font-mono font-extrabold text-[var(--color-text)] tracking-tight">
          {pending}
        </span>
        <span className="text-[10px] uppercase font-bold text-[var(--color-text-muted)] tracking-wider">
          Pending
        </span>
      </div>
    </div>
  );
}
