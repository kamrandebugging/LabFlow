/**
 * Dashboard data helpers.
 *
 * Every helper in this file reads from an existing tenant API. Nothing is
 * seeded, guessed or defaulted to a non-zero figure: a failed read is returned
 * as `null` and the screen renders an honest dash.
 */

import { billingService } from "../billing/billingService";
import type { InvoiceSummary } from "../billing/types";
import { sampleService } from "../samples/sampleService";

const PKT_TIME_ZONE = "Asia/Karachi";
const PKT_DAY_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: PKT_TIME_ZONE,
});
const MAX_INVOICE_PAGES = 50;

export const PKT_LABEL = "times are PKT";

export function pktDateLabel(date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: PKT_TIME_ZONE,
  }).format(date);
}

/** True when the ISO timestamp falls on the same Asia/Karachi calendar day. */
export function isTodayInPkt(
  value: string | null | undefined,
  now = new Date(),
): boolean {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  return PKT_DAY_FORMATTER.format(parsed) === PKT_DAY_FORMATTER.format(now);
}

export function formatPkr(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const amount = typeof value === "number" ? value : Number.parseFloat(value);
  if (!Number.isFinite(amount)) return "—";
  return `PKR ${amount.toFixed(2)}`;
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value);
}

/**
 * Read every page of the invoice list. The list endpoint is cursor-paginated;
 * a dashboard count must not silently stop at the first page.
 */
export async function listAllInvoices(
  params: {
    status?: string;
    signal?: AbortSignal;
  } = {},
): Promise<InvoiceSummary[]> {
  const rows: InvoiceSummary[] = [];
  let cursor: string | undefined;
  let previousCursor: string | undefined;
  let pages = 0;

  do {
    const page = await billingService.listInvoices({
      ...params,
      cursor,
      limit: 100,
    });
    rows.push(...page.results);
    pages += 1;
    previousCursor = cursor;
    cursor = page.next_cursor ?? undefined;
    if (cursor && cursor === previousCursor) break;
    if (pages >= MAX_INVOICE_PAGES) {
      throw new Error("Invoice pagination exceeded the safe page limit.");
    }
  } while (cursor);

  return rows;
}

/** Open invoices for the dashboard, fetched by status rather than scanning history. */
export async function listOpenInvoices(
  signal?: AbortSignal,
): Promise<InvoiceSummary[]> {
  const [unpaid, partial] = await Promise.all([
    listAllInvoices({ status: "unpaid", signal }),
    listAllInvoices({ status: "partial", signal }),
  ]);
  return [...unpaid, ...partial];
}

export function outstandingBalance(invoice: InvoiceSummary): number | null {
  if (invoice.net_paid === undefined || invoice.net_paid === null) return null;
  const total = Number.parseFloat(invoice.total || "0");
  const paid = Number.parseFloat(invoice.net_paid || "0");
  if (!Number.isFinite(total) || !Number.isFinite(paid)) return null;
  const balance = total - paid;
  return balance > 0 ? balance : 0;
}

export interface SampleStatusCounts {
  collected: number;
  received: number;
  inProcess: number;
  ready: number;
  rejected: number;
  cancelled: number;
  total: number;
}

/**
 * Exact status totals from the server. GET /samples returns `total` before the
 * 100-row page cap, so one filtered call per status avoids under-counting a
 * busy lab.
 */
export async function fetchSampleStatusCounts(
  signal?: AbortSignal,
): Promise<SampleStatusCounts> {
  const [collected, received, inProcess, ready, rejected, cancelled] =
    await Promise.all([
      sampleService.listSamples({ status: "collected" }, signal),
      sampleService.listSamples({ status: "received" }, signal),
      sampleService.listSamples({ status: "in_process" }, signal),
      sampleService.listSamples({ status: "ready" }, signal),
      sampleService.listSamples({ status: "rejected" }, signal),
      sampleService.listSamples({ status: "cancelled" }, signal),
    ]);

  return {
    collected: collected.total,
    received: received.total,
    inProcess: inProcess.total,
    ready: ready.total,
    rejected: rejected.total,
    cancelled: cancelled.total,
    total:
      collected.total +
      received.total +
      inProcess.total +
      ready.total +
      rejected.total +
      cancelled.total,
  };
}
