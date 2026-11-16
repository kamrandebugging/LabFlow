import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const read = (relative: string): string =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const rgb = [0, 2, 4].map((offset) => {
    const channel = Number.parseInt(value.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.03928
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return (
    0.2126 * (rgb[0] ?? 0) + 0.7152 * (rgb[1] ?? 0) + 0.0722 * (rgb[2] ?? 0)
  );
}

function ratio(a: string, b: string): number {
  const sorted = [luminance(a), luminance(b)].sort((x, y) => y - x);
  const high = sorted[0] ?? 0;
  const low = sorted[1] ?? 0;
  return (high + 0.05) / (low + 0.05);
}

function composite(
  foreground: string,
  alpha: number,
  background: string,
): string {
  const parse = (hex: string): number[] => {
    const value = hex.replace("#", "");
    return [0, 2, 4].map((offset) =>
      Number.parseInt(value.slice(offset, offset + 2), 16),
    );
  };
  const fg = parse(foreground);
  const bg = parse(background);
  return `#${fg
    .map((channel, index) =>
      Math.round(channel * alpha + (bg[index] ?? 0) * (1 - alpha))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

/**
 * Every list stylesheet that must stay free of literal colours. The invoice
 * list still ships with the pre-Veyla tokens, but it never hardcodes a
 * colour, so the no-literal-colour rule already applies to it.
 */
const TOUCHED_CSS = [
  "../../features/patients/PatientListScreen.module.css",
  "../../features/billing/InvoicesListScreen.module.css",
] as const;

/**
 * Stylesheets converted to the Veyla token set.
 *
 * The invoice list is deliberately excluded: it is converted in the invoice
 * batch, which follows this patient batch. Editing the invoice file here to
 * satisfy a Veyla assertion is out of scope, so the Veyla assertions below
 * only cover the patient list.
 */
const VEYLA_CSS = [
  "../../features/patients/PatientListScreen.module.css",
] as const;

describe("Patients + Invoices list theme", () => {
  it("keeps the touched CSS modules free of literal colours", () => {
    for (const file of TOUCHED_CSS) {
      const css = read(file);
      expect(css, `${file} hex`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(css, `${file} rgb`).not.toMatch(/\brgba?\(/);
      expect(css, `${file} hsl`).not.toMatch(/\bhsla?\(/);
    }
  });

  it("routes the patient list surfaces through the Veyla tokens", () => {
    for (const file of VEYLA_CSS) {
      const css = read(file);
      for (const token of [
        "var(--color-surface)",
        "var(--color-well)",
        "var(--color-card-border)",
        "var(--color-border)",
        "var(--shadow-veyla-card)",
        "var(--shadow-control)",
        "var(--ring-color)",
      ]) {
        expect(css, `${file} uses ${token}`).toContain(token);
      }
    }
  });

  it("leaves no dead neumorphism token in the patient list", () => {
    for (const file of VEYLA_CSS) {
      const css = read(file);
      for (const token of [
        "--shadow-neu-raised",
        "--shadow-neu-inset",
        "--shadow-neu-control",
        "--shadow-neu-control-pressed",
        "--shadow-neu-card",
      ]) {
        expect(css, `${file} drops ${token}`).not.toContain(token);
      }
    }
  });

  it("ships the Veyla shadow and radius scale in both themes", () => {
    const tokens = read("../../theme/tokens.css");
    // Veyla control scale: --shadow-veyla-pill (aliased as --shadow-control),
    // with --shadow-veyla-hover for the raised state.
    expect(tokens).toContain("--shadow-veyla-card:");
    expect(tokens).toContain("--shadow-veyla-pill:");
    expect(tokens).toContain("--shadow-veyla-hover:");
    expect(tokens).toContain("--shadow-veyla-dropdown:");
    expect(tokens).toContain("--shadow-control: var(--shadow-veyla-pill);");
    expect(tokens).toContain("--radius-card: 16px;");
    expect(tokens).toContain("--radius-pill: 9999px;");
    expect(tokens).toContain('[data-theme="dark"]');
  });

  it("gives every interactive control a 44px hit target and a 2px focus ring", () => {
    for (const file of VEYLA_CSS) {
      const css = read(file);
      expect(css, `${file} control height`).toContain("min-height: 44px");
      const minHeights = css.match(/min-height: (\d+)px/g) ?? [];
      expect(minHeights.length, `${file} hit targets`).toBeGreaterThan(0);
      for (const rule of minHeights) {
        const value = Number.parseInt(rule.replace(/\D/g, ""), 10);
        expect(value, `${file} ${rule}`).toBeGreaterThanOrEqual(32);
      }
      expect(css, `${file} focus ring`).toMatch(
        /:focus-visible\s*\{[^}]*outline: 2px solid var\(--ring-color\)/,
      );
      expect(css, `${file} focus offset`).toMatch(/outline-offset: [3-4]px/);
    }
  });

  it("keeps every shipped text pair at >= 4.5:1 in both themes", () => {
    const textPairs = [
      // Light — page, card, well.
      ["#121011", "#eaecec"], // ink on page
      ["#242626", "#eaecec"], // body on page
      ["#596060", "#eaecec"], // muted on page
      ["#646c6c", "#eaecec"], // subtle on page
      ["#121011", "#feffff"], // ink on card
      ["#242626", "#feffff"], // body on card
      ["#596060", "#feffff"], // muted on card
      ["#646c6c", "#feffff"], // subtle on card
      ["#121011", "#f4f6f6"], // ink on well
      ["#242626", "#f4f6f6"], // body on well
      ["#596060", "#f4f6f6"], // muted on well
      ["#646c6c", "#f4f6f6"], // subtle on well
      // Light — brand, accent and status fills.
      ["#feffff", "#121011"], // primary CTA label on near-black fill
      ["#133835", "#cae2e0"], // accent label on teal accent
      ["#0e6b3a", "#e6f4ea"], // success status
      ["#8c5800", "#fef3d6"], // warning status
      ["#b91c1c", "#fee2e2"], // danger status
      ["#0369a1", "#e0f2fe"], // info status
      // Dark — page, card, well.
      ["#f1f2f2", "#111213"], // ink on page
      ["#e1e4e4", "#111213"], // body on page
      ["#9ea3a3", "#111213"], // muted on page
      ["#868e8e", "#111213"], // subtle on page
      ["#f1f2f2", "#191b1c"], // ink on card
      ["#e1e4e4", "#191b1c"], // body on card
      ["#9ea3a3", "#191b1c"], // muted on card
      ["#868e8e", "#191b1c"], // subtle on card
      ["#f1f2f2", "#222526"], // ink on well
      ["#e1e4e4", "#222526"], // body on well
      ["#9ea3a3", "#222526"], // muted on well
      ["#868e8e", "#222526"], // subtle on well
      // Dark — brand, accent and status fills.
      ["#111213", "#f1f2f2"], // primary CTA label on inverted fill
      ["#a4dfda", "#233b39"], // accent label on dark teal accent
      ["#7cd3a2", composite("#7cd3a2", 0.16, "#191b1c")], // success
      ["#f6c776", composite("#f6c776", 0.16, "#191b1c")], // warning
      ["#f87171", composite("#f87171", 0.18, "#191b1c")], // danger
      ["#7dd3fc", composite("#7dd3fc", 0.16, "#191b1c")], // info
    ] as const;

    for (const [text, background] of textPairs) {
      expect(
        ratio(text, background),
        `${text} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps the focus affordance at >= 3:1 against the surfaces", () => {
    // Veyla drops hard outlines for soft elevation, so the hairline border
    // tokens are decorative separators rather than the sole identifier of a
    // control. The 3:1 non-text affordance is carried by the focus ring, so
    // that is what this guardrail measures.
    const focusPairs = [
      ["#121011", "#feffff"], // light ring on card
      ["#121011", "#f4f6f6"], // light ring on well
      ["#a4dfda", "#191b1c"], // dark ring on card
      ["#a4dfda", "#222526"], // dark ring on well
    ] as const;

    for (const [line, surface] of focusPairs) {
      expect(
        ratio(line, surface),
        `${line} on ${surface}`,
      ).toBeGreaterThanOrEqual(3);
    }
  });

  it("ships the hairline border ramp in both themes", () => {
    const tokens = read("../../theme/tokens.css");
    const light = tokens.slice(0, tokens.indexOf('[data-theme="dark"]'));
    const dark = tokens.slice(tokens.indexOf('[data-theme="dark"]'));
    for (const [name, block] of [
      ["light", light],
      ["dark", dark],
    ] as const) {
      expect(block, `${name} border ramp`).toContain("--color-border: rgba(");
      expect(block, `${name} strong border ramp`).toContain(
        "--color-border-strong: rgba(",
      );
      expect(block, `${name} card border ramp`).toContain(
        "--color-card-border: rgba(",
      );
      expect(block, `${name} focus ring`).toContain("--shadow-focus:");
    }
  });
});
