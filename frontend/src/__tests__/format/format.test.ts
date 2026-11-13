import { describe, expect, it } from "vitest";

import {
  ageBand,
  formatAge,
  formatDate,
  formatDateTime,
  formatId,
  formatMoney,
  formatPercent,
} from "../../lib/format";

describe("shared formatting (Doc 07 §10)", () => {
  it("keeps money verbatim and only swaps the prefix", () => {
    expect(formatMoney("1250.00", "en")).toBe("PKR 1250.00");
    expect(formatMoney("1250.00", "ur")).toBe("روپے 1250.00");
    expect(formatMoney("0.00", "ur")).toBe("روپے 0.00");
  });

  it("formats dates with English month names and Latin digits in both languages", () => {
    expect(formatDate("2026-10-20")).toBe("20 Oct 2026");
    expect(formatDate("2026-10-20T10:00:00+05:00")).toBe("20 Oct 2026");
  });

  it("reads datetime wall-clock fields from the wire offset, not the browser zone", () => {
    expect(formatDateTime("2026-11-03T09:15:00+05:00")).toBe(
      "03 Nov 2026, 09:15",
    );
  });

  it("selects the age band exactly as Doc 07 §10 states", () => {
    const now = new Date("2026-11-13T00:00:00Z");
    expect(ageBand("2026-10-01", now)).toEqual({ value: 43, unit: "days" });
    expect(ageBand("2025-09-01", now)).toEqual({ value: 14, unit: "months" });
    expect(ageBand("1992-11-01", now)).toEqual({ value: 34, unit: "years" });
    expect(ageBand(null, now)).toBeNull();
  });

  it("localises only the age unit, never the digits", () => {
    expect(formatAge("1992-11-01", "en", "Not recorded")).toBe("34 years");
    expect(formatAge("1992-11-01", "ur", "درج نہیں")).toBe("34 سال");
    expect(formatAge(null, "ur", "درج نہیں")).toBe("درج نہیں");
  });

  it("never converts digits or adds separators", () => {
    expect(formatPercent("12.5")).toBe("12.5%");
    expect(formatId("MRN-000123")).toBe("MRN-000123");
  });
});
