import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface DashboardHeaderProps {
  title: string;
  subtitle: string;
  badge?: string;
}

export function DashboardHeader({
  title,
  subtitle,
  badge,
}: DashboardHeaderProps): JSX.Element {
  return (
    <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
          {title}
        </h1>
        <p className="text-sm text-slate-500 font-normal mt-1">{subtitle}</p>
      </div>
      {badge ? (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 font-mono self-start sm:self-auto">
          <span
            aria-hidden="true"
            className="w-2 h-2 rounded-full bg-emerald-500"
          />
          {badge}
        </span>
      ) : null}
    </div>
  );
}

interface StatCardProps {
  testId: string;
  label: string;
  value: string;
  hint?: string;
  icon?: string;
  tone?: "default" | "warning" | "danger" | "success";
}

const TONE_CLASSES: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-slate-900",
  warning: "text-amber-700",
  danger: "text-red-700",
  success: "text-emerald-700",
};

export function StatCard({
  testId,
  label,
  value,
  hint,
  icon,
  tone = "default",
}: StatCardProps): JSX.Element {
  return (
    <div
      data-testid={testId}
      className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col justify-between"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {label}
          </p>
          <p
            className={`text-3xl font-bold mt-1 tracking-tight ${TONE_CLASSES[tone]}`}
          >
            {value}
          </p>
        </div>
        {icon ? (
          <span
            aria-hidden="true"
            className="w-10 h-10 rounded-lg bg-[#86f2e4]/40 text-[#005c55] flex items-center justify-center shrink-0"
          >
            <span className="material-symbols-outlined text-[22px]">
              {icon}
            </span>
          </span>
        ) : null}
      </div>
      {hint ? (
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">{hint}</p>
      ) : null}
    </div>
  );
}

interface PanelProps {
  title: string;
  subtitle?: string;
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
      className={`bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col ${className}`}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          {subtitle ? (
            <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  );
}

export function EmptyState({ message }: { message: string }): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500"
    >
      {message}
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
      className="text-sm font-medium text-teal-700 hover:text-teal-800 inline-flex items-center gap-1 group transition-colors"
    >
      <span>{children}</span>
      <span
        aria-hidden="true"
        className="group-hover:translate-x-0.5 transition-transform"
      >
        →
      </span>
    </Link>
  );
}
