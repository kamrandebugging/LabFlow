/**
 * Shared formatting module (Doc 07 §10) — screens never format inline.
 *
 * Everything here obeys two rules in both languages:
 *   - digits are Latin 0-9; dates use English month names;
 *   - money, dates, IDs and phones stay LTR and are never re-ordered by RTL.
 */
import statusValues from "./statusValues.json";

export type Lang = "en" | "ur";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/** PKR 1250.00 in English, روپے 1250.00 in Urdu. Never regroups or rounds. */
export function formatMoney(
  value: string | number | null | undefined,
  lang: Lang = "en",
): string {
  const raw = value === null || value === undefined ? "" : String(value).trim();
  if (!raw) return "—";
  return lang === "ur" ? `روپے ${raw}` : `PKR ${raw}`;
}

interface DateParts {
  year: string;
  month: string;
  day: string;
}

function parseDateParts(value: string): DateParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return null;
  return {
    year: match[1] as string,
    month: match[2] as string,
    day: match[3] as string,
  };
}

/** YYYY-MM-DD → DD MMM YYYY (English month names in both languages). */
export function formatDate(
  value: string | null | undefined,
  fallback = "—",
): string {
  if (!value) return fallback;
  const parts = parseDateParts(value);
  if (!parts) return value;
  const monthIndex = Number(parts.month) - 1;
  const month = MONTHS[monthIndex] ?? parts.month;
  return `${parts.day} ${month} ${parts.year}`;
}

/**
 * ISO 8601 datetime → DD MMM YYYY, HH:mm.
 * The wall-clock fields are read from the wire string, so the stored +05:00
 * offset is honoured and the browser's own zone never re-derives the time.
 */
export function formatDateTime(
  value: string | null | undefined,
  fallback = "—",
): string {
  if (!value) return fallback;
  const date = formatDate(value, fallback);
  const match = /^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})/.exec(value.trim());
  if (!match) return date;
  return `${date}, ${match[1]}:${match[2]}`;
}

export interface AgeBand {
  value: number;
  unit: "days" | "months" | "years";
}

/** Doc 07 §10: under 90 days, under 2 years, otherwise years. */
export function ageBand(
  dateOfBirth: string | null | undefined,
  now: Date = new Date(),
): AgeBand | null {
  const parts = dateOfBirth ? parseDateParts(dateOfBirth) : null;
  if (!parts) return null;
  const born = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
  );
  if (!Number.isFinite(born)) return null;
  const days = Math.floor((now.getTime() - born) / 86_400_000);
  if (days < 0) return null;
  if (days < 90) return { value: days, unit: "days" };
  if (days < 730) return { value: Math.floor(days / 30.4375), unit: "months" };
  return { value: Math.floor(days / 365.25), unit: "years" };
}

const AGE_UNITS: Record<Lang, Record<AgeBand["unit"], string>> = {
  en: { days: "days", months: "months", years: "years" },
  ur: { days: "دن", months: "ماہ", years: "سال" },
};

/** Age display, e.g. "34 years" / "34 سال". Null DOB is never guessed. */
export function formatAge(
  dateOfBirth: string | null | undefined,
  lang: Lang = "en",
  notRecorded = "Not recorded",
): string {
  const band = ageBand(dateOfBirth);
  if (!band) return `${notRecorded}`;
  return `${band.value} ${AGE_UNITS[lang][band.unit]}`;
}

/** Decimal string plus %, never an arithmetic operation. */
export function formatPercent(
  value: string | number | null | undefined,
): string {
  const raw = value === null || value === undefined ? "" : String(value).trim();
  return raw ? `${raw}%` : "—";
}

/** IDs are monospace and forced LTR wherever they appear. */
export function formatId(value: string | null | undefined): string {
  return value ?? "—";
}

export const idProps = {
  dir: "ltr",
  className: "font-mono lf-ltr",
} as const;

export type StatusDomain = keyof typeof statusValues;

/**
 * Translate a raw Doc 02 status value from the common namespace. A value with
 * no key fails `npm run i18n:check`, not silently at runtime.
 */
export function statusLabel(
  domain: StatusDomain,
  raw: string | null | undefined,
  t: (key: string) => string,
): string {
  if (!raw) return "—";
  return t(`status.${domain}.${raw}`);
}

/** True when the value is a known raw status for that domain. */
export function isKnownStatus(domain: StatusDomain, raw: string): boolean {
  return (statusValues[domain] as readonly string[]).includes(raw);
}

/** "times are PKT" stated once per screen, never per row. */
export function pktNotice(t: (key: string) => string): string {
  return t("time.pkt");
}
