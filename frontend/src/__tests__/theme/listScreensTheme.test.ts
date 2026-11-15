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

const TOUCHED_CSS = [
  "../../features/patients/PatientListScreen.module.css",
  "../../features/billing/InvoicesListScreen.module.css",
] as const;

describe("Patients + Invoices neumorphism tokens", () => {
  it("keeps the touched CSS modules free of literal colours", () => {
    for (const file of TOUCHED_CSS) {
      const css = read(file);
      expect(css, `${file} hex`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(css, `${file} rgb`).not.toMatch(/\brgba?\(/);
      expect(css, `${file} hsl`).not.toMatch(/\bhsla?\(/);
    }
  });

  it("ships the control-scale shadow tokens in both themes", () => {
    const tokens = read("../../theme/tokens.css");
    expect(tokens).toContain("--shadow-neu-control:");
    expect(tokens).toContain("--shadow-neu-control-pressed:");
    expect(tokens).toContain('[data-theme="dark"]');
  });

  it("keeps every shipped text pair at >= 4.5:1 in both themes", () => {
    const textPairs = [
      // Light
      ["#081c15", "#faf9f6"], // ink on paper
      ["#35473d", "#faf9f6"], // muted on paper
      ["#45564c", "#faf9f6"], // subtle on paper
      ["#0e6b3a", "#faf9f6"], // brand link on paper
      ["#ffffff", "#0e6b3a"], // primary CTA label
      ["#081c15", "#f1efea"], // ink on well (MRN / totals / inputs)
      ["#35473d", "#f1efea"], // muted on well
      ["#0e6b3a", "#e3f0e8"], // success status
      ["#7a5a00", "#f7efd2"], // warning status
      ["#b42318", "#fdecea"], // danger status
      ["#175cd3", "#eaf1fe"], // info status
      // Dark
      ["#f2f7f3", "#081c15"], // ink on page
      ["#f2f7f3", "#12291d"], // ink on card
      ["#c3d6c9", "#12291d"], // muted on card
      ["#a8bfb1", "#12291d"], // subtle on card
      ["#f2f7f3", "#0b1f14"], // ink on well
      ["#52b788", "#12291d"], // leaf link on card
      ["#081c15", "#52b788"], // primary CTA label
      ["#52b788", composite("#52b788", 0.14, "#12291d")], // success
      ["#c9a227", composite("#c9a227", 0.14, "#12291d")], // warning
      ["#f97066", composite("#f97066", 0.12, "#12291d")], // danger
      ["#84adff", composite("#84adff", 0.12, "#12291d")], // info
    ] as const;

    for (const [text, background] of textPairs) {
      expect(
        ratio(text, background),
        `${text} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps shipped borders at >= 3:1 against their surface", () => {
    const borderPairs = [
      // Light: control border on paper, strong header rule on paper.
      ["#7c8a82", "#faf9f6"],
      ["#5a6a61", "#faf9f6"],
      // Dark: control border on page, strong header rule on card.
      ["#6e8a79", "#081c15"],
      ["#8fae9c", "#12291d"],
    ] as const;

    for (const [line, surface] of borderPairs) {
      expect(ratio(line, surface), `${line} on ${surface}`).toBeGreaterThanOrEqual(
        3,
      );
    }
  });
});
