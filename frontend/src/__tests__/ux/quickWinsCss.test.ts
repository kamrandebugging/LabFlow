import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const read = (relative: string): string =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

const patientRecordCss = read(
  "../../features/patients/PatientRecord.module.css",
);
const newInvoiceCss = read(
  "../../features/billing/NewInvoiceScreen.module.css",
);
const invoiceDetailCss = read(
  "../../features/billing/InvoiceDetailScreen.module.css",
);
const patientFormCss = read("../../features/patients/PatientForm.module.css");
const indexCss = read("../../index.css");
const tokensCss = read("../../theme/tokens.css");

/** Returns the body of the first block matching `selector` inside `css`. */
function blockFor(css: string, selector: string): string {
  const start = css.indexOf(selector);
  if (start === -1) return "";
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("Item 5 — pulse animations respect prefers-reduced-motion", () => {
  for (const [name, css] of [
    ["PatientRecord", patientRecordCss],
    ["NewInvoiceScreen", newInvoiceCss],
  ] as const) {
    it(`${name} gates the pulse and keeps a static reduced-motion state`, () => {
      expect(css).toContain("@media (prefers-reduced-motion: no-preference)");
      expect(css).toContain("@media (prefers-reduced-motion: reduce)");

      const noPreference = css.indexOf(
        "@media (prefers-reduced-motion: no-preference)",
      );
      const reduce = css.indexOf("@media (prefers-reduced-motion: reduce)");
      const pulseSelector =
        name === "PatientRecord" ? ".pulse {" : ".pulseText {";

      const gatedIndex = css.indexOf(pulseSelector, noPreference);
      expect(gatedIndex).toBeGreaterThan(noPreference);
      expect(gatedIndex).toBeLessThan(reduce);
      expect(css.slice(gatedIndex, gatedIndex + 160)).toContain(
        "animation: pulse 2s",
      );

      const reducedIndex = css.indexOf(pulseSelector, reduce);
      expect(reducedIndex).toBeGreaterThan(reduce);
      expect(css.slice(reducedIndex, reducedIndex + 120)).toContain(
        "animation: none",
      );
    });
  }
});

describe("Item 6 — payment toast exists on the payment path", () => {
  it("uses the shared toast markup and the formatted amount", () => {
    const screenSource = read("../../features/billing/InvoiceDetailScreen.tsx");
    expect(screenSource).toContain('role="status"');
    expect(screenSource).toContain("billing:detail.toast_payment");
    expect(screenSource).toContain("formatMoney(amt.toFixed(2), lang)");
  });
});

describe("Item 1 — footer alignment and mobile stacking", () => {
  it("aligns the footer to the inline-end and stacks full-width buttons on mobile", () => {
    expect(blockFor(newInvoiceCss, ".footer {")).toContain(
      "justify-content: flex-end",
    );
    const mobile = newInvoiceCss.slice(
      newInvoiceCss.indexOf("@media (max-width: 640px)"),
    );
    expect(mobile).toContain(".footer {");
    expect(mobile).toContain("flex-direction: column-reverse");
    expect(mobile).toContain("min-height: 48px");
  });
});

describe("Item 10 — delete control separator on desktop", () => {
  it("adds a border-inline-start separator at >=1024px", () => {
    const desktop = patientRecordCss.slice(
      patientRecordCss.indexOf("@media (min-width: 1024px)"),
    );
    expect(desktop).toContain(".dangerSeparator {");
    expect(desktop).toContain("margin-inline-start: 12px");
    expect(desktop).toContain("padding-inline-start: 12px");
    expect(desktop).toContain(
      "border-inline-start: 1px solid var(--color-border)",
    );
  });
});

describe("Item 12 — global scroll padding clears the fixed header", () => {
  it("sets scroll-padding-top on html and scroll-margin-top on controls", () => {
    expect(indexCss).toContain("scroll-padding-top: 80px");
    expect(indexCss).toContain("scroll-margin-top: 80px");
    expect(indexCss).toContain('[role="alert"]');
    // One global rule only: no screen module duplicates the rule.
    for (const css of [
      patientRecordCss,
      newInvoiceCss,
      invoiceDetailCss,
      patientFormCss,
    ]) {
      expect(css).not.toContain("scroll-margin-top");
      expect(css).not.toContain("scroll-padding-top");
    }
  });
});

describe("Item 15 — money inputs use mono with tabular figures", () => {
  it("documents the rule next to --font-mono and enables tabular figures", () => {
    expect(tokensCss).toContain(
      "Money inputs (amounts, totals, PKR) use --font-mono with tabular figures",
    );
    expect(tokensCss).toContain("font-variant-numeric: tabular-nums");
    expect(tokensCss).toContain("--font-mono:");
  });
});
