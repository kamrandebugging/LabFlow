import { sampleService } from "../samples/sampleService";

const PKT_TIME_ZONE = "Asia/Karachi";
const PKT_DAY_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: PKT_TIME_ZONE,
});
const DAY_LABEL = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  timeZone: PKT_TIME_ZONE,
});

const MAX_SAMPLE_PAGES = 20;
const SAMPLE_PAGE_SIZE = 100;

export interface SampleDayBucket {
  date: string;
  label: string;
  /** Real samples collected that day. Never fabricated. */
  total: number;
  /** Ready + Collected -> Veyla "Passed" (teal). */
  ready: number;
  /** In Process + Received -> Veyla "Review" (grey). */
  review: number;
  /** Rejected -> Veyla "Declined" (near-black). */
  declined: number;
}

/** Day key in the tenant timezone, e.g. "2026-11-16". */
function pktDayKey(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return PKT_DAY_FORMATTER.format(date);
}

/**
 * Per-day sample buckets for the "Checks per day" waffle.
 *
 * There is no server-side per-day aggregate, so this derives the buckets from
 * the samples the existing GET /samples endpoint already returns. It pages
 * newest-first and stops as soon as it walks past the requested window: no new
 * endpoint, no backend change, and no fabricated counts.
 */
export async function fetchSampleDayBuckets(
  days: number,
  signal?: AbortSignal,
): Promise<SampleDayBucket[]> {
  const buckets = new Map<string, SampleDayBucket>();

  // Seed the window oldest -> newest so empty days still render as Capacity.
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = pktDayKey(d);
    buckets.set(key, {
      date: key,
      label: DAY_LABEL.format(d),
      total: 0,
      ready: 0,
      review: 0,
      declined: 0,
    });
  }

  const oldestKey = Array.from(buckets.keys())[0];

  for (let page = 1; page <= MAX_SAMPLE_PAGES; page++) {
    const { results } = await sampleService.listSamples(
      { page, limit: SAMPLE_PAGE_SIZE, order: "newest" },
      signal,
    );
    if (!results.length) break;

    for (const sample of results) {
      const key = pktDayKey(sample.collected_at);
      const bucket = buckets.get(key);
      if (!bucket) continue;
      bucket.total += 1;
      if (sample.status === "ready" || sample.status === "collected") {
        bucket.ready += 1;
      } else if (
        sample.status === "in_process" ||
        sample.status === "received"
      ) {
        bucket.review += 1;
      } else if (sample.status === "rejected") {
        bucket.declined += 1;
      }
      // Cancelled counts towards the day's total but renders as Capacity.
    }

    const last = results[results.length - 1];
    if (!last) break;
    const lastKey = pktDayKey(last.collected_at);
    if (oldestKey && lastKey && lastKey < oldestKey) break;
    if (results.length < SAMPLE_PAGE_SIZE) break;
  }

  return Array.from(buckets.values());
}
